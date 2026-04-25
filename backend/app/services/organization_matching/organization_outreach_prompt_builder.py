"""
PATHS outreach email — job-relevant, no protected attributes, no AI-score disclosure.
"""

from __future__ import annotations

import json
from typing import Any


def build_outreach_messages(
    *,
    organization_profile: dict[str, Any],
    job_title: str,
    job_profile_summary: str,
    candidate_evidence: dict[str, Any],
    matched_strengths: list[str] | None,
    booking_link: str,
    deadline_days: int,
) -> list[dict[str, str]]:
    org_name = (organization_profile or {}).get("name") or "our organization"
    ms = "\n".join(f"- {s}" for s in (matched_strengths or [])[:8])
    ev = json.dumps(candidate_evidence, ensure_ascii=False)[:6000]
    user = f"""You are PATHS Outreach Agent.

Return ONLY valid JSON with keys "subject" and "body". No code fences, no extra keys.

Write a professional recruitment email. Rules:
- Do not mention protected attributes, AI scoring, or internal rankings.
- Use only the evidence provided.
- Include job title, organization name, 2-3 clear fit reasons, booking link, and ask to schedule within {deadline_days} days.

Organization: {org_name}
Job title: {job_title}
Job context: {job_profile_summary[:2000]}

Job-relevant candidate evidence (may omit name):
{ev}

Fit highlights:
{ms}

Booking link: {booking_link}
Deadline: reply or book within {deadline_days} calendar days.
"""
    return [
        {
            "role": "system",
            "content": "You return only a JSON object with string fields subject and body.",
        },
        {"role": "user", "content": user},
    ]
