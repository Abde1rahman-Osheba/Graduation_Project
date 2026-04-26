"""LLM agents for DSS: decision packet, development plan, compliance, email drafts."""

from __future__ import annotations

import json
from typing import Any

from app.core.config import get_settings
from app.services.llm.openrouter_client import OpenRouterClientError, generate_json_response

settings = get_settings()

DSS_SCHEMA_HINT = """
Return ONLY a JSON object with these keys (fill all string/list/object fields; use null where unknown):
{
  "executive_summary": "",
  "candidate_journey_summary": "",
  "score_breakdown": {
    "candidate_job_match_score": 0, "assessment_score": null,
    "technical_interview_score": null, "hr_interview_score": null,
    "experience_alignment_score": 0, "evidence_confidence_score": 0, "final_journey_score": 0
  },
  "advantages": [{"point": "", "evidence": "", "source": ""}],
  "disadvantages": [{"point": "", "evidence": "", "source": ""}],
  "risks": [{"risk": "", "severity": "low", "evidence": ""}],
  "verified_claims": [],
  "unverified_claims": [],
  "missing_information": [],
  "recommendation": "accept",
  "confidence": 0.5,
  "recommendation_reason": "",
  "suggested_next_step": "",
  "development_direction_preview": "",
  "human_review_required": true
}
recommendation must be one of: accept, reject, hold, another_hr_interview, another_technical_interview, manager_review
"""


def run_decision_support_agent(
    *,
    context: dict[str, Any],
    computed_journey_score: float,
    score_explanation: dict[str, Any],
) -> dict[str, Any]:
    system = (
        "You are the PATHS Decision Support Agent. You only RECOMMEND — HR decides. "
        "Never invent interview results or scores; use the numbers provided. "
        "If data is missing, say 'Not enough evidence available.' "
        "Separate evidence from inference. Output valid JSON only. " + DSS_SCHEMA_HINT
    )
    user = json.dumps(
        {
            "journey_context": context,
            "precomputed_journey_score": computed_journey_score,
            "score_engine_explanation": score_explanation,
        },
        default=str,
    )[:120000]
    return generate_json_response(
        system, user, model=settings.openrouter_dss_model, temperature=0.15, max_tokens=4500,
    )


def run_compliance_agent(*, content: dict[str, Any], content_type: str) -> dict[str, Any]:
    system = (
        "You are a hiring compliance guardrail. Check for bias, protected attributes, "
        "unsupported claims. Output JSON: "
        "compliance_status (pass|warning|fail), issues_found (list), "
        "corrected_output (object or null), audit_notes (string)"
    )
    user = json.dumps({"type": content_type, "content": content}, default=str)[:80000]
    return generate_json_response(
        system, user, model=settings.openrouter_dss_model, temperature=0.1, max_tokens=2000,
    )


def run_development_planner_agent(
    *,
    plan_type: str,
    context: dict[str, Any],
    packet_summary: dict[str, Any],
) -> dict[str, Any]:
    system = (
        "You are the Development Planner. Produce respectful, job-related plans. "
        "Output JSON with: plan_type, summary, strengths_to_build_on, gaps_to_improve, "
        "timeline { first_30_days, first_60_days, first_90_days, six_months, twelve_months } as lists, "
        "technical_skills, soft_skills, recommended_projects, recommended_resources, "
        "milestones, kpis, manager_or_candidate_checkpoints. "
        "For rejected candidates, be constructive; never insult or reference protected attributes."
    )
    user = json.dumps(
        {"plan_type": plan_type, "hiring_context": context, "decision_artifacts": packet_summary},
        default=str,
    )[:100000]
    return generate_json_response(
        system, user, model=settings.openrouter_development_model, temperature=0.2, max_tokens=4500,
    )


def run_decision_email_agent(
    *,
    email_type: str,
    context: dict[str, Any],
    hr_decision: str,
    packet: dict[str, Any],
) -> dict[str, Any]:
    tone = 0.45 if email_type == "rejection" else 0.4
    system = (
        "Generate a professional email subject and body. Output JSON: "
        "email_type, subject, body, personalization_used (list of strings), requires_hr_approval (true). "
        "Do not include protected attributes. Keep rejection legally safe and brief."
    )
    user = json.dumps(
        {
            "email_type": email_type,
            "hr_decision": hr_decision,
            "candidate": context.get("candidate"),
            "job": context.get("job"),
            "organization": context.get("organization"),
            "highlights": packet,
        },
        default=str,
    )[:50000]
    return generate_json_response(
        system, user, model=settings.openrouter_outreach_model, temperature=tone, max_tokens=2500,
    )


__all__ = [
    "run_compliance_agent",
    "run_decision_email_agent",
    "run_decision_support_agent",
    "run_development_planner_agent",
]
