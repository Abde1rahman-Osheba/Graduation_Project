"""
Interview orchestration: scheduling, question generation, LangGraph analysis, HITL logging.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Sequence

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.agents.interview_intelligence.graph import interview_analysis_app
from app.agents.interview_intelligence.nodes import llm_json
from app.core.config import get_settings
from app.db.models import Job
from app.db.models.application import Application, OrganizationMember
from app.db.models.candidate import Candidate
from app.db.models.interview import (
    Interview,
    InterviewDecisionPacket,
    InterviewEvaluation,
    InterviewHumanDecision,
    InterviewParticipant,
    InterviewQuestionPack,
    InterviewSummary,
    InterviewTranscript,
)
from app.db.models.user import User
from app.db.models.scoring import CandidateJobScore
from app.services.interview.interview_audit import log_interview_action
from app.services.interview.meeting_providers import get_meeting_provider
settings = get_settings()


def _org_membership(
    db: Session, user_id: uuid.UUID, org_id: uuid.UUID,
) -> OrganizationMember | None:
    return db.execute(
        select(OrganizationMember).where(
            OrganizationMember.user_id == user_id,
            OrganizationMember.organization_id == org_id,
            OrganizationMember.is_active == True,  # noqa: E712
        ),
    ).scalar_one_or_none()


def require_org_hr(
    db: Session, user: User, org_id: uuid.UUID, allowed_roles: Sequence[str] | None = None,
) -> None:
    from fastapi import HTTPException, status

    allowed = set(allowed_roles or ("admin", "hr", "hiring_manager", "member", "interviewer"))
    if user.account_type != "organization_member":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Organization only")
    m = _org_membership(db, user.id, org_id)
    if m is None or m.role_code not in allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member of this organization")


def get_interview_for_org(
    db: Session, interview_id: uuid.UUID, org_id: uuid.UUID,
) -> Interview:
    from fastapi import HTTPException, status

    row = db.get(Interview, interview_id)
    if row is None or row.organization_id != org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview not found")
    return row


def assert_application_in_org(
    db: Session, app_id: uuid.UUID, org_id: uuid.UUID,
) -> Application:
    from fastapi import HTTPException, status

    app = db.get(Application, app_id)
    if app is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
    job = db.get(Job, app.job_id)
    if job is None or job.organization_id != org_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Job/organization mismatch")
    return app


def candidate_owns_application(db: Session, user: User, app: Application) -> bool:
    if user.account_type != "candidate" or not user.candidate_profile:
        return False
    return app.candidate_id == user.candidate_profile.id


def build_job_context(db: Session, job_id: uuid.UUID) -> dict[str, Any]:
    j = db.get(Job, job_id)
    if j is None:
        return {}
    return {
        "title": j.title,
        "summary": (j.summary or "")[:15000],
        "requirements": (j.requirements or "")[:15000],
        "description_text": (j.description_text or "")[:15000],
        "seniority_level": j.seniority_level,
        "role_family": j.role_family,
    }


def build_candidate_context(db: Session, candidate_id: uuid.UUID) -> dict[str, Any]:
    c = db.get(Candidate, candidate_id)
    if c is None:
        return {}
    return {
        "full_name": c.full_name,
        "headline": c.headline,
        "summary": (c.summary or "")[:15000],
        "current_title": c.current_title,
        "years_experience": c.years_experience,
    }


def get_latest_job_match_score(db: Session, candidate_id: uuid.UUID, job_id: uuid.UUID) -> float | None:
    row = db.execute(
        select(CandidateJobScore).where(
            CandidateJobScore.candidate_id == candidate_id,
            CandidateJobScore.job_id == job_id,
        ),
    ).scalar_one_or_none()
    if row is None:
        return None
    return float(row.final_score)


# Availability: see `app.services.interview.availability.list_availability`.

# ── Question generation (LLM) ─────────────────────────────────────────

async def generate_question_packs(
    db: Session,
    interview: Interview,
    *,
    include_hr: bool,
    include_technical: bool,
    regenerate: bool,
) -> list[InterviewQuestionPack]:
    job = build_job_context(db, interview.job_id)
    cand = build_candidate_context(db, interview.candidate_id)
    itype = interview.interview_type.lower()
    results: list[InterviewQuestionPack] = []

    if regenerate:
        db.execute(
            delete(InterviewQuestionPack).where(
                InterviewQuestionPack.interview_id == interview.id,
            ),
        )
    else:
        existing = db.execute(
            select(InterviewQuestionPack).where(
                InterviewQuestionPack.interview_id == interview.id,
            ),
        ).scalars().all()
        if existing:
            return list(existing)

    if include_hr and itype in ("hr", "mixed"):
        system = (
            "You are an expert HR interviewer. Generate fair, job-related, non-discriminatory questions. "
            "Output JSON: { questions: [ { question_id, question_text, competency_tested, "
            "why_this_question_matters, expected_good_answer_signals, red_flags, scoring_rubric_1_to_5, "
            "follow_up_questions } ] }"
        )
        user = f"Job context:\n{job}\n\nCandidate context:\n{cand}\n"
        pack = await llm_json(system, user)
        results.append(
            InterviewQuestionPack(
                id=uuid.uuid4(),
                interview_id=interview.id,
                question_pack_type="hr",
                generated_by_agent="hr_question_agent",
                questions_json=pack,
            )
        )
    if include_technical and itype in ("technical", "mixed"):
        system = (
            "You are a technical interviewer. Every question must tie to job requirements or CV claims. "
            "Output JSON: { questions: [ { question_id, skill_area, difficulty, question_text, "
            "expected_answer_points, evaluation_rubric_1_to_5, practical_task_if_needed, follow_up_questions, "
            "evidence_source_type, why_this_question_is_relevant } ] }"
        )
        user = f"Job context:\n{job}\n\nCandidate context:\n{cand}\n"
        pack = await llm_json(system, user)
        results.append(
            InterviewQuestionPack(
                id=uuid.uuid4(),
                interview_id=interview.id,
                question_pack_type="technical",
                generated_by_agent="technical_question_agent",
                questions_json=pack,
            )
        )
    if itype == "mixed" and not results:
        system = (
            "Generate both HR and technical questions as separate arrays hr_questions, technical_questions. "
            "Use the same per-question field shapes as the dedicated HR/technical agents."
        )
        user = f"Job context:\n{job}\n\nCandidate context:\n{cand}\n"
        pack = await llm_json(system, user)
        results.append(
            InterviewQuestionPack(
                id=uuid.uuid4(),
                interview_id=interview.id,
                question_pack_type="mixed",
                generated_by_agent="hr_technical_question_agent",
                questions_json=pack,
            )
        )
    for r in results:
        db.add(r)
    log_interview_action(
        db,
        actor_user_id=None,
        action="interview.questions_generated",
        entity_id=interview.id,
        new_value={"packs": [str(p.id) for p in results]},
    )
    return results


# ── Analysis (LangGraph) ───────────────────────────────────────────────

async def run_full_analysis(
    db: Session,
    interview: Interview,
) -> dict[str, Any]:
    # Re-runs: replace prior agent outputs for this interview (idempotent UX).
    db.execute(delete(InterviewSummary).where(InterviewSummary.interview_id == interview.id))
    db.execute(delete(InterviewEvaluation).where(InterviewEvaluation.interview_id == interview.id))
    db.execute(
        delete(InterviewDecisionPacket).where(InterviewDecisionPacket.interview_id == interview.id),
    )

    tr_rows = db.execute(
        select(InterviewTranscript)
        .where(InterviewTranscript.interview_id == interview.id)
        .order_by(InterviewTranscript.created_at.desc())
        .limit(1),
    ).scalar_one_or_none()
    transcript = (tr_rows.transcript_text if tr_rows else "") or ""
    tq = "low" if len(transcript) < 200 else "medium" if len(transcript) < 2000 else "high"

    packs = db.execute(
        select(InterviewQuestionPack).where(
            InterviewQuestionPack.interview_id == interview.id,
        ),
    ).scalars().all()
    qjson = [p.questions_json for p in packs]
    jm = get_latest_job_match_score(db, interview.candidate_id, interview.job_id)

    state: dict[str, Any] = {
        "interview_id": str(interview.id),
        "organization_id": str(interview.organization_id),
        "job_context": build_job_context(db, interview.job_id),
        "candidate_context": build_candidate_context(db, interview.candidate_id),
        "application_context": {
            "application_id": str(interview.application_id),
        },
        "question_packs": qjson,
        "transcript": transcript,
        "transcript_quality": tq,
        "interview_type": interview.interview_type,
        "job_match_score": jm,
    }
    if not settings.interview_intelligence_enabled:
        return {"error": "interview module disabled", "compliance": {"compliance_status": "fail"}}

    out = await interview_analysis_app.ainvoke(state)
    if out.get("error"):
        return out

    summ = out.get("interview_summary") or {}
    summ_row = InterviewSummary(
        id=uuid.uuid4(),
        interview_id=interview.id,
        summary_json=summ,
        generated_by_agent="transcript_summarization_agent",
    )
    db.add(summ_row)

    hr = out.get("hr_scorecard") or {}
    te = out.get("technical_scorecard") or {}
    comp = out.get("compliance") or {}
    dp = out.get("decision_packet") or {}

    db.add(
        InterviewEvaluation(
            id=uuid.uuid4(),
            interview_id=interview.id,
            evaluation_type="hr",
            score_json=hr,
            recommendation=str(hr.get("recommendation_from_hr_perspective", ""))[:2000],
            confidence=float(hr.get("overall_hr_score") or 0) / 100.0 if hr.get("overall_hr_score") else 0.5,
        )
    )
    db.add(
        InterviewEvaluation(
            id=uuid.uuid4(),
            interview_id=interview.id,
            evaluation_type="technical",
            score_json=te,
            recommendation=str(te.get("recommendation_from_technical_perspective", ""))[:2000],
            confidence=0.5,
        )
    )
    cstat = (comp.get("compliance_status") or "pass").lower()
    require_human = True
    rec = (dp.get("overall_recommendation") or "Hold") if isinstance(dp, dict) else "Hold"
    fscore = float(dp.get("final_score") or 0.0) if isinstance(dp, dict) else 0.0
    conf = float(dp.get("confidence") or 0.5) if isinstance(dp, dict) else 0.5

    full_packet = {
        "candidate_id": str(interview.candidate_id),
        "job_id": str(interview.job_id),
        "application_id": str(interview.application_id),
        "interview_id": str(interview.id),
        "recommendation": rec,
        "confidence": conf,
        "final_score": fscore,
        "hr_score": dp.get("hr_score"),
        "technical_score": dp.get("technical_score"),
        "job_match_score": dp.get("job_match_score"),
        "main_strengths": dp.get("main_strengths", []),
        "main_weaknesses": dp.get("main_weaknesses", []),
        "risk_flags": dp.get("risk_flags", []),
        "missing_information": dp.get("missing_information", []),
        "evidence_summary": dp.get("evidence_summary", []),
        "suggested_next_step": dp.get("suggested_next_step"),
        "suggested_growth_plan_if_rejected": dp.get("suggested_growth_plan_if_rejected", []),
        "human_review_required": True,
        "compliance": comp,
    }

    if cstat == "fail":
        rec = "Hold"
        full_packet["overall_recommendation"] = "Hold"
        require_human = True

    drow = InterviewDecisionPacket(
        id=uuid.uuid4(),
        interview_id=interview.id,
        application_id=interview.application_id,
        candidate_id=interview.candidate_id,
        job_id=interview.job_id,
        recommendation=rec,
        final_score=fscore,
        confidence=conf,
        decision_packet_json=full_packet,
        human_review_required=require_human,
    )
    db.add(drow)
    log_interview_action(
        db,
        actor_user_id=None,
        action="interview.analysis_complete",
        entity_id=interview.id,
        new_value={"decision_packet_id": str(drow.id), "recommendation": rec},
    )
    return {
        "summary": summ_row,
        "compliance": comp,
        "decision_id": drow.id,
    }


async def schedule_interview(
    db: Session,
    *,
    application: Application,
    org_id: uuid.UUID,
    user: User,
    interview_type: str,
    slot_start: datetime,
    slot_end: datetime,
    tz: str,
    participant_user_ids: list[uuid.UUID],
    meeting_provider: str | None,
    manual_meeting_url: str | None,
    create_calendar_event: bool,
) -> tuple[Interview, str | None]:
    job = db.get(Job, application.job_id)
    if not job or job.organization_id != org_id:
        raise ValueError("invalid org/job")

    prov_name = (meeting_provider or "manual").lower()
    prov = get_meeting_provider(prov_name)
    meeting_url: str | None = manual_meeting_url
    cal_id: str | None = None
    err: str | None = None
    if create_calendar_event and meeting_url is None and prov_name in (
        "google_meet",
        "google",
        "gcal",
    ):
        result = await prov.create_meeting(
            title=f"Interview: {job.title or 'Role'}",
            start=slot_start,
            end=slot_end,
            timezone=tz,
            attendees_emails=[],
        )
        if result.success and result.meeting_url:
            meeting_url = result.meeting_url
            cal_id = result.calendar_event_id
        else:
            err = result.error_message
            fb = get_meeting_provider("manual")
            result2 = await fb.create_meeting(
                title="Interview",
                start=slot_start,
                end=slot_end,
                timezone=tz,
                attendees_emails=[],
            )
            meeting_url = result2.meeting_url
    elif meeting_url is None:
        m = get_meeting_provider("manual")
        r = await m.create_meeting(
            title="Interview",
            start=slot_start,
            end=slot_end,
            timezone=tz,
            attendees_emails=[],
        )
        meeting_url = r.meeting_url

    inv = Interview(
        id=uuid.uuid4(),
        application_id=application.id,
        candidate_id=application.candidate_id,
        job_id=application.job_id,
        organization_id=org_id,
        interview_type=interview_type,
        status="scheduled",
        scheduled_start_time=slot_start,
        scheduled_end_time=slot_end,
        timezone=tz,
        meeting_provider=prov_name if meeting_url else "manual",
        meeting_url=meeting_url,
        calendar_event_id=cal_id,
        created_by_user_id=user.id,
    )
    db.add(inv)
    for uid in participant_user_ids:
        db.add(
            InterviewParticipant(
                id=uuid.uuid4(),
                interview_id=inv.id,
                user_id=uid,
                role="hr",
                attendance_status="invited",
            )
        )
    # Candidate as participant
    c = db.get(Candidate, application.candidate_id)
    if c and c.user_id:
        db.add(
            InterviewParticipant(
                id=uuid.uuid4(),
                interview_id=inv.id,
                user_id=c.user_id,
                role="candidate",
                attendance_status="invited",
            )
        )
    log_interview_action(
        db,
        actor_user_id=user.id,
        action="interview.scheduled",
        entity_id=inv.id,
        new_value={"err": err},
    )
    return inv, err
