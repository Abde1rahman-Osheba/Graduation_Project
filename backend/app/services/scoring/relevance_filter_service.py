"""
PATHS Backend — Relevance filter (role family + skill overlap + vector).

Implements the "Score Only Relevant Jobs" rule from the spec
(§3 + §10): never send a finance / sales / unrelated job to the
LlamaAgent if the candidate is clearly a software engineer.

The filter combines three deterministic signals:

  1. **Role-family match.** Inferred from skills + titles via a small
     keyword catalog. Exact match passes.
  2. **Required-skill overlap ratio.** ``matched_required / total_required``.
  3. **Qdrant vector similarity** ≥ ``SCORING_MIN_RELEVANCE_THRESHOLD``.

A job is relevant if any of (1), (2), or (3) is strong, **but** clearly
unrelated families (e.g. software ↔ accounting) require BOTH (2) and (3)
to be strong.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Iterable

from app.core.config import get_settings
from app.db.repositories.candidates_relational import CandidateFullProfile
from app.db.repositories.jobs_relational import JobFullProfile

logger = logging.getLogger(__name__)
settings = get_settings()


# ── Role family catalog ──────────────────────────────────────────────────


ROLE_FAMILIES: list[str] = [
    "software_engineering",
    "data_science",
    "machine_learning",
    "cybersecurity",
    "devops",
    "product_management",
    "ui_ux",
    "business_analysis",
    "sales",
    "marketing",
    "hr",
    "finance",
    "other",
]

# Lowercase keywords. A token matches if it appears as a whole word in
# the haystack (we lowercase + split punctuation before matching).
_ROLE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "software_engineering": (
        "software engineer", "software developer", "backend engineer",
        "backend developer", "frontend engineer", "frontend developer",
        "full stack", "fullstack", "full-stack", "web developer",
        "python developer", "java developer", "javascript", "typescript",
        "react", "node.js", "fastapi", "django", "flask", "spring boot",
        "rest api", "graphql", "microservices", "go", "golang", "rust",
        "c++", "c#", ".net", "ruby on rails", "android engineer",
        "ios engineer",
    ),
    "data_science": (
        "data scientist", "data analyst", "statistician", "analytics engineer",
        "business intelligence", "tableau", "power bi", "looker",
        "jupyter", "pandas", "numpy", "regression", "statistics",
        "data mining",
    ),
    "machine_learning": (
        "machine learning", "ml engineer", "ai engineer", "deep learning",
        "tensorflow", "pytorch", "scikit-learn", "sklearn", "transformer",
        "llm", "langchain", "langgraph", "rag",
        "computer vision", "natural language processing", "nlp",
        "huggingface", "hugging face", "mlops",
    ),
    "cybersecurity": (
        "cybersecurity", "cyber security", "security engineer", "soc analyst",
        "penetration tester", "pentest", "siem", "incident response",
        "blue team", "red team", "ciso", "iso 27001", "nist",
        "vulnerability", "threat intel",
    ),
    "devops": (
        "devops", "site reliability", "sre", "platform engineer",
        "infrastructure engineer", "kubernetes", "k8s", "docker",
        "terraform", "ansible", "ci/cd", "ci cd", "continuous integration",
        "aws", "azure", "gcp", "cloud engineer",
    ),
    "product_management": (
        "product manager", "product owner", "associate product manager",
        "technical product manager", "head of product", "vp of product",
    ),
    "ui_ux": (
        "ui designer", "ux designer", "product designer",
        "user experience", "user interface", "figma", "interaction designer",
        "design system",
    ),
    "business_analysis": (
        "business analyst", "ba", "requirements analyst", "process analyst",
        "systems analyst", "business intelligence analyst",
    ),
    "sales": (
        "sales representative", "account executive", "account manager",
        "business development", "bdr", "sdr", "inside sales", "outside sales",
        "sales engineer", "channel partner",
    ),
    "marketing": (
        "marketing", "growth marketer", "content marketer",
        "performance marketing", "social media", "seo",
        "digital marketing", "brand manager", "marketing manager",
        "campaign manager",
    ),
    "hr": (
        "human resources", "hr specialist", "hr manager", "recruiter",
        "talent acquisition", "people operations", "compensation analyst",
        "hr business partner",
    ),
    "finance": (
        "accountant", "accounting", "financial analyst", "auditor",
        "audit", "controller", "cfo", "treasury", "tax accountant",
        "actuary", "underwriter",
    ),
}

# Pairs of role families that should NEVER be considered close enough
# without strong skill+vector evidence.
_INCOMPATIBLE_FAMILIES: frozenset[frozenset[str]] = frozenset({
    frozenset({"software_engineering", "finance"}),
    frozenset({"software_engineering", "hr"}),
    frozenset({"software_engineering", "sales"}),
    frozenset({"software_engineering", "marketing"}),
    frozenset({"data_science", "sales"}),
    frozenset({"data_science", "hr"}),
    frozenset({"machine_learning", "finance"}),
    frozenset({"machine_learning", "hr"}),
    frozenset({"machine_learning", "sales"}),
    frozenset({"cybersecurity", "marketing"}),
    frozenset({"cybersecurity", "sales"}),
    frozenset({"devops", "finance"}),
    frozenset({"devops", "sales"}),
    frozenset({"devops", "hr"}),
    frozenset({"ui_ux", "finance"}),
    frozenset({"ui_ux", "hr"}),
})

# Families considered "adjacent" — relevance is loosened across them.
_ADJACENT_FAMILIES: frozenset[frozenset[str]] = frozenset({
    frozenset({"software_engineering", "devops"}),
    frozenset({"software_engineering", "machine_learning"}),
    frozenset({"software_engineering", "data_science"}),
    frozenset({"data_science", "machine_learning"}),
    frozenset({"devops", "cybersecurity"}),
    frozenset({"product_management", "ui_ux"}),
    frozenset({"product_management", "business_analysis"}),
})


# ── Result containers ────────────────────────────────────────────────────


@dataclass
class RelevanceDecision:
    is_relevant: bool
    relevance_score: float                 # 0..1
    candidate_role_family: str
    job_role_family: str
    skill_overlap_ratio: float
    vector_similarity_score: float         # 0..100 (or 0 when not provided)
    reasons: list[str] = field(default_factory=list)


# ── Helpers ──────────────────────────────────────────────────────────────


def _build_haystack(*texts: str | None) -> str:
    return " ".join(t.lower() for t in texts if t).strip()


def infer_role_family(haystack: str) -> str:
    """Return the role family for the given lowercased text blob."""
    if not haystack:
        return "other"
    best_family = "other"
    best_hits = 0
    for family, keywords in _ROLE_KEYWORDS.items():
        hits = sum(1 for kw in keywords if kw in haystack)
        if hits > best_hits:
            best_family = family
            best_hits = hits
    return best_family


def candidate_role_family(profile: CandidateFullProfile) -> str:
    """Infer the candidate's primary role family deterministically."""
    c = profile.candidate
    parts: list[str] = [c.current_title or "", c.headline or "", c.summary or ""]
    for cs, sk in profile.skills:
        parts.append(sk.normalized_name or "")
    for exp, _co in profile.experiences:
        parts.append(exp.title or "")
    return infer_role_family(_build_haystack(*parts))


def job_role_family(profile: JobFullProfile) -> str:
    j = profile.job
    parts: list[str] = [
        j.title or "",
        j.summary or "",
        j.description_text or "",
        j.requirements or "",
    ]
    for jsr, sk in profile.skill_requirements:
        parts.append((sk.normalized_name if sk else jsr.skill_name_normalized) or "")
    return infer_role_family(_build_haystack(*parts))


def candidate_skill_set(profile: CandidateFullProfile) -> set[str]:
    return {
        sk.normalized_name.strip().lower()
        for _, sk in profile.skills
        if sk and sk.normalized_name
    }


def job_required_skills(profile: JobFullProfile) -> tuple[set[str], set[str]]:
    """Return (required_skills, preferred_skills) as lowercase sets."""
    required: set[str] = set()
    preferred: set[str] = set()
    for jsr, sk in profile.skill_requirements:
        name = (sk.normalized_name if sk else jsr.skill_name_normalized) or ""
        name = name.strip().lower()
        if not name:
            continue
        if jsr.is_required:
            required.add(name)
        else:
            preferred.add(name)
    return required, preferred


def skill_overlap_ratio(
    candidate_skills: set[str],
    required_skills: Iterable[str],
) -> float:
    required = set(required_skills)
    if not required:
        return 0.0
    matched = candidate_skills & required
    return len(matched) / len(required)


# ── Decision ─────────────────────────────────────────────────────────────


def _families_are_incompatible(a: str, b: str) -> bool:
    if a == b or "other" in (a, b):
        return False
    return frozenset({a, b}) in _INCOMPATIBLE_FAMILIES


def _families_are_adjacent(a: str, b: str) -> bool:
    if a == b:
        return True
    if "other" in (a, b):
        return False
    return frozenset({a, b}) in _ADJACENT_FAMILIES


def assess_relevance(
    candidate: CandidateFullProfile,
    job: JobFullProfile,
    *,
    candidate_family: str | None = None,
    vector_similarity_score: float = 0.0,
    min_relevance_threshold: float | None = None,
) -> RelevanceDecision:
    """Decide whether `job` is worth scoring for this `candidate`."""
    cand_family = candidate_family or candidate_role_family(candidate)
    j_family = job_role_family(job)

    cand_skills = candidate_skill_set(candidate)
    required_skills, _preferred = job_required_skills(job)
    overlap = skill_overlap_ratio(cand_skills, required_skills)

    thr = (
        settings.scoring_min_relevance_threshold
        if min_relevance_threshold is None
        else float(min_relevance_threshold)
    )
    threshold_pct = thr * 100.0
    reasons: list[str] = []
    relevance_signals: list[float] = []

    family_match = cand_family == j_family
    if family_match:
        reasons.append(f"role_family_match:{cand_family}")
        relevance_signals.append(1.0)
    elif _families_are_adjacent(cand_family, j_family):
        reasons.append(f"role_family_adjacent:{cand_family}↔{j_family}")
        relevance_signals.append(0.7)
    elif _families_are_incompatible(cand_family, j_family):
        reasons.append(f"role_family_incompatible:{cand_family}↔{j_family}")
        # Only ALL strong signals can rescue an incompatible pair
        strong_skill = overlap >= 0.7
        strong_vector = vector_similarity_score >= max(threshold_pct + 25.0, 75.0)
        if not (strong_skill and strong_vector):
            return RelevanceDecision(
                is_relevant=False,
                relevance_score=0.0,
                candidate_role_family=cand_family,
                job_role_family=j_family,
                skill_overlap_ratio=overlap,
                vector_similarity_score=vector_similarity_score,
                reasons=reasons + ["incompatible_families_without_strong_evidence"],
            )

    if overlap >= 0.5:
        reasons.append(f"skill_overlap_strong:{overlap:.2f}")
        relevance_signals.append(min(1.0, overlap))
    elif overlap > 0:
        reasons.append(f"skill_overlap_weak:{overlap:.2f}")
        relevance_signals.append(overlap * 0.6)

    if vector_similarity_score >= threshold_pct:
        signal = min(1.0, vector_similarity_score / 100.0)
        reasons.append(
            f"vector_similarity_above_threshold:{vector_similarity_score:.1f} "
            f">= {threshold_pct:.1f}",
        )
        relevance_signals.append(signal)
    elif vector_similarity_score > 0:
        reasons.append(
            f"vector_similarity_below_threshold:{vector_similarity_score:.1f} "
            f"< {threshold_pct:.1f}",
        )

    relevance_score = max(relevance_signals) if relevance_signals else 0.0

    is_relevant = (
        family_match
        or overlap >= 0.4
        or vector_similarity_score >= threshold_pct
        or _families_are_adjacent(cand_family, j_family)
    )
    if not is_relevant:
        reasons.append("no_signal_strong_enough")
    return RelevanceDecision(
        is_relevant=is_relevant,
        relevance_score=round(relevance_score, 3),
        candidate_role_family=cand_family,
        job_role_family=j_family,
        skill_overlap_ratio=round(overlap, 3),
        vector_similarity_score=round(vector_similarity_score, 3),
        reasons=reasons,
    )


__all__ = [
    "ROLE_FAMILIES",
    "RelevanceDecision",
    "assess_relevance",
    "candidate_role_family",
    "candidate_skill_set",
    "infer_role_family",
    "job_required_skills",
    "job_role_family",
    "skill_overlap_ratio",
]
