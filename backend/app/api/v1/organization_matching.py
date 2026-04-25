"""
Organization-side candidate search, ranking, and outreach (Path A + Path B).
"""

from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.db.models.organization_matching import OrganizationCandidateRanking
from app.db.repositories import organization_matching_repo as om_repo
from app.schemas.organization_matching import (
    ApproveOutreachRequest,
    DatabaseSearchRequest,
    SendOutreachRequest,
)
from app.services.organization_matching import (
    organization_matching_service as org_match,
    organization_outreach_service as org_out,
)

router = APIRouter(
    prefix="/organization-matching",
    tags=["Organization matching"],
)
settings = get_settings()


@router.post("/database-search")
def database_search(
    body: DatabaseSearchRequest,
    db: Session = Depends(get_db),
):
    if not settings.org_matching_enabled:
        raise HTTPException(503, detail="organization matching is disabled")
    res = org_match.create_job_request_and_match_from_database(
        db,
        organization_id=body.organization_id,
        job_request_data={"top_k": body.top_k, "job": body.job.model_dump()},
        top_k=body.top_k,
    )
    if not res.get("ok"):
        raise HTTPException(400, detail=res.get("error", "match_failed"))
    return {
        "matching_run_id": res["matching_run_id"],
        "job_id": res["job_id"],
        "top_k": res["top_k"],
        "total_candidates": res.get("discovery", {}).get("pg_scanned", 0),
        "relevant_candidates": res.get("discovery", {}).get("passed_filter", 0),
        "scored_candidates": res.get("discovery", {}).get("passed_filter", 0),
        "shortlisted_candidates": len(res.get("shortlist") or []),
        "shortlist": res.get("shortlist") or [],
    }


@router.post("/csv-search")
async def csv_search(
    organization_id: UUID = Form(...),
    top_k: int = Form(3),
    job: str = Form(..., description="JSON string of job payload"),
    csv_file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    if not settings.org_matching_enabled:
        raise HTTPException(503, detail="organization matching is disabled")
    try:
        job_data = json.loads(job)
    except json.JSONDecodeError as e:
        raise HTTPException(400, detail=f"invalid job json: {e}") from e
    raw = await csv_file.read()
    res = org_match.create_job_request_and_match_from_csv(
        db,
        organization_id=organization_id,
        job_request_data={"top_k": top_k, "job": job_data},
        csv_file_bytes=raw,
        file_name=csv_file.filename or "candidates.csv",
        top_k=top_k,
    )
    if not res.get("ok"):
        raise HTTPException(400, detail=res.get("error", "match_failed"))
    return {
        "matching_run_id": res["matching_run_id"],
        "job_id": res["job_id"],
        "top_k": res["top_k"],
        "candidate_import": res.get("candidate_import") or {},
        "total_candidates": res.get("candidate_import", {}).get("total_rows", 0),
        "relevant_candidates": res.get("candidate_import", {}).get("valid_rows", 0),
        "scored_candidates": res.get("candidate_import", {}).get("valid_rows", 0),
        "shortlisted_candidates": len(res.get("shortlist") or []),
        "shortlist": res.get("shortlist") or [],
    }


@router.get("/runs/{run_id}")
def get_run(run_id: UUID, db: Session = Depends(get_db)):
    r = org_match.get_matching_run(db, run_id)
    if r is None:
        raise HTTPException(404, detail="run not found")
    return r


@router.get("/runs/{run_id}/shortlist")
def get_shortlist_endpoint(run_id: UUID, db: Session = Depends(get_db)):
    return {"shortlist": org_match.get_shortlist(db, run_id, anonymized=True)}


@router.post("/runs/{run_id}/shortlist/{ranking_id}/approve-outreach")
def approve_outreach(
    run_id: UUID,
    ranking_id: UUID,
    body: ApproveOutreachRequest,
    db: Session = Depends(get_db),
):
    row = db.get(OrganizationCandidateRanking, ranking_id)
    if row is None or row.matching_run_id != run_id:
        raise HTTPException(404, detail="ranking not found")
    org_out.approve_deanonymize_for_outreach(
        db,
        matching_run_id=run_id,
        candidate_id=row.candidate_id,
        approved_by=None,
    )
    row.status = "approved_for_outreach"
    db.add(row)
    db.commit()
    return {"ok": True, "booking_link": body.booking_link, "deadline_days": body.deadline_days}


@router.post("/runs/{run_id}/outreach/{ranking_id}/generate-draft")
def generate_draft(
    run_id: UUID,
    ranking_id: UUID,
    body: ApproveOutreachRequest | None = None,
    db: Session = Depends(get_db),
):
    row = db.get(OrganizationCandidateRanking, ranking_id)
    if row is None or row.matching_run_id != run_id:
        raise HTTPException(404, detail="ranking not found")
    b = body or ApproveOutreachRequest()
    m = org_out.generate_draft(
        db,
        organization_id=row.organization_id,
        matching_run_id=run_id,
        ranking=row,
        booking_link=b.booking_link,
        deadline_days=b.deadline_days,
    )
    return {
        "message_id": str(m.id),
        "status": m.status,
        "subject": m.subject,
        "body": m.body,
    }


@router.post("/runs/{run_id}/outreach/{ranking_id}/stream-email")
async def stream_email(
    run_id: UUID,
    ranking_id: UUID,
    body: ApproveOutreachRequest | None = None,
    db: Session = Depends(get_db),
):
    row = db.get(OrganizationCandidateRanking, ranking_id)
    if row is None or row.matching_run_id != run_id:
        raise HTTPException(404, detail="ranking not found")
    b = body or ApproveOutreachRequest()
    days = int(b.deadline_days or settings.outreach_reply_deadline_days)
    messages = org_out.build_stream_messages(
        db,
        organization_id=row.organization_id,
        ranking=row,
        booking_link=b.booking_link,
        deadline_days=days,
    )
    from app.core.database import SessionLocal as _SL

    async def gen():
        acc: list[str] = []
        try:
            async for chunk in org_out.stream_email_tokens(messages):
                acc.append(chunk)
                yield chunk
        finally:
            full = "".join(acc)
            s2 = _SL()
            try:
                org_out.save_streamed_draft(
                    s2,
                    organization_id=row.organization_id,
                    matching_run_id=run_id,
                    ranking=row,
                    full_text=full,
                    booking_link=b.booking_link,
                    deadline_days=days,
                )
            finally:
                s2.close()

    return StreamingResponse(gen(), media_type="text/plain; charset=utf-8")


@router.post("/outreach/{message_id}/send")
def send_outreach(
    message_id: UUID,
    body: SendOutreachRequest,
    db: Session = Depends(get_db),
):
    m = om_repo.get_outreach_message(db, message_id)
    if m is None:
        raise HTTPException(404, detail="message not found")
    if m.ranking_id and settings.outreach_require_approval:
        rk = db.get(OrganizationCandidateRanking, m.ranking_id)
        if rk and rk.status != "approved_for_outreach":
            raise HTTPException(400, detail="ranking not approved for outreach")
    from app.db.models.candidate import Candidate

    to = body.recipient_email
    if m.candidate_id:
        c = db.get(Candidate, m.candidate_id)
        if c and c.email:
            to = c.email
    m.status = "approved"
    db.add(m)
    db.commit()
    r = org_out.send_approved_smtp(db, message_id=message_id, recipient_email=to)
    if not r.get("ok"):
        raise HTTPException(400, detail=r.get("error", "send_failed"))
    return {"ok": True}
