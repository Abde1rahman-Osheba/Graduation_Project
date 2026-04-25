"""
Generate, approve, and optionally send outreach emails (SMTP) for organization runs.
"""

from __future__ import annotations

import asyncio
import json
import smtplib
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
import re
from typing import Any, AsyncIterator
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models.organization_matching import OrganizationCandidateRanking
from app.db.repositories import organization_matching_repo as om_repo
from app.services.organization_matching.organization_llm_provider import get_provider
from app.services.organization_matching.organization_outreach_prompt_builder import (
    build_outreach_messages,
)
from app.db.repositories import scoring_repository as srepo
from app.services.scoring.scoring_prompt_builder import anonymize_candidate

settings = get_settings()


def _json_subject_body(text: str) -> dict[str, str] | None:
    t = (text or "").strip()
    if not t:
        return None
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    try:
        o = json.loads(t)
    except json.JSONDecodeError:
        return None
    if isinstance(o, dict) and "subject" in o and "body" in o:
        return {"subject": str(o["subject"]), "body": str(o["body"])}
    return None


def generate_draft(
    db: Session,
    *,
    organization_id: UUID,
    matching_run_id: UUID,
    ranking: OrganizationCandidateRanking,
    booking_link: str | None = None,
    deadline_days: int | None = None,
) -> Any:
    days = int(deadline_days or settings.outreach_reply_deadline_days)
    link = (booking_link or settings.outreach_default_booking_link or "").strip()
    if not link:
        raise ValueError("booking_link required (or set OUTREACH_DEFAULT_BOOKING_LINK)")

    oprof = om_repo.get_org_profile(db, organization_id) or {"name": "Organization"}
    jtitle = om_repo.get_job_title(db, ranking.job_id) or "Open role"
    cprof = srepo.get_candidate_profile(db, ranking.candidate_id)
    evidence = (
        anonymize_candidate(cprof, candidate_id="candidate")
        if cprof
        else {"summary": "Profile unavailable"}
    )
    prof_summary = f'{evidence.get("headline") or ""} {evidence.get("summary") or ""}'

    messages = build_outreach_messages(
        organization_profile=oprof,
        job_title=jtitle,
        job_profile_summary=prof_summary,
        candidate_evidence=evidence,
        matched_strengths=ranking.strengths or [],
        booking_link=link,
        deadline_days=days,
    )
    prov = get_provider()

    async def _call() -> str:
        return await prov.generate_text(messages)

    out = _json_subject_body(asyncio.run(_call()))
    if not out:
        out = {
            "subject": f"Opportunity: {jtitle} at {oprof.get('name', 'our team')}",
            "body": (
                f"We would like to invite you to discuss the {jtitle} role.\n\n"
                f"Please book a time within {days} days: {link}\n"
            ),
        }
    deadline = datetime.now(timezone.utc) + timedelta(days=days)
    m = om_repo.create_outreach_message(
        db,
        {
            "organization_id": organization_id,
            "matching_run_id": matching_run_id,
            "ranking_id": ranking.id,
            "job_id": ranking.job_id,
            "candidate_id": ranking.candidate_id,
            "blind_candidate_id": ranking.blind_candidate_id,
            "recipient_email": None,
            "subject": out["subject"],
            "body": out["body"],
            "booking_link": link,
            "reply_deadline_at": deadline,
            "status": "draft" if settings.outreach_require_approval else "pending_approval",
        },
    )
    db.commit()
    return m


def build_stream_messages(
    db: Session,
    *,
    organization_id: UUID,
    ranking: OrganizationCandidateRanking,
    booking_link: str | None,
    deadline_days: int,
) -> list[dict[str, str]]:
    link = (booking_link or settings.outreach_default_booking_link or "").strip() or "https://example.invalid"
    oprof = om_repo.get_org_profile(db, organization_id) or {"name": "Organization"}
    jtitle = om_repo.get_job_title(db, ranking.job_id) or "Open role"
    cprof = srepo.get_candidate_profile(db, ranking.candidate_id)
    evidence = (
        anonymize_candidate(cprof, candidate_id="candidate")
        if cprof
        else {"summary": "Profile unavailable"}
    )
    prof_summary = f'{evidence.get("headline") or ""} {evidence.get("summary") or ""}'
    return build_outreach_messages(
        organization_profile=oprof,
        job_title=jtitle,
        job_profile_summary=prof_summary,
        candidate_evidence=evidence,
        matched_strengths=ranking.strengths or [],
        booking_link=link,
        deadline_days=deadline_days,
    )


async def stream_email_tokens(
    messages: list[dict[str, str]],
) -> AsyncIterator[str]:
    prov = get_provider()
    async for chunk in prov.stream_text(messages):  # type: ignore[union-attr]
        if chunk:
            yield chunk


def save_streamed_draft(
    db: Session,
    *,
    organization_id: UUID,
    matching_run_id: UUID,
    ranking: OrganizationCandidateRanking,
    full_text: str,
    booking_link: str | None,
    deadline_days: int,
) -> Any:
    link = (booking_link or settings.outreach_default_booking_link or "").strip() or None
    out = _json_subject_body(full_text) or {
        "subject": "Message",
        "body": full_text,
    }
    days = int(deadline_days or settings.outreach_reply_deadline_days)
    deadline = datetime.now(timezone.utc) + timedelta(days=days)
    m = om_repo.create_outreach_message(
        db,
        {
            "organization_id": organization_id,
            "matching_run_id": matching_run_id,
            "ranking_id": ranking.id,
            "job_id": ranking.job_id,
            "candidate_id": ranking.candidate_id,
            "blind_candidate_id": ranking.blind_candidate_id,
            "recipient_email": None,
            "subject": out["subject"][:500],
            "body": out["body"],
            "booking_link": link,
            "reply_deadline_at": deadline,
            "status": "draft",
        },
    )
    db.commit()
    return m


def send_approved_smtp(
    db: Session,
    *,
    message_id: UUID,
    recipient_email: str,
) -> dict[str, Any]:
    m = om_repo.get_outreach_message(db, message_id)
    if m is None:
        return {"ok": False, "error": "message_not_found"}
    if settings.outreach_require_approval and m.status != "approved":
        return {"ok": False, "error": "not_approved"}
    if not settings.smtp_host or not settings.smtp_username:
        return {"ok": False, "error": "smtp_not_configured"}

    msg = MIMEText(m.body, "plain", "utf-8")
    msg["Subject"] = m.subject
    msg["From"] = settings.outreach_from_email or settings.smtp_username
    msg["To"] = recipient_email
    try:
        with smtplib.SMTP(
            settings.smtp_host, int(settings.smtp_port),
        ) as smtp:
            if settings.smtp_use_tls:
                smtp.starttls()
            if settings.smtp_password:
                smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(msg)
        om_repo.update_outreach_message_status(
            db, message_id, status="sent", sent_at=datetime.now(timezone.utc), provider="smtp",
        )
        db.commit()
        return {"ok": True}
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        om_repo.update_outreach_message_status(
            db, message_id, status="failed", error_message=str(exc)[:500],
        )
        db.commit()
        return {"ok": False, "error": "send_failed"}


def approve_deanonymize_for_outreach(
    db: Session,
    *,
    matching_run_id: UUID,
    candidate_id: UUID,
    approved_by: UUID | None,
) -> None:
    b = om_repo.get_blind_candidate_map(db, matching_run_id, candidate_id)
    if b:
        b.de_anonymized = True
        b.de_anonymized_at = datetime.now(timezone.utc)
        if approved_by is not None:
            b.de_anonymized_by = approved_by
    db.commit()
