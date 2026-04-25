"""
PATHS Backend — Job normalizer.

Converts raw scraped job dicts (returned by `scraper_adapter`) into a
clean, validated `NormalizedJob` ready for relational + graph + vector
sync. Performs:

  * field harmonization (handles both `title`/`job_title` etc.)
  * text cleanup (whitespace, boilerplate)
  * workplace-type detection (remote / hybrid / onsite / unknown)
  * year-of-experience extraction (e.g. "3+ years", "2-5 years")
  * deterministic skill extraction (via `skill_dictionary`)
  * validation (skip when title / company / source URL missing)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable

from app.services.job_scraper.skill_dictionary import (
    extract_skills_from_text,
    normalize_skill_list,
)

logger = logging.getLogger(__name__)


# ── NormalizedJob dataclass ──────────────────────────────────────────────


@dataclass
class NormalizedJob:
    """Spec-compliant normalized job structure."""

    title: str
    company_name: str
    source_platform: str
    source_url: str
    location_text: str | None = None
    workplace_type: str = "unknown"
    employment_type: str | None = None
    seniority_level: str | None = None
    min_years_experience: int | None = None
    max_years_experience: int | None = None
    summary: str | None = None
    description: str | None = None
    responsibilities: list[str] = field(default_factory=list)
    requirements: list[str] = field(default_factory=list)
    required_skills: list[str] = field(default_factory=list)
    preferred_skills: list[str] = field(default_factory=list)
    education_requirements: list[str] = field(default_factory=list)
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str | None = None
    posted_at: datetime | None = None
    scraped_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "company_name": self.company_name,
            "source_platform": self.source_platform,
            "source_url": self.source_url,
            "location_text": self.location_text,
            "workplace_type": self.workplace_type,
            "employment_type": self.employment_type,
            "seniority_level": self.seniority_level,
            "min_years_experience": self.min_years_experience,
            "max_years_experience": self.max_years_experience,
            "summary": self.summary,
            "description": self.description,
            "responsibilities": list(self.responsibilities),
            "requirements": list(self.requirements),
            "required_skills": list(self.required_skills),
            "preferred_skills": list(self.preferred_skills),
            "education_requirements": list(self.education_requirements),
            "salary_min": self.salary_min,
            "salary_max": self.salary_max,
            "salary_currency": self.salary_currency,
            "posted_at": self.posted_at.isoformat() if self.posted_at else None,
            "scraped_at": self.scraped_at.isoformat(),
            "raw_payload": self.raw_payload,
        }


@dataclass
class RejectedJob:
    raw: dict[str, Any]
    reasons: list[str]


# ── Text cleaning helpers ────────────────────────────────────────────────

_WS_RE = re.compile(r"[ \t]+")
_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")
_LINKEDIN_BOILERPLATE_RE = re.compile(
    r"(?:see who .* is hiring|sign in to view|join now to see|"
    r"easy apply|apply on company website|share this job|"
    r"saved jobs|premium career insights)",
    re.IGNORECASE,
)
_TRACKING_PARAM_RE = re.compile(r"[?&](?:utm_[^=]+|trk|trkInfo|refId)=[^&#]*")


def _clean_text(text: str | None) -> str | None:
    if not text:
        return None
    cleaned = text.replace("\r", "\n")
    cleaned = _LINKEDIN_BOILERPLATE_RE.sub(" ", cleaned)
    cleaned = _WS_RE.sub(" ", cleaned)
    cleaned = _MULTI_NEWLINE_RE.sub("\n\n", cleaned)
    return cleaned.strip() or None


def _clean_url(url: str | None) -> str | None:
    if not url:
        return None
    return _TRACKING_PARAM_RE.sub("", url.strip()) or None


def _split_bullets(text: str | None) -> list[str]:
    if not text:
        return []
    bullets: list[str] = []
    for raw in re.split(r"\r?\n|\u2022|\u2023|\u25e6|^\s*[-*•]\s+", text, flags=re.MULTILINE):
        item = raw.strip(" -*•·\t")
        if item and len(item) > 2:
            bullets.append(item)
    return bullets


# ── Workplace / experience / employment / seniority helpers ──────────────

_WORKPLACE_PATTERNS = [
    (re.compile(r"\bremote(?:-?first)?\b", re.IGNORECASE), "remote"),
    (re.compile(r"\bwork[ -]?from[ -]?home\b|\bwfh\b", re.IGNORECASE), "remote"),
    (re.compile(r"\bhybrid\b", re.IGNORECASE), "hybrid"),
    (re.compile(r"\b(on[ -]?site|onsite|in[ -]?office|in person)\b", re.IGNORECASE), "onsite"),
]


def detect_workplace_type(*texts: str | None) -> str:
    haystack = " \n ".join(t for t in texts if t)
    for pattern, label in _WORKPLACE_PATTERNS:
        if pattern.search(haystack):
            return label
    return "unknown"


_EXPERIENCE_RANGE_RE = re.compile(
    r"(\d+)\s*(?:[-–to]+)\s*(\d+)\+?\s*(?:years?|yrs?)\b",
    re.IGNORECASE,
)
_EXPERIENCE_PLUS_RE = re.compile(
    r"(?:at\s+least\s+|min(?:imum)?\s+|over\s+)?(\d+)\s*\+?\s*(?:years?|yrs?)\b",
    re.IGNORECASE,
)


def detect_experience_range(*texts: str | None) -> tuple[int | None, int | None]:
    haystack = " ".join(t for t in texts if t)
    if not haystack:
        return None, None
    rng = _EXPERIENCE_RANGE_RE.search(haystack)
    if rng:
        try:
            return int(rng.group(1)), int(rng.group(2))
        except ValueError:
            return None, None
    plus = _EXPERIENCE_PLUS_RE.search(haystack)
    if plus:
        try:
            return int(plus.group(1)), None
        except ValueError:
            return None, None
    return None, None


_EMPLOYMENT_PATTERNS = [
    (re.compile(r"\bfull[- ]time\b", re.IGNORECASE), "full_time"),
    (re.compile(r"\bpart[- ]time\b", re.IGNORECASE), "part_time"),
    (re.compile(r"\bcontract(?:or)?\b", re.IGNORECASE), "contract"),
    (re.compile(r"\binternship\b|\bintern\b", re.IGNORECASE), "internship"),
    (re.compile(r"\bfreelance\b", re.IGNORECASE), "freelance"),
    (re.compile(r"\btemporary\b|\btemp\b", re.IGNORECASE), "temporary"),
]


def detect_employment_type(*texts: str | None) -> str | None:
    haystack = " ".join(t for t in texts if t)
    for pattern, label in _EMPLOYMENT_PATTERNS:
        if pattern.search(haystack):
            return label
    return None


_SENIORITY_PATTERNS = [
    (re.compile(r"\b(intern(?:ship)?|trainee)\b", re.IGNORECASE), "intern"),
    (re.compile(r"\b(entry[- ]level|junior|jr\.?)\b", re.IGNORECASE), "junior"),
    (re.compile(r"\b(senior|sr\.?)\b", re.IGNORECASE), "senior"),
    (re.compile(r"\b(staff)\b", re.IGNORECASE), "staff"),
    (re.compile(r"\b(principal)\b", re.IGNORECASE), "principal"),
    (re.compile(r"\b(lead|tech lead)\b", re.IGNORECASE), "lead"),
    (re.compile(r"\b(manager|director|head|vp|chief)\b", re.IGNORECASE), "manager"),
    (re.compile(r"\b(mid[- ]level|mid)\b", re.IGNORECASE), "mid"),
]


def detect_seniority(*texts: str | None) -> str | None:
    haystack = " ".join(t for t in texts if t)
    if not haystack:
        return None
    for pattern, label in _SENIORITY_PATTERNS:
        if pattern.search(haystack):
            return label
    return None


# ── Validation ───────────────────────────────────────────────────────────


def validate_normalized_job(job: NormalizedJob) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if not job.title or not job.title.strip():
        reasons.append("missing_title")
    if not job.company_name or not job.company_name.strip():
        reasons.append("missing_company")
    if not job.source_url or not job.source_url.strip():
        reasons.append("missing_source_url")
    return (len(reasons) == 0), reasons


# ── Main entry point ─────────────────────────────────────────────────────


def normalize_one(raw: dict[str, Any]) -> NormalizedJob:
    """Convert a single raw job dict into a `NormalizedJob`.

    Accepts both the canonical adapter shape and the raw scraper shape so
    the normalizer is usable on its own (e.g. in tests).
    """
    title = (raw.get("title") or raw.get("job_title") or "").strip()
    company = (raw.get("company_name") or raw.get("company") or "").strip()
    source_platform = (raw.get("source_platform") or "linkedin").strip().lower()
    source_url = _clean_url(raw.get("source_url") or raw.get("job_url") or raw.get("url"))
    description = _clean_text(raw.get("description") or raw.get("job_description"))
    summary_in = _clean_text(raw.get("summary"))
    location = (raw.get("location_text") or raw.get("location") or raw.get("job_location") or "").strip() or None

    workplace = detect_workplace_type(title, location, description)
    employment = detect_employment_type(title, description)
    seniority = detect_seniority(title, description)
    min_y, max_y = detect_experience_range(title, description, raw.get("requirements"))

    # Bullets — accept either pre-split lists or free text
    requirements_in = raw.get("requirements")
    responsibilities_in = raw.get("responsibilities")

    requirements: list[str] = []
    if isinstance(requirements_in, list):
        requirements = [
            r.strip() for r in requirements_in if isinstance(r, str) and r.strip()
        ]
    elif isinstance(requirements_in, str):
        requirements = _split_bullets(requirements_in)

    responsibilities: list[str] = []
    if isinstance(responsibilities_in, list):
        responsibilities = [
            r.strip() for r in responsibilities_in if isinstance(r, str) and r.strip()
        ]
    elif isinstance(responsibilities_in, str):
        responsibilities = _split_bullets(responsibilities_in)

    # Skills — prefer scraper-provided list; fall back to deterministic extraction
    raw_required = raw.get("required_skills") or raw.get("skills") or []
    raw_preferred = raw.get("preferred_skills") or []
    if isinstance(raw_required, str):
        raw_required = re.split(r"[,;\n]", raw_required)
    if isinstance(raw_preferred, str):
        raw_preferred = re.split(r"[,;\n]", raw_preferred)

    required_skills = normalize_skill_list(raw_required)
    if not required_skills:
        required_skills = extract_skills_from_text(
            [title, summary_in, description, *requirements, *responsibilities],
        )
    preferred_skills = [
        s for s in normalize_skill_list(raw_preferred) if s not in required_skills
    ]

    # Salary heuristics (only attempt if numeric fields already provided)
    salary_min = _maybe_float(raw.get("salary_min"))
    salary_max = _maybe_float(raw.get("salary_max"))
    salary_currency = (raw.get("salary_currency") or "").strip() or None

    posted_at = _parse_datetime(raw.get("posted_at") or raw.get("posting_date"))
    scraped_at = _parse_datetime(raw.get("scraped_at")) or datetime.now(timezone.utc)

    return NormalizedJob(
        title=title,
        company_name=company,
        source_platform=source_platform,
        source_url=source_url or "",
        location_text=location,
        workplace_type=workplace,
        employment_type=employment,
        seniority_level=seniority,
        min_years_experience=min_y,
        max_years_experience=max_y,
        summary=summary_in,
        description=description,
        responsibilities=responsibilities,
        requirements=requirements,
        required_skills=required_skills,
        preferred_skills=preferred_skills,
        education_requirements=[],
        salary_min=salary_min,
        salary_max=salary_max,
        salary_currency=salary_currency,
        posted_at=posted_at,
        scraped_at=scraped_at,
        raw_payload=raw,
    )


def normalize_scraped_jobs(
    raw_jobs: Iterable[dict[str, Any]],
) -> tuple[list[NormalizedJob], list[RejectedJob]]:
    """Normalize a batch of raw scraped jobs.

    Returns (valid_jobs, rejected_jobs). Each rejected job carries its
    rejection reasons so they can be logged into `job_import_errors`.
    """
    valid: list[NormalizedJob] = []
    rejected: list[RejectedJob] = []
    for raw in raw_jobs:
        try:
            normalized = normalize_one(raw)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to normalize job: %s", exc)
            rejected.append(RejectedJob(raw=raw, reasons=[f"normalize_error:{exc}"]))
            continue
        ok, reasons = validate_normalized_job(normalized)
        if ok:
            valid.append(normalized)
        else:
            rejected.append(RejectedJob(raw=raw, reasons=reasons))
    return valid, rejected


# ── Tiny helpers ─────────────────────────────────────────────────────────


def _maybe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    if not text or text.lower() in {"n/a", "na"}:
        return None
    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            dt = datetime.strptime(text, fmt)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None
