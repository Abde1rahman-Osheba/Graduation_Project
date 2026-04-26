"""LLM nodes for summarization, HR/tech evaluation, compliance, and decision support."""

from __future__ import annotations

import json
import re
from typing import Any

from app.core.logging import get_logger
from app.services.organization_matching.organization_llm_provider import (
    LLMProviderError,
    get_provider,
)

logger = get_logger(__name__)


def _extract_json_object(text: str) -> dict[str, Any]:
    t = (text or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    try:
        out = json.loads(t)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}\s*$", t)
        if not m:
            raise ValueError("no JSON object in model output")
        out = json.loads(m.group(0))
    if not isinstance(out, dict):
        raise ValueError("model JSON was not an object")
    return out


async def llm_json(system: str, user: str) -> dict[str, Any]:
    prov = get_provider()
    try:
        text = await prov.generate_text(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.2,
        )
    except LLMProviderError as exc:
        logger.exception("LLM call failed: %s", exc)
        raise
    return _extract_json_object(text)


async def node_summarize(state: dict[str, Any]) -> dict[str, Any]:
    tr = (state.get("transcript") or "").strip()
    job = state.get("job_context") or {}
    cand = state.get("candidate_context") or {}
    packs = state.get("question_packs") or []
    system = (
        "You are a careful interview analyst. Do not invent facts. "
        "If the transcript lacks evidence, write exactly: 'Not enough evidence in transcript.' "
        "Return ONLY valid JSON with keys: short_summary, detailed_summary, key_answers, "
        "strengths_observed, weaknesses_observed, unclear_or_missing_points, job_requirement_alignment, "
        "candidate_cv_claims_verified, candidate_cv_claims_not_verified, important_quotes_or_answer_evidence."
    )
    user = json.dumps(
        {
            "job": job,
            "candidate": cand,
            "question_packs": packs,
            "transcript": tr[:80000],
        },
        default=str,
    )
    if len(tr) < 80:
        return {
            "interview_summary": {
                "short_summary": "Not enough evidence in transcript.",
                "detailed_summary": "Not enough evidence in transcript.",
                "strengths_observed": [],
                "weaknesses_observed": [],
                "unclear_or_missing_points": ["Transcript too short or empty."],
            }
        }
    out = await llm_json(system, user)
    return {"interview_summary": out}


async def node_hr_evaluation(state: dict[str, Any]) -> dict[str, Any]:
    summary = state.get("interview_summary") or {}
    system = (
        "You are an HR evaluator. Be fair, job-related, and avoid protected attributes. "
        "Output ONLY JSON: communication_score, motivation_score, culture_alignment_score, "
        "role_understanding_score, teamwork_score, ownership_score, adaptability_score, overall_hr_score, "
        "strengths, weaknesses, risks, development_needs, evidence, "
        "recommendation_from_hr_perspective (a short sentence — recommendation, not a hiring decision)"
    )
    user = json.dumps(
        {
            "summary": summary,
            "transcript": (state.get("transcript") or "")[:80000],
        },
        default=str,
    )
    out = await llm_json(system, user)
    return {"hr_scorecard": out}


async def node_technical_evaluation(state: dict[str, Any]) -> dict[str, Any]:
    job = state.get("job_context") or {}
    summary = state.get("interview_summary") or {}
    system = (
        "You are a technical evaluator. Map answers to job skills; compare to CV. "
        "Output ONLY JSON: skill_scores (object skill->1-5), strongest_skills, weakest_skills, "
        "verified_cv_claims, unverified_cv_claims, incorrect_or_weak_answers, "
        "practical_task_result_if_any, overall_technical_score, evidence, "
        "recommendation_from_technical_perspective"
    )
    user = json.dumps(
        {
            "job": job,
            "summary": summary,
            "transcript": (state.get("transcript") or "")[:80000],
        },
        default=str,
    )
    itype = (state.get("interview_type") or "mixed").lower()
    if itype == "hr":
        return {
            "technical_scorecard": {
                "skill_scores": {},
                "overall_technical_score": None,
                "strongest_skills": [],
                "weakest_skills": [],
                "evidence": "No technical interview in this event.",
            }
        }
    out = await llm_json(system, user)
    return {"technical_scorecard": out}


async def node_compliance(state: dict[str, Any]) -> dict[str, Any]:
    hr = state.get("hr_scorecard") or {}
    tech = state.get("technical_scorecard") or {}
    dp = {
        "hr_recommendation": (hr or {}).get("recommendation_from_hr_perspective", ""),
        "technical_recommendation": (tech or {}).get("recommendation_from_technical_perspective", ""),
    }
    system = (
        "You are a compliance guardrail. Detect biased or illegal interview patterns in TEXT outputs only. "
        "Output JSON: compliance_status (pass|warning|fail), detected_issues (list of strings), "
        "corrected_output (or null), audit_notes"
    )
    user = json.dumps({"artifacts": dp}, default=str)
    out = await llm_json(system, user)
    return {"compliance": out}


async def node_decision_support(state: dict[str, Any]) -> dict[str, Any]:
    hr = state.get("hr_scorecard") or {}
    tech = state.get("technical_scorecard") or {}
    comp = state.get("compliance") or {}
    jm = state.get("job_match_score")
    tq = state.get("transcript_quality") or "medium"
    itype = (state.get("interview_type") or "mixed").lower()

    def _f(v: Any, default: float = 0.0) -> float:
        try:
            return float(v)
        except (TypeError, ValueError):
            return default

    hr_s = _f(hr.get("overall_hr_score"), 0.0)
    tech_s = _f(tech.get("overall_technical_score"), 0.0) if itype != "hr" else 0.0
    match_s: float | None
    if jm is None:
        match_s = None
    else:
        jmf = _f(jm, 0.0)
        match_s = jmf * 100.0 if jmf <= 1.0 else jmf

    ev_conf = 0.7 if tq == "high" else 0.5 if tq == "medium" else 0.3

    if itype == "hr":
        w_match, w_tech, w_hr, w_ev = 0.5, 0.0, 0.4, 0.1
    elif itype == "technical":
        w_match, w_tech, w_hr, w_ev = 0.35, 0.45, 0.15, 0.05
    else:
        w_match, w_tech, w_hr, w_ev = 0.35, 0.30, 0.25, 0.10

    norm_hr = min(max(hr_s, 0.0), 100.0) / 100.0
    norm_tech = min(max(tech_s, 0.0), 100.0) / 100.0 if itype != "hr" else 0.0
    norm_match = (
        min(max(match_s, 0.0), 100.0) / 100.0
        if match_s is not None
        else 0.0
    )

    final_score_100 = (
        w_match * norm_match * 100.0
        + w_tech * norm_tech * 100.0
        + w_hr * norm_hr * 100.0
        + w_ev * ev_conf * 100.0
    )

    system = (
        "You are a decision-support assistant for HR. Never make autonomous hiring decisions. "
        "The final hire/no-hire is always with HR. "
        "Return ONLY JSON: overall_recommendation, confidence, main_strengths, main_weaknesses, risk_flags, "
        "missing_information, evidence_summary (list of {claim, evidence}), suggested_next_step, "
        "suggested_growth_plan_if_rejected, human_review_required (always true). "
        "overall_recommendation must be one of: "
        "Accept, Reject, Hold, Needs another technical interview, Needs another HR interview, "
        "Needs manager review, Needs another interview"
    )
    user = json.dumps(
        {
            "hr": hr,
            "technical": tech,
            "compliance": comp,
            "computed_final_score": final_score_100,
            "interview_type": itype,
        },
        default=str,
    )
    out = await llm_json(system, user)
    out["final_score"] = final_score_100
    out["hr_score"] = hr_s
    out["technical_score"] = tech_s
    out["job_match_score"] = round(match_s, 2) if match_s is not None else None
    out["human_review_required"] = True
    cstatus = (comp.get("compliance_status") or "pass").lower()
    if cstatus == "fail":
        out["overall_recommendation"] = "Hold"
        out["suggested_next_step"] = "Compliance review required before proceeding."
    return {"decision_packet": out}
