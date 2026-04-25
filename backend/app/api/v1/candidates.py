import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.core.database import get_db
from app.db.models.candidate import Candidate
from app.db.models.cv_entities import CandidateSkill, CandidateExperience, CandidateEducation, CandidateCertification

router = APIRouter(prefix="/candidates", tags=["Candidates"])

@router.get("/{candidate_id}")
async def get_candidate(candidate_id: str, db: Session = Depends(get_db)):
    try:
        cand_uuid = uuid.UUID(candidate_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid candidate_id UUID")

    cand = db.get(Candidate, cand_uuid)
    if not cand:
        raise HTTPException(status_code=404, detail="Candidate not found")
        
    skills = db.execute(select(CandidateSkill).where(CandidateSkill.candidate_id == cand_uuid)).scalars().all()
    experiences = db.execute(select(CandidateExperience).where(CandidateExperience.candidate_id == cand_uuid)).scalars().all()
    education = db.execute(select(CandidateEducation).where(CandidateEducation.candidate_id == cand_uuid)).scalars().all()
    certifications = db.execute(select(CandidateCertification).where(CandidateCertification.candidate_id == cand_uuid)).scalars().all()

    return {
        "candidate": {
            "id": str(cand.id),
            "full_name": cand.full_name,
            "email": cand.email,
            "phone": cand.phone,
            "location_text": cand.location_text,
            "summary": cand.summary,
            "years_experience": cand.years_experience
        },
        "skills": [{"skill_id": str(s.skill_id), "score": s.proficiency_score} for s in skills],
        "experiences": [{"company": e.company_name, "title": e.title} for e in experiences],
        "education": [{"institution": e.institution, "degree": e.degree} for e in education],
        "certifications": [{"name": c.name, "issuer": c.issuer} for c in certifications]
    }
