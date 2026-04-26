"""
Interview intelligence API (PATHS extension).

Mounted at ``/api/v1/interviews``. AI outputs are recommendations only;
final hiring decisions require an HR user via ``human-decision``.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.dependencies import get_current_active_user
from app.db.models.interview import (
    Interview,
    InterviewDecisionPacket,
    InterviewEvaluation,
    InterviewHumanDecision,
    InterviewQuestionPack,
    InterviewSummary,
    InterviewTranscript,
)
from app.db.models.user import User
from app.schemas.interview import (
    ApproveInterviewQuestionsRequest,
    GenerateInterviewQuestionsRequest,
    InterviewAnalyzeResponse,
    InterviewAvailabilityRequest,
    InterviewAvailabilityResponse,
    InterviewCancelRequest,
    InterviewCreateStub,
    InterviewDecisionPacketOut,
    InterviewEvaluationOut,
    InterviewHumanDecisionOut,
    InterviewHumanDecisionRequest,
    InterviewRescheduleRequest,
    InterviewScheduleRequest,
    InterviewScheduleResponse,
    InterviewSummaryOut,
    InterviewTranscriptCreate,
    TimeSlotOut,
)
from app.services.interview.interview_audit import log_interview_action
from app.services.interview.availability import list_availability
from app.services.interview.interview_service import (
    assert_application_in_org,
    candidate_owns_application,
    generate_question_packs,
    get_interview_for_org,
    require_org_hr,
    run_full_analysis,
    schedule_interview,
)
from app.services.interview.meeting_providers import get_meeting_provider

settings = get_settings()
router = APIRouter(prefix="/interviews", tags=["Interviews"])


def _parse_uuid(s: str, name: str = "id") -> uuid.UUID:
    try:
        return uuid.UUID(s)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {name}",
        ) from exc


# ── Scheduling & availability ─────────────────────────────────────────


@router.post("/availability", response_model=InterviewAvailabilityResponse)
def post_availability(
    body: InterviewAvailabilityRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    require_org_hr(db, current_user, body.organization_id)
    slots_raw = list_availability(body.from_date, body.to_date, body.slot_minutes)
    slots = [
        TimeSlotOut(start=x["start"], end=x["end"], timezone=x["timezone"])
        for x in slots_raw
    ]
    return InterviewAvailabilityResponse(
        organization_id=body.organization_id,
        slots=slots,
    )


@router.post("/schedule", response_model=InterviewScheduleResponse)
async def post_schedule(
    body: InterviewScheduleRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    require_org_hr(db, current_user, body.organization_id)
    app = assert_application_in_org(db, body.application_id, body.organization_id)
    if not settings.interview_intelligence_enabled:
        raise HTTPException(status_code=503, detail="Interview module disabled")
    try:
        inv, err = await schedule_interview(
            db,
            application=app,
            org_id=body.organization_id,
            user=current_user,
            interview_type=body.interview_type,
            slot_start=body.slot_start,
            slot_end=body.slot_end,
            tz=body.timezone,
            participant_user_ids=body.participant_user_ids,
            meeting_provider=body.meeting_provider,
            manual_meeting_url=body.manual_meeting_url,
            create_calendar_event=body.create_calendar_event,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    db.commit()
    db.refresh(inv)
    return InterviewScheduleResponse(
        interview_id=inv.id,
        status=inv.status,
        meeting_url=inv.meeting_url,
        meeting_provider=inv.meeting_provider,
        calendar_event_id=inv.calendar_event_id,
        message=err,
    )


@router.post("/", status_code=201)
def create_interview_draft(
    body: InterviewCreateStub,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    require_org_hr(db, current_user, body.organization_id)
    app = assert_application_in_org(db, body.application_id, body.organization_id)
    inv = Interview(
        id=uuid.uuid4(),
        application_id=app.id,
        candidate_id=app.candidate_id,
        job_id=app.job_id,
        organization_id=body.organization_id,
        interview_type=body.interview_type,
        status="draft",
        created_by_user_id=current_user.id,
    )
    db.add(inv)
    log_interview_action(
        db, actor_user_id=current_user.id, action="interview.create_draft",
        entity_id=inv.id, new_value={},
    )
    db.commit()
    return {"interview_id": str(inv.id), "status": inv.status}


@router.patch("/{interview_id}/reschedule")
async def patch_reschedule(
    interview_id: str,
    body: InterviewRescheduleRequest,
    org_id: uuid.UUID = Query(..., description="Organization scope"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    iid = _parse_uuid(interview_id)
    require_org_hr(db, current_user, org_id)
    inv = get_interview_for_org(db, iid, org_id)
    prov = get_meeting_provider("google_meet")
    if inv.calendar_event_id:
        await prov.update_meeting(
            calendar_event_id=inv.calendar_event_id,
            start=body.new_start,
            end=body.new_end,
            timezone=body.timezone,
        )
    inv.scheduled_start_time = body.new_start
    inv.scheduled_end_time = body.new_end
    inv.timezone = body.timezone
    inv.status = "rescheduled"
    log_interview_action(
        db, actor_user_id=current_user.id, action="interview.reschedule",
        entity_id=inv.id, new_value={"start": body.new_start.isoformat()},
    )
    db.commit()
    return {"interview_id": str(inv.id), "status": inv.status}


@router.patch("/{interview_id}/cancel")
def patch_cancel(
    interview_id: str,
    org_id: uuid.UUID = Query(...),
    body: InterviewCancelRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    iid = _parse_uuid(interview_id)
    require_org_hr(db, current_user, org_id)
    inv = get_interview_for_org(db, iid, org_id)
    inv.status = "cancelled"
    log_interview_action(
        db, actor_user_id=current_user.id, action="interview.cancel",
        entity_id=inv.id, new_value={"reason": (body and body.reason) or None},
    )
    db.commit()
    return {"interview_id": str(inv.id), "status": inv.status}


# ── Questions ─────────────────────────────────────────────────────────


@router.post("/{interview_id}/generate-questions")
async def post_generate_questions(
    interview_id: str,
    body: GenerateInterviewQuestionsRequest,
    org_id: uuid.UUID = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    iid = _parse_uuid(interview_id)
    require_org_hr(db, current_user, org_id)
    inv = get_interview_for_org(db, iid, org_id)
    if not settings.interview_intelligence_enabled:
        raise HTTPException(status_code=503, detail="Interview module disabled")
    packs = await generate_question_packs(
        db, inv, include_hr=body.include_hr, include_technical=body.include_technical,
        regenerate=body.regenerate,
    )
    log_interview_action(
        db, actor_user_id=current_user.id, action="interview.generate_questions",
        entity_id=inv.id, new_value={},
    )
    db.commit()
    return {"question_pack_ids": [str(p.id) for p in packs]}


@router.get("/{interview_id}/questions")
def get_questions(
    interview_id: str,
    org_id: uuid.UUID = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    iid = _parse_uuid(interview_id)
    require_org_hr(db, current_user, org_id)
    inv = get_interview_for_org(db, iid, org_id)
    rows = db.execute(
        select(InterviewQuestionPack).where(InterviewQuestionPack.interview_id == inv.id),
    ).scalars().all()
    return {
        "interview_id": str(inv.id),
        "packs": [
            {
                "id": str(r.id),
                "question_pack_type": r.question_pack_type,
                "questions_json": r.questions_json,
                "approved_by_hr": r.approved_by_hr,
                "approved_at": r.approved_at.isoformat() if r.approved_at else None,
            }
            for r in rows
        ],
    }


@router.patch("/{interview_id}/questions/approve")
def patch_questions_approve(
    interview_id: str,
    body: ApproveInterviewQuestionsRequest,
    org_id: uuid.UUID = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    from datetime import timezone as dt_tz

    iid = _parse_uuid(interview_id)
    require_org_hr(db, current_user, org_id)
    inv = get_interview_for_org(db, iid, org_id)
    rows = db.execute(
        select(InterviewQuestionPack).where(InterviewQuestionPack.interview_id == inv.id),
    ).scalars().all()
    if not rows:
        raise HTTPException(status_code=404, detail="No question packs")
    for r in rows:
        r.approved_by_hr = body.approved
        r.approved_at = datetime.now(dt_tz.utc) if body.approved else None
        if body.edited_questions_json is not None:
            r.questions_json = body.edited_questions_json
    log_interview_action(
        db, actor_user_id=current_user.id, action="interview.questions_approve",
        entity_id=inv.id, new_value={"approved": body.approved},
    )
    db.commit()
    return {"ok": True}


# ── Transcript & analysis ─────────────────────────────────────────────


@router.post("/{interview_id}/transcript")
def post_transcript(
    interview_id: str,
    body: InterviewTranscriptCreate,
    org_id: uuid.UUID = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    iid = _parse_uuid(interview_id)
    require_org_hr(db, current_user, org_id)
    inv = get_interview_for_org(db, iid, org_id)
    tr = InterviewTranscript(
        id=uuid.uuid4(),
        interview_id=inv.id,
        transcript_text=body.transcript_text,
        transcript_source=body.transcript_source,
        language=body.language,
        quality_hint=body.quality_hint,
    )
    db.add(tr)
    log_interview_action(
        db, actor_user_id=current_user.id, action="interview.transcript_upload",
        entity_id=inv.id, new_value={"len": len(body.transcript_text)},
    )
    db.commit()
    return {"transcript_id": str(tr.id)}


@router.post("/{interview_id}/transcribe-audio")
async def post_transcribe_audio(
    interview_id: str,
    org_id: uuid.UUID = Query(...),
    file: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    iid = _parse_uuid(interview_id)
    require_org_hr(db, current_user, org_id)
    get_interview_for_org(db, iid, org_id)
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Audio transcription is not wired in this deployment; upload a text transcript instead.",
    )


@router.post("/{interview_id}/analyze", response_model=InterviewAnalyzeResponse)
async def post_analyze(
    interview_id: str,
    org_id: uuid.UUID = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    iid = _parse_uuid(interview_id)
    require_org_hr(db, current_user, org_id)
    inv = get_interview_for_org(db, iid, org_id)
    if not settings.interview_intelligence_enabled:
        raise HTTPException(status_code=503, detail="Interview module disabled")
    result = await run_full_analysis(db, inv)
    log_interview_action(
        db, actor_user_id=current_user.id, action="interview.analyze",
        entity_id=inv.id, new_value=result,
    )
    db.commit()
    summ = result.get("summary")
    summ_out = None
    if summ:
        db.refresh(summ)
        summ_out = InterviewSummaryOut(
            id=summ.id, summary_json=summ.summary_json, created_at=summ.created_at,
        )
    ev_hr = db.execute(
        select(InterviewEvaluation)
        .where(InterviewEvaluation.interview_id == inv.id, InterviewEvaluation.evaluation_type == "hr")
        .order_by(InterviewEvaluation.created_at.desc())
        .limit(1),
    ).scalar_one_or_none()
    ev_t = db.execute(
        select(InterviewEvaluation)
        .where(InterviewEvaluation.interview_id == inv.id, InterviewEvaluation.evaluation_type == "technical")
        .order_by(InterviewEvaluation.created_at.desc())
        .limit(1),
    ).scalar_one_or_none()
    de = db.execute(
        select(InterviewDecisionPacket)
        .where(InterviewDecisionPacket.interview_id == inv.id)
        .order_by(InterviewDecisionPacket.created_at.desc())
        .limit(1),
    ).scalar_one_or_none()
    return InterviewAnalyzeResponse(
        interview_id=inv.id,
        summary=summ_out,
        hr_evaluation=InterviewEvaluationOut(
            id=ev_hr.id, evaluation_type=ev_hr.evaluation_type,
            score_json=ev_hr.score_json, recommendation=ev_hr.recommendation,
            confidence=ev_hr.confidence, created_at=ev_hr.created_at,
        ) if ev_hr else None,
        technical_evaluation=InterviewEvaluationOut(
            id=ev_t.id, evaluation_type=ev_t.evaluation_type,
            score_json=ev_t.score_json, recommendation=ev_t.recommendation,
            confidence=ev_t.confidence, created_at=ev_t.created_at,
        ) if ev_t else None,
        decision_packet=InterviewDecisionPacketOut(
            id=de.id, recommendation=de.recommendation, final_score=de.final_score,
            confidence=de.confidence, decision_packet_json=de.decision_packet_json,
            human_review_required=de.human_review_required, created_at=de.created_at,
        ) if de else None,
        compliance=result.get("compliance") or {},
    )


@router.get("/{interview_id}/summary")
def get_summary(
    interview_id: str,
    org_id: uuid.UUID = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    iid = _parse_uuid(interview_id)
    require_org_hr(db, current_user, org_id)
    inv = get_interview_for_org(db, iid, org_id)
    row = db.execute(
        select(InterviewSummary)
        .where(InterviewSummary.interview_id == inv.id)
        .order_by(InterviewSummary.created_at.desc())
        .limit(1),
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="No summary")
    return {"id": str(row.id), "summary_json": row.summary_json, "created_at": row.created_at}


@router.get("/{interview_id}/evaluation")
def get_evaluation(
    interview_id: str,
    org_id: uuid.UUID = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    iid = _parse_uuid(interview_id)
    require_org_hr(db, current_user, org_id)
    inv = get_interview_for_org(db, iid, org_id)
    rows = db.execute(
        select(InterviewEvaluation).where(InterviewEvaluation.interview_id == inv.id),
    ).scalars().all()
    return {
        "items": [
            {
                "id": str(r.id),
                "evaluation_type": r.evaluation_type,
                "score_json": r.score_json,
                "recommendation": r.recommendation,
                "confidence": r.confidence,
            }
            for r in rows
        ],
    }


@router.get("/{interview_id}/decision-packet")
def get_decision_packet(
    interview_id: str,
    org_id: uuid.UUID = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    iid = _parse_uuid(interview_id)
    require_org_hr(db, current_user, org_id)
    inv = get_interview_for_org(db, iid, org_id)
    row = db.execute(
        select(InterviewDecisionPacket)
        .where(InterviewDecisionPacket.interview_id == inv.id)
        .order_by(InterviewDecisionPacket.created_at.desc())
        .limit(1),
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="No decision packet")
    return {
        "id": str(row.id),
        "recommendation": row.recommendation,
        "decision_packet_json": row.decision_packet_json,
        "human_review_required": row.human_review_required,
    }


# ── Human decision (HR only) ──────────────────────────────────────────


@router.post("/{interview_id}/human-decision", response_model=InterviewHumanDecisionOut)
def post_human_decision(
    interview_id: str,
    body: InterviewHumanDecisionRequest,
    org_id: uuid.UUID = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    iid = _parse_uuid(interview_id)
    require_org_hr(db, current_user, org_id, allowed_roles=("admin", "hr", "hiring_manager"))
    inv = get_interview_for_org(db, iid, org_id)
    row = InterviewHumanDecision(
        id=uuid.uuid4(),
        interview_id=inv.id,
        decided_by=current_user.id,
        final_decision=body.final_decision,
        hr_notes=body.hr_notes,
        override_reason=body.override_reason,
    )
    db.add(row)
    log_interview_action(
        db, actor_user_id=current_user.id, action="interview.human_decision",
        entity_id=inv.id,
        new_value={
            "decision": body.final_decision,
            "override_reason": body.override_reason,
        },
    )
    db.commit()
    db.refresh(row)
    return row


# ── Candidate: own interview scheduling view (read-only link + slot confirm) ─


@router.get("/candidate/{interview_id}/meeting")
def candidate_meeting(
    interview_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    iid = _parse_uuid(interview_id)
    inv = db.get(Interview, iid)
    if not inv:
        raise HTTPException(status_code=404, detail="Not found")
    cand = current_user.candidate_profile
    if not cand or inv.candidate_id != cand.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return {
        "interview_id": str(inv.id),
        "meeting_url": inv.meeting_url,
        "scheduled_start_time": inv.scheduled_start_time,
        "scheduled_end_time": inv.scheduled_end_time,
        "timezone": inv.timezone,
        "status": inv.status,
    }
