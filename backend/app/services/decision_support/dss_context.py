"""Load all evidence for a decision support packet (no LLM)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Job, Organization
from app.db.models.application import Application
from app.db.models.candidate import Candidate
from app.db.models.interview import (
    Interview,
    InterviewDecisionPacket,
    InterviewEvaluation,
    InterviewSummary,
)
from app.db.models.organization_matching import OrganizationOutreachMessage
from app.db.models.scoring import CandidateJobScore


def load_journey_context(
    db: Session,
    *,
    application_id: uuid.UUID,
) -> dict[str, Any]:
    app = db.get(Application, application_id)
    if app is None:
        raise ValueError("application not found")
    cand = db.get(Candidate, app.candidate_id)
    job = db.get(Job, app.job_id)
    if not job or not cand:
        raise ValueError("candidate or job missing")
    org = db.get(Organization, job.organization_id) if job.organization_id else None

    score_row = db.execute(
        select(CandidateJobScore).where(
            CandidateJobScore.candidate_id == app.candidate_id,
            CandidateJobScore.job_id == app.job_id,
        ),
    ).scalar_one_or_none()

    interviews = db.execute(
        select(Interview).where(Interview.application_id == application_id),
    ).scalars().all()

    interview_blocks: list[dict[str, Any]] = []
    transcript_quality = "medium"
    for inv in interviews:
        summ = db.execute(
            select(InterviewSummary)
            .where(InterviewSummary.interview_id == inv.id)
            .order_by(InterviewSummary.created_at.desc())
            .limit(1),
        ).scalar_one_or_none()
        evs = db.execute(
            select(InterviewEvaluation).where(InterviewEvaluation.interview_id == inv.id),
        ).scalars().all()
        dpack = db.execute(
            select(InterviewDecisionPacket)
            .where(InterviewDecisionPacket.interview_id == inv.id)
            .order_by(InterviewDecisionPacket.created_at.desc())
            .limit(1),
        ).scalar_one_or_none()
        block: dict[str, Any] = {
            "interview_id": str(inv.id),
            "interview_type": inv.interview_type,
            "status": inv.status,
            "summary": summ.summary_json if summ else None,
            "evaluations": [
                {"type": e.evaluation_type, "score_json": e.score_json}
                for e in evs
            ],
            "interview_decision_packet": dpack.decision_packet_json if dpack else None,
        }
        interview_blocks.append(block)
        if summ and summ.summary_json:
            t = str(summ.summary_json.get("short_summary", ""))
            if len(t) < 80:
                transcript_quality = "low"

    outreach_rows = db.execute(
        select(OrganizationOutreachMessage).where(
            OrganizationOutreachMessage.candidate_id == app.candidate_id,
            OrganizationOutreachMessage.job_id == app.job_id,
        ).order_by(OrganizationOutreachMessage.created_at.desc()).limit(5),
    ).scalars().all()
    outreach_history = [
        {
            "subject": r.subject,
            "status": r.status,
            "reply_deadline_at": r.reply_deadline_at.isoformat() if r.reply_deadline_at else None,
        }
        for r in outreach_rows
    ]

    return {
        "application": {
            "id": str(app.id),
            "current_stage_code": app.current_stage_code,
            "overall_status": app.overall_status,
        },
        "candidate": {
            "id": str(cand.id),
            "full_name": cand.full_name,
            "headline": cand.headline,
            "summary": (cand.summary or "")[:8000],
            "years_experience": cand.years_experience,
        },
        "job": {
            "id": str(job.id),
            "title": job.title,
            "requirements": (job.requirements or "")[:8000],
            "description_text": (job.description_text or "")[:8000],
            "seniority_level": job.seniority_level,
        },
        "organization": {
            "id": str(org.id) if org else None,
            "name": org.name if org else None,
        },
        "candidate_job_score": (
            {
                "final_score": float(score_row.final_score),
                "explanation": score_row.explanation,
                "agent_score": float(score_row.agent_score),
                "vector_similarity_score": float(score_row.vector_similarity_score),
                "criteria_breakdown": score_row.criteria_breakdown,
            }
            if score_row
            else None
        ),
        "assessment": None,
        "interviews": interview_blocks,
        "outreach_history": outreach_history,
        "transcript_quality": transcript_quality,
    }
