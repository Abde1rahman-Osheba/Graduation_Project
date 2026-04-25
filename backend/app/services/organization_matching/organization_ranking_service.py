"""
Score job ↔ candidates (same agent + vector logic as candidate-side),
persist `organization_candidate_rankings`, and best-effort AGE `MATCHES_JOB`.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models.organization_matching import OrganizationCandidateRanking
from app.db.repositories import organization_matching_repo as om_repo
from app.db.repositories import scoring_repository as srepo
from app.services.scoring.llama_scoring_agent import (
    AgentScoreError,
    score_candidate_for_job,
)
from app.services.scoring.relevance_filter_service import assess_relevance, candidate_role_family
from app.services.scoring.scoring_criteria import (
    classify_final_score,
    recommendation_for,
)
from app.services.scoring.scoring_prompt_builder import anonymize_candidate, anonymize_job
from app.services.scoring.scoring_service import combine_scores
from app.services.scoring.vector_similarity_service import compute_similarity_score
from app.utils.age_query import ensure_graph, run_cypher

logger = logging.getLogger(__name__)
settings = get_settings()


def _age_org_matches_job(
    db: Session,
    *,
    candidate_id: UUID,
    job_id: UUID,
    row: OrganizationCandidateRanking,
    matching_run_id: UUID,
) -> None:
    try:
        ensure_graph(db)
        cypher = """
        MERGE (c:Candidate {candidate_id: $candidate_id})
        MERGE (j:Job {job_id: $job_id})
        MERGE (c)-[m:MATCHES_JOB]->(j)
        SET m.final_score = $final_score,
            m.agent_score = $agent_score,
            m.vector_similarity_score = $vector_similarity_score,
            m.recommendation = $recommendation,
            m.match_classification = $match_classification,
            m.matching_run_id = $matching_run_id,
            m.blind_candidate_id = $blind_candidate_id,
            m.rank_position = $rank_position,
            m.anonymized = true,
            m.updated_at = $updated_at
        RETURN m
        """
        run_cypher(
            db, cypher,
            {
                "candidate_id": str(candidate_id),
                "job_id": str(job_id),
                "final_score": float(row.final_score),
                "agent_score": float(row.agent_score),
                "vector_similarity_score": float(row.vector_similarity_score),
                "recommendation": row.recommendation or "",
                "match_classification": row.match_classification or "",
                "matching_run_id": str(matching_run_id),
                "blind_candidate_id": row.blind_candidate_id,
                "rank_position": row.rank_position,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        db.flush()
    except Exception:  # noqa: BLE001
        db.rollback()
        logger.exception("AGE org MATCHES_JOB sync failed")


async def score_candidates_for_job(
    db: Session,
    *,
    organization_id: UUID,
    matching_run_id: UUID,
    job_request_id: UUID,
    job_id: UUID,
    candidate_ids: list[UUID],
    top_k: int,
) -> dict[str, Any]:
    jprof = srepo.get_job_profile(db, job_id)
    if jprof is None:
        return {"scored": 0, "failed": 0, "rows": []}

    thr = float(settings.org_scoring_min_relevance_threshold)
    a_w, v_w = float(settings.org_scoring_agent_weight), float(settings.org_scoring_vector_weight)
    ranked: list[dict[str, Any]] = []
    failed = 0

    async with httpx.AsyncClient(
        timeout=settings.scoring_request_timeout_seconds,
    ) as client:
        for cand_id in candidate_ids:
            cprof = srepo.get_candidate_profile(db, cand_id)
            if cprof is None:
                failed += 1
                continue
            sim = compute_similarity_score(cand_id, job_id)
            dec = assess_relevance(
                cprof, jprof,
                candidate_family=candidate_role_family(cprof),
                vector_similarity_score=sim.score,
                min_relevance_threshold=thr,
            )
            if not dec.is_relevant:
                continue
            anon_c = anonymize_candidate(cprof, candidate_id=str(cand_id))
            anon_j = anonymize_job(jprof, job_id=str(job_id))
            outcome = await score_candidate_for_job(
                anonymized_candidate=anon_c, anonymized_job=anon_j, client=client,
            )
            if isinstance(outcome, AgentScoreError):
                failed += 1
                continue
            final = combine_scores(
                outcome.agent_score, sim.score,
                agent_weight=a_w, vector_weight=v_w,
            )
            blind = om_repo.create_blind_candidate_map(
                db, organization_id=organization_id,
                matching_run_id=matching_run_id, candidate_id=cand_id,
            )
            mcls = classify_final_score(final)
            row = om_repo.upsert_candidate_ranking(
                db,
                {
                    "organization_id": organization_id,
                    "matching_run_id": matching_run_id,
                    "job_request_id": job_request_id,
                    "job_id": job_id,
                    "candidate_id": cand_id,
                    "blind_candidate_id": blind,
                    "agent_score": float(outcome.agent_score),
                    "vector_similarity_score": float(sim.score),
                    "final_score": float(final),
                    "relevance_score": float(dec.relevance_score),
                    "criteria_breakdown": outcome.criteria_breakdown,
                    "matched_skills": outcome.matched_skills,
                    "missing_required_skills": outcome.missing_required_skills,
                    "missing_preferred_skills": outcome.missing_preferred_skills,
                    "strengths": outcome.strengths,
                    "weaknesses": outcome.weaknesses,
                    "explanation": outcome.explanation,
                    "recommendation": outcome.recommendation
                    or recommendation_for(final),
                    "match_classification": mcls,
                    "status": "ranked",
                },
            )
            ranked.append(
                {
                    "row_id": row.id,
                    "final_score": final,
                },
            )
            try:
                _age_org_matches_job(
                    db, candidate_id=cand_id, job_id=job_id, row=row,
                    matching_run_id=matching_run_id,
                )
            except Exception:  # noqa: BLE001
                logger.debug("age skipped")
        db.commit()

    ranked.sort(key=lambda x: x["final_score"], reverse=True)
    top = ranked[: max(1, int(top_k))]
    for i, r in enumerate(top, start=1):
        row2 = db.get(OrganizationCandidateRanking, r["row_id"])
        if row2 is None:
            continue
        row2.rank_position = i
        if not settings.org_matching_require_human_approval:
            row2.status = "shortlisted"
    db.commit()

    top_rows: list[OrganizationCandidateRanking] = []
    for r in top:
        tr = db.get(OrganizationCandidateRanking, r["row_id"])
        if tr is not None:
            top_rows.append(tr)
    return {
        "scored": len(ranked),
        "failed": failed,
        "shortlist": top_rows,
    }
