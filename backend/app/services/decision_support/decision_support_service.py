"""Orchestration: build DSS packet, HR decision, development plan, emails."""

from __future__ import annotations

import smtplib
import uuid
from datetime import datetime, timezone
from email.mime.text import MIMEText
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Job
from app.db.models.application import Application
from app.db.models.candidate import Candidate
from app.db.models.decision_support import (
    DecisionEmail,
    DecisionScoreBreakdown,
    DecisionSupportPacket,
    DevelopmentPlan,
    HrFinalDecision,
)
from app.services.decision_support.dss_agents import (
    run_compliance_agent,
    run_decision_email_agent,
    run_decision_support_agent,
    run_development_planner_agent,
)
from app.services.decision_support.dss_audit import log_dss
from app.services.decision_support.dss_context import load_journey_context
from app.services.decision_support.scoring_aggregation_service import ScoreInputs, compute_journey_score
from app.services.llm.openrouter_client import OpenRouterClientError

settings = get_settings()


def _f(x: Any) -> float | None:
    if x is None:
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _interview_scores(blocks: list[dict[str, Any]]) -> tuple[float | None, float | None]:
    hr_all: list[float] = []
    tech_all: list[float] = []
    for b in blocks:
        for e in b.get("evaluations") or []:
            sj = e.get("score_json") or {}
            if e.get("type") == "hr":
                v = _f(sj.get("overall_hr_score"))
                if v is not None:
                    hr_all.append(v if v > 1 else v * 100)
            if e.get("type") == "technical":
                v = _f(sj.get("overall_technical_score"))
                if v is not None:
                    tech_all.append(v if v > 1 else v * 100)
    def _avg(xs: list[float]) -> float | None:
        if not xs:
            return None
        return sum(xs) / len(xs)
    return _avg(hr_all), _avg(tech_all)


def build_score_inputs(ctx: dict[str, Any]) -> ScoreInputs:
    cjs = ctx.get("candidate_job_score") or {}
    match = _f(cjs.get("final_score"))
    hr_s, tech_s = _interview_scores(ctx.get("interviews") or [])
    exp = None
    cb = cjs.get("criteria_breakdown") or {}
    if isinstance(cb, dict) and cb:
        exp = _f(cb.get("experience")) or _f((cb.get("experience") or {}).get("score"))
    if exp is None and match is not None:
        exp = match * 0.85
    return ScoreInputs(
        candidate_job_match_score=match,
        assessment_score=None,
        technical_interview_score=tech_s,
        hr_interview_score=hr_s,
        experience_alignment_score=exp,
        evidence_confidence_score=None,
        transcript_quality=ctx.get("transcript_quality"),
    )


def generate_decision_packet(
    db: Session,
    *,
    application_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
) -> DecisionSupportPacket:
    if not settings.decision_support_enabled:
        raise ValueError("decision support disabled")
    ctx = load_journey_context(db, application_id=application_id)
    app = db.get(Application, application_id)
    if not app or not app.job_id:
        raise ValueError("invalid application")
    job = db.get(Job, app.job_id)
    if not job or not job.organization_id:
        raise ValueError("job or organization missing")

    sin = build_score_inputs(ctx)
    final_score, expl = compute_journey_score(sin)

    try:
        raw = run_decision_support_agent(
            context=ctx,
            computed_journey_score=final_score,
            score_explanation=expl,
        )
    except OpenRouterClientError as exc:
        raise ValueError(str(exc)) from exc

    raw["score_breakdown"] = raw.get("score_breakdown") or {}
    raw["score_breakdown"]["final_journey_score"] = final_score

    comp = run_compliance_agent(content=raw, content_type="decision_packet")
    cstat = (comp.get("compliance_status") or "pass").lower()
    if cstat == "fail":
        raw["recommendation"] = "hold"
        raw["suggested_next_step"] = "Compliance review required before accepting any recommendation."

    packet = DecisionSupportPacket(
        id=uuid.uuid4(),
        organization_id=job.organization_id,
        job_id=app.job_id,
        candidate_id=app.candidate_id,
        application_id=application_id,
        generated_by_agent="decision_support_agent",
        model_provider="openrouter",
        model_name=settings.openrouter_dss_model,
        final_journey_score=final_score,
        recommendation=str(raw.get("recommendation", "hold")),
        confidence=float(raw.get("confidence") or 0.5),
        packet_json=raw,
        evidence_json={"engine": expl, "compliance": comp},
        compliance_status=cstat,
        human_review_required=True,
    )

    db.add(packet)
    db.add(
        DecisionScoreBreakdown(
            id=uuid.uuid4(),
            decision_packet_id=packet.id,
            candidate_job_match_score=sin.candidate_job_match_score,
            assessment_score=sin.assessment_score,
            technical_interview_score=sin.technical_interview_score,
            hr_interview_score=sin.hr_interview_score,
            experience_alignment_score=sin.experience_alignment_score,
            evidence_confidence_score=sin.evidence_confidence_score,
            final_journey_score=final_score,
            scoring_formula_version="v1",
            explanation_json=expl,
        ),
    )
    log_dss(
        db,
        actor_user_id=actor_user_id,
        action="dss.packet_generated",
        entity_id=packet.id,
        new_value={"recommendation": packet.recommendation},
    )
    return packet


def get_latest_packet_for_application(
    db: Session, application_id: uuid.UUID,
) -> DecisionSupportPacket | None:
    return db.execute(
        select(DecisionSupportPacket)
        .where(DecisionSupportPacket.application_id == application_id)
        .order_by(DecisionSupportPacket.created_at.desc())
        .limit(1),
    ).scalar_one_or_none()


def record_hr_decision(
    db: Session,
    *,
    packet: DecisionSupportPacket,
    user_id: uuid.UUID,
    final_decision: str,
    hr_notes: str | None,
    override_reason: str | None,
) -> HrFinalDecision:
    row = HrFinalDecision(
        id=uuid.uuid4(),
        decision_packet_id=packet.id,
        organization_id=packet.organization_id,
        job_id=packet.job_id,
        candidate_id=packet.candidate_id,
        application_id=packet.application_id,
        decided_by_user_id=user_id,
        ai_recommendation=packet.recommendation,
        final_hr_decision=final_decision,
        override_reason=override_reason,
        hr_notes=hr_notes,
    )
    db.add(row)
    log_dss(
        db,
        actor_user_id=user_id,
        action="dss.hr_final_decision",
        entity_id=packet.id,
        new_value={"final": final_decision, "override": override_reason},
    )
    return row


def generate_development_plan_for_packet(
    db: Session,
    *,
    packet: DecisionSupportPacket,
    actor_user_id: uuid.UUID | None,
) -> DevelopmentPlan:
    hr = db.execute(
        select(HrFinalDecision)
        .where(HrFinalDecision.decision_packet_id == packet.id)
        .order_by(HrFinalDecision.decided_at.desc())
        .limit(1),
    ).scalar_one_or_none()
    if hr is None:
        raise ValueError("HR decision required before development plan")
    fd = hr.final_hr_decision.lower().strip()
    if fd in ("accepted", "accept"):
        ptype = "accepted_internal_growth"
    elif fd in ("rejected", "reject"):
        ptype = "rejected_improvement_plan"
    else:
        raise ValueError("Development plan only after accept or reject")

    ctx = load_journey_context(db, application_id=packet.application_id)
    try:
        plan = run_development_planner_agent(
            plan_type=ptype,
            context=ctx,
            packet_summary=packet.packet_json,
        )
    except OpenRouterClientError as exc:
        raise ValueError(str(exc)) from exc

    comp = run_compliance_agent(content=plan, content_type="development_plan")
    if (comp.get("compliance_status") or "").lower() == "fail":
        plan["compliance_note"] = "Review required"

    row = DevelopmentPlan(
        id=uuid.uuid4(),
        decision_packet_id=packet.id,
        organization_id=packet.organization_id,
        job_id=packet.job_id,
        candidate_id=packet.candidate_id,
        application_id=packet.application_id,
        plan_type=ptype,
        generated_by_agent="development_planner_agent",
        model_provider="openrouter",
        model_name=settings.openrouter_development_model,
        plan_json=plan,
        summary=str(plan.get("summary", ""))[:2000],
    )
    db.add(row)
    log_dss(db, actor_user_id=actor_user_id, action="dss.development_plan", entity_id=packet.id, new_value={})
    return row


def generate_decision_email(
    db: Session,
    *,
    packet: DecisionSupportPacket,
    email_type: str,
    actor_user_id: uuid.UUID | None,
) -> DecisionEmail:
    hr = db.execute(
        select(HrFinalDecision)
        .where(HrFinalDecision.decision_packet_id == packet.id)
        .order_by(HrFinalDecision.decided_at.desc())
        .limit(1),
    ).scalar_one_or_none()
    if hr is None:
        raise ValueError("HR decision required first")
    ctx = load_journey_context(db, application_id=packet.application_id)
    try:
        out = run_decision_email_agent(
            email_type=email_type,
            context=ctx,
            hr_decision=hr.final_hr_decision,
            packet=packet.packet_json,
        )
    except OpenRouterClientError as exc:
        raise ValueError(str(exc)) from exc
    subj = str(out.get("subject", "Update on your application"))[:500]
    body = str(out.get("body", ""))
    row = DecisionEmail(
        id=uuid.uuid4(),
        decision_packet_id=packet.id,
        organization_id=packet.organization_id,
        candidate_id=packet.candidate_id,
        job_id=packet.job_id,
        application_id=packet.application_id,
        email_type=email_type,
        subject=subj,
        body=body,
        generated_by_agent="decision_email_agent",
        status="draft",
    )
    db.add(row)
    log_dss(db, actor_user_id=actor_user_id, action="dss.email_draft", entity_id=packet.id, new_value={"type": email_type})
    return row


def run_compliance_on_packet(
    db: Session,
    *,
    packet: DecisionSupportPacket,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"packet": packet.packet_json, "extra": extra or {}}
    return run_compliance_agent(content=payload, content_type="full_review")


def send_decision_email_smtp(
    db: Session,
    *,
    email_row: DecisionEmail,
    recipient_email: str,
) -> dict[str, str]:
    if email_row.status != "approved":
        return {"ok": "false", "error": "not_approved"}
    if not settings.smtp_host or not settings.smtp_username:
        return {"ok": "false", "error": "smtp_not_configured"}
    msg = MIMEText(email_row.body, "plain", "utf-8")
    msg["Subject"] = email_row.subject
    msg["From"] = settings.outreach_from_email or settings.smtp_username
    msg["To"] = recipient_email
    try:
        with smtplib.SMTP(settings.smtp_host, int(settings.smtp_port)) as smtp:
            if settings.smtp_use_tls:
                smtp.starttls()
            if settings.smtp_password:
                smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(msg)
        email_row.status = "sent"
        email_row.sent_at = datetime.now(timezone.utc)
        log_dss(
            db, actor_user_id=None, action="dss.email_sent", entity_id=email_row.decision_packet_id, new_value={},
        )
        return {"ok": "true"}
    except Exception as exc:  # noqa: BLE001
        email_row.status = "failed"
        return {"ok": "false", "error": str(exc)[:500]}
