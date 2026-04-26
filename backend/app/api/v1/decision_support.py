"""
Decision Support System (DSS) — full-journey explainable packet, HR HITL, plans, email drafts.

Base URL: /api/v1/decision-support
"""

from __future__ import annotations

import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.dependencies import get_current_active_user
from app.db.models import Job
from app.db.models.application import Application
from app.db.models.decision_support import (
    DecisionEmail,
    DecisionSupportPacket,
    DevelopmentPlan,
    HrFinalDecision,
)
from app.db.models.user import User
from app.db.models.candidate import Candidate
from app.schemas.decision_support import (
    DecisionSupportGenerateRequest,
    EmailPatchRequest,
    HrDecisionRequest,
)
import app.services.decision_support.decision_support_service as dss
from app.services.interview.interview_service import require_org_hr
from sqlalchemy import select

settings = get_settings()
router = APIRouter(prefix="/decision-support", tags=["Decision Support"])


def _pid(s: str) -> uuid.UUID:
    try:
        return uuid.UUID(s)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid UUID") from exc


def _org_for_application(db, app_id: uuid.UUID) -> uuid.UUID:
    app = db.get(Application, app_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    job = db.get(Job, app.job_id)
    if not job or not job.organization_id:
        raise HTTPException(status_code=400, detail="Job/organization not found")
    return job.organization_id


def _get_packet_for_org(
    db, packet_id: uuid.UUID, org_id: uuid.UUID,
) -> DecisionSupportPacket:
    p = db.get(DecisionSupportPacket, packet_id)
    if p is None or p.organization_id != org_id:
        raise HTTPException(status_code=404, detail="Packet not found")
    return p


@router.post("/generate", status_code=201)
def post_generate(
    body: DecisionSupportGenerateRequest,
    org_id: uuid.UUID = Query(..., description="Organization id (job must belong here)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if not settings.decision_support_enabled:
        raise HTTPException(status_code=503, detail="DSS disabled")
    app = db.get(Application, body.application_id)
    if not app or app.candidate_id != body.candidate_id or app.job_id != body.job_id:
        raise HTTPException(status_code=400, detail="Application/candidate/job mismatch")
    o = _org_for_application(db, body.application_id)
    if o != org_id:
        raise HTTPException(status_code=400, detail="organization_id mismatch")
    require_org_hr(db, current_user, org_id)
    try:
        p = dss.generate_decision_packet(
            db, application_id=body.application_id, actor_user_id=current_user.id,
        )
        db.commit()
        db.refresh(p)
        return {"packet_id": str(p.id), "recommendation": p.recommendation, "final_journey_score": p.final_journey_score}
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/applications/{application_id}/latest")
def get_latest_for_application(
    application_id: str,
    org_id: uuid.UUID = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Latest DSS packet for an application (see spec: GET .../applications/.../decision-support)."""
    require_org_hr(db, current_user, org_id)
    aid = _pid(application_id)
    if _org_for_application(db, aid) != org_id:
        raise HTTPException(status_code=400, detail="organization mismatch")
    p = dss.get_latest_packet_for_application(db, aid)
    if not p:
        raise HTTPException(status_code=404, detail="No decision packet")
    return {
        "packet_id": str(p.id),
        "final_journey_score": p.final_journey_score,
        "recommendation": p.recommendation,
        "packet_json": p.packet_json,
    }


@router.get("/{packet_id}")
def get_packet(
    packet_id: str,
    org_id: uuid.UUID = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    require_org_hr(db, current_user, org_id)
    p = _get_packet_for_org(db, _pid(packet_id), org_id)
    return {
        "id": str(p.id),
        "application_id": str(p.application_id),
        "final_journey_score": p.final_journey_score,
        "recommendation": p.recommendation,
        "confidence": p.confidence,
        "compliance_status": p.compliance_status,
        "packet_json": p.packet_json,
        "evidence_json": p.evidence_json,
        "human_review_required": p.human_review_required,
    }


@router.post("/{packet_id}/hr-decision", status_code=201)
def post_hr_decision(
    packet_id: str,
    body: HrDecisionRequest,
    org_id: uuid.UUID = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    require_org_hr(
        db, current_user, org_id,
        allowed_roles=("admin", "hr", "hiring_manager"),
    )
    p = _get_packet_for_org(db, _pid(packet_id), org_id)
    row = dss.record_hr_decision(
        db,
        packet=p,
        user_id=current_user.id,
        final_decision=body.final_decision,
        hr_notes=body.hr_notes,
        override_reason=body.override_reason,
    )
    db.commit()
    return {"id": str(row.id), "final_hr_decision": row.final_hr_decision}


@router.post("/{packet_id}/development-plan", status_code=201)
def post_dev_plan(
    packet_id: str,
    org_id: uuid.UUID = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    require_org_hr(db, current_user, org_id)
    p = _get_packet_for_org(db, _pid(packet_id), org_id)
    try:
        pl = dss.generate_development_plan_for_packet(
            db, packet=p, actor_user_id=current_user.id,
        )
        db.commit()
        db.refresh(pl)
        return {"id": str(pl.id), "plan_type": pl.plan_type, "plan_json": pl.plan_json}
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/{packet_id}/development-plan")
def get_dev_plan(
    packet_id: str,
    org_id: uuid.UUID = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    require_org_hr(db, current_user, org_id)
    p = _get_packet_for_org(db, _pid(packet_id), org_id)
    pl = db.execute(
        select(DevelopmentPlan)
        .where(DevelopmentPlan.decision_packet_id == p.id)
        .order_by(DevelopmentPlan.created_at.desc())
        .limit(1),
    ).scalar_one_or_none()
    if not pl:
        raise HTTPException(status_code=404, detail="No plan")
    return {"plan_json": pl.plan_json, "summary": pl.summary}


@router.post("/{packet_id}/generate-email", status_code=201)
def post_generate_email(
    packet_id: str,
    org_id: uuid.UUID = Query(...),
    email_type: str = Query(..., description="acceptance | rejection"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    require_org_hr(db, current_user, org_id)
    if email_type not in ("acceptance", "rejection"):
        raise HTTPException(status_code=400, detail="email_type must be acceptance or rejection")
    p = _get_packet_for_org(db, _pid(packet_id), org_id)
    try:
        e = dss.generate_decision_email(
            db, packet=p, email_type=email_type, actor_user_id=current_user.id,
        )
        db.commit()
        db.refresh(e)
        return {"email_id": str(e.id), "subject": e.subject, "body": e.body, "status": e.status}
    except ValueError as ex:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(ex)) from ex


@router.get("/{packet_id}/email")
def get_email(
    packet_id: str,
    org_id: uuid.UUID = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    require_org_hr(db, current_user, org_id)
    p = _get_packet_for_org(db, _pid(packet_id), org_id)
    e = db.execute(
        select(DecisionEmail)
        .where(DecisionEmail.decision_packet_id == p.id)
        .order_by(DecisionEmail.created_at.desc())
        .limit(1),
    ).scalar_one_or_none()
    if not e:
        raise HTTPException(status_code=404, detail="No email")
    return {
        "email_id": str(e.id),
        "email_type": e.email_type,
        "subject": e.subject,
        "body": e.body,
        "status": e.status,
    }


@router.patch("/{packet_id}/email")
def patch_email(
    packet_id: str,
    body: EmailPatchRequest,
    org_id: uuid.UUID = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    require_org_hr(db, current_user, org_id)
    p = _get_packet_for_org(db, _pid(packet_id), org_id)
    e = db.execute(
        select(DecisionEmail)
        .where(DecisionEmail.decision_packet_id == p.id)
        .order_by(DecisionEmail.created_at.desc())
        .limit(1),
    ).scalar_one_or_none()
    if not e:
        raise HTTPException(status_code=404, detail="No email")
    if body.subject is not None:
        e.subject = body.subject[:500]
    if body.body is not None:
        e.body = body.body
    db.commit()
    return {"ok": True}


@router.post("/{packet_id}/email/approve")
def post_email_approve(
    packet_id: str,
    org_id: uuid.UUID = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    require_org_hr(db, current_user, org_id)
    p = _get_packet_for_org(db, _pid(packet_id), org_id)
    e = db.execute(
        select(DecisionEmail)
        .where(DecisionEmail.decision_packet_id == p.id)
        .order_by(DecisionEmail.created_at.desc())
        .limit(1),
    ).scalar_one_or_none()
    if not e:
        raise HTTPException(status_code=404, detail="No email")
    e.status = "approved"
    e.approved_by_user_id = current_user.id
    db.commit()
    return {"ok": True}


@router.post("/{packet_id}/email/send")
def post_email_send(
    packet_id: str,
    org_id: uuid.UUID = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    require_org_hr(db, current_user, org_id)
    p = _get_packet_for_org(db, _pid(packet_id), org_id)
    e = db.execute(
        select(DecisionEmail)
        .where(DecisionEmail.decision_packet_id == p.id)
        .order_by(DecisionEmail.created_at.desc())
        .limit(1),
    ).scalar_one_or_none()
    if not e:
        raise HTTPException(status_code=404, detail="No email")
    c = db.get(Candidate, p.candidate_id)
    to = c.email if c else None
    if not to:
        raise HTTPException(status_code=400, detail="Candidate email missing")
    out = dss.send_decision_email_smtp(db, email_row=e, recipient_email=to)
    db.commit()
    if out.get("ok") != "true":
        raise HTTPException(status_code=502, detail=out.get("error", "send failed"))
    return {"ok": True}


@router.post("/{packet_id}/compliance-check")
def post_compliance(
    packet_id: str,
    org_id: uuid.UUID = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    require_org_hr(db, current_user, org_id)
    p = _get_packet_for_org(db, _pid(packet_id), org_id)
    r = dss.run_compliance_on_packet(db, packet=p)
    p.evidence_json = {**(p.evidence_json or {}), "compliance_recheck": r}
    p.compliance_status = (r.get("compliance_status") or "pass").lower()
    db.commit()
    return r
