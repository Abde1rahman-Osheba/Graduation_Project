"""
Journey score aggregation (DECISION_SUPPORT_SYSTEM spec).

Base weights: match 0.30, assessment 0.20, technical 0.20, hr 0.15,
experience 0.10, evidence 0.05. Missing components: weight goes mainly to
match and existing interview/match terms (no invented scores).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ScoreInputs:
    candidate_job_match_score: float | None
    assessment_score: float | None
    technical_interview_score: float | None
    hr_interview_score: float | None
    experience_alignment_score: float | None
    evidence_confidence_score: float | None
    transcript_quality: str | None


def _n100(x: float | None) -> float:
    if x is None:
        return 0.0
    return x * 100.0 if x <= 1.0 else min(max(x, 0.0), 100.0)


def compute_journey_score(inp: ScoreInputs) -> tuple[float, dict[str, Any]]:
    tq = (inp.transcript_quality or "medium").lower()
    if tq == "low":
        ev = 0.35
    elif tq == "high":
        ev = 0.90
    else:
        ev = 0.65
    if inp.evidence_confidence_score is not None:
        ev = (ev + _n100(inp.evidence_confidence_score) / 100.0) / 2.0

    m = _n100(inp.candidate_job_match_score)
    a = _n100(inp.assessment_score) if inp.assessment_score is not None else None
    t = _n100(inp.technical_interview_score) if inp.technical_interview_score is not None else None
    h = _n100(inp.hr_interview_score) if inp.hr_interview_score is not None else None
    e = _n100(inp.experience_alignment_score) if inp.experience_alignment_score is not None else None

    wM, wA, wT, wH, wE, wV = 0.30, 0.20, 0.20, 0.15, 0.10, 0.05
    if a is None:
        wM += 0.10
        wT += 0.05
        wH += 0.05
        wA = 0.0
    if t is None:
        wM += 0.10
        wH += 0.05
        wE += 0.05
        wT = 0.0
    if h is None:
        wM += 0.09
        wT += 0.03
        wE += 0.03
        wH = 0.0
    if e is None:
        wM += 0.07
        wT += 0.02
        wH += 0.01
        wE = 0.0

    s = wM + wA + wT + wH + wE + wV
    wM, wA, wT, wH, wE, wV = wM / s, wA / s, wT / s, wH / s, wE / s, wV / s

    final = (
        wM * m
        + (wA * a if a is not None else 0.0)
        + (wT * t if t is not None else 0.0)
        + (wH * h if h is not None else 0.0)
        + (wE * e if e is not None else 0.0)
        + wV * ev * 100.0
    )
    expl: dict[str, Any] = {
        "weights": {
            "match": wM,
            "assessment": wA,
            "technical": wT,
            "hr": wH,
            "experience": wE,
            "evidence": wV,
        },
        "components_0_100": {
            "match": m,
            "assessment": a,
            "technical": t,
            "hr": h,
            "experience": e,
            "evidence_confidence_0_1": ev,
        },
    }
    return round(final, 3), expl
