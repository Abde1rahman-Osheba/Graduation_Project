"""
PATHS Backend — Candidate-Job scoring orchestrator.

End-to-end pipeline that:

  1. Loads the candidate's structured profile from PostgreSQL.
  2. Loads candidate vector status from Qdrant (via vector_similarity_service).
  3. Infers candidate role family.
  4. Picks at most ``SCORING_MAX_JOBS_PER_CANDIDATE`` active jobs and
     filters them through :func:`relevance_filter_service.assess_relevance`.
  5. For each relevant job:
        - compute Qdrant vector similarity (cosine, normalized 0..100)
        - call the LlamaAgent with the **anonymized** candidate + job
        - combine: ``final_score = agent*W_a + vector*W_v``
        - upsert into ``candidate_job_scores``
        - best-effort sync of the ``MATCHES_JOB`` edge in Apache AGE
        - keep going on failure — record into ``scoring_errors``.
  6. Finalize the ``scoring_runs`` row.

Every per-job step uses its own transaction so a single failure cannot
roll back successful scores.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.db.models.scoring import CandidateJobScore, ScoringRun
from app.db.repositories import scoring_repository as repo
from app.db.repositories.candidates_relational import CandidateFullProfile
from app.db.repositories.jobs_relational import JobFullProfile
from app.services.scoring.llama_scoring_agent import (
    AgentScoreError,
    AgentScoreResult,
    score_candidate_for_job,
)
from app.services.scoring.relevance_filter_service import (
    RelevanceDecision,
    assess_relevance,
    candidate_role_family,
)
from app.services.scoring.scoring_criteria import (
    classify_final_score,
    recommendation_for,
)
from app.services.scoring.scoring_prompt_builder import (
    anonymize_candidate,
    anonymize_job,
)
from app.services.scoring.vector_similarity_service import (
    VectorSimilarityResult,
    compute_similarity_score,
)
from app.utils.age_query import ensure_graph, run_cypher

logger = logging.getLogger(__name__)
settings = get_settings()


# ── Result containers (mirror schemas/scoring.py shape) ─────────────────


@dataclass
class TopMatch:
    job_id: str
    job_title: str
    company_name: str | None
    agent_score: float
    vector_similarity_score: float
    final_score: float
    recommendation: str
    match_classification: str


@dataclass
class ScoreCandidateResult:
    candidate_id: str
    scoring_run_id: str | None
    candidate_role_family: str
    total_relevant_jobs: int = 0
    scored_jobs: int = 0
    skipped_jobs: int = 0
    failed_jobs: int = 0
    top_matches: list[TopMatch] = field(default_factory=list)
    status: str = "completed"
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None
    errors: list[str] = field(default_factory=list)


# ── Public API ──────────────────────────────────────────────────────────


class ScoringService:
    """Coordinates the full scoring pipeline.

    The constructor accepts injectable dependencies so unit tests can swap
    in fakes (e.g. a fake LlamaAgent that doesn't hit OpenRouter).
    """

    def __init__(
        self,
        *,
        session_factory=SessionLocal,
        agent_callable=score_candidate_for_job,
        similarity_callable=compute_similarity_score,
    ) -> None:
        self._session_factory = session_factory
        self._agent_callable = agent_callable
        self._similarity_callable = similarity_callable

    # ── Multi-job entry point ──────────────────────────────────────────

    async def score_candidate(
        self,
        candidate_id: UUID,
        *,
        max_jobs: int | None = None,
        force_rescore: bool = False,
    ) -> ScoreCandidateResult:
        cap = settings.scoring_max_jobs_per_candidate
        if max_jobs is None:
            max_jobs = cap
        max_jobs = max(1, min(int(max_jobs), int(cap)))

        result = ScoreCandidateResult(
            candidate_id=str(candidate_id),
            scoring_run_id=None,
            candidate_role_family="other",
        )

        # ── Load candidate profile ─────────────────────────────────────
        load_session: Session = self._session_factory()
        try:
            profile = repo.get_candidate_profile(load_session, candidate_id)
            if profile is None:
                result.status = "failed"
                result.errors.append("candidate_not_found")
                result.finished_at = datetime.now(timezone.utc)
                return result
            cand_family = candidate_role_family(profile)
            result.candidate_role_family = cand_family
            active_jobs = repo.get_active_jobs(
                load_session, limit=max(50, max_jobs * 5),
            )
        finally:
            load_session.close()

        # ── Open scoring run ───────────────────────────────────────────
        run = self._open_run(
            candidate_id,
            metadata={
                "candidate_role_family": cand_family,
                "max_jobs": max_jobs,
                "force_rescore": force_rescore,
            },
        )
        if run is None:
            result.status = "failed"
            result.errors.append("could_not_create_scoring_run")
            result.finished_at = datetime.now(timezone.utc)
            return result
        result.scoring_run_id = str(run.id)

        relevant_pairs: list[tuple[JobFullProfile, RelevanceDecision, VectorSimilarityResult]] = []
        skipped = 0

        # ── First pass: relevance filter (no LLM calls yet) ───────────
        for job in active_jobs:
            if len(relevant_pairs) >= max_jobs:
                break

            job_session: Session = self._session_factory()
            try:
                job_profile = repo.get_job_profile(job_session, job.id)
                cand_profile = repo.get_candidate_profile(job_session, candidate_id)
            finally:
                job_session.close()
            if job_profile is None or cand_profile is None:
                skipped += 1
                continue

            # Compute vector similarity once — it feeds both relevance and final score
            sim = self._safe_vector_similarity(candidate_id, job.id)
            decision = assess_relevance(
                cand_profile,
                job_profile,
                candidate_family=cand_family,
                vector_similarity_score=sim.score,
            )
            if not decision.is_relevant:
                skipped += 1
                logger.debug(
                    "[Scoring] skipping irrelevant job %s — %s",
                    job.id, "; ".join(decision.reasons),
                )
                self._record_skipped(
                    run.id, candidate_id, job.id, decision, sim,
                )
                continue
            relevant_pairs.append((job_profile, decision, sim))

        result.total_relevant_jobs = len(relevant_pairs)
        result.skipped_jobs = skipped

        # ── Second pass: agent + final score (LLM calls happen here) ──
        if not relevant_pairs:
            result.status = "completed"
            self._close_run(run.id, result)
            result.finished_at = datetime.now(timezone.utc)
            return result

        async with httpx.AsyncClient(
            timeout=settings.scoring_request_timeout_seconds,
        ) as http_client:
            for job_profile, decision, sim in relevant_pairs:
                try:
                    score_row = await self._score_one_job(
                        candidate_id=candidate_id,
                        job_profile=job_profile,
                        decision=decision,
                        sim=sim,
                        scoring_run_id=run.id,
                        force_rescore=force_rescore,
                        http_client=http_client,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.exception(
                        "[Scoring] job %s failed catastrophically",
                        job_profile.job.id,
                    )
                    result.failed_jobs += 1
                    self._safe_log_error(
                        scoring_run_id=run.id,
                        candidate_id=candidate_id,
                        job_id=job_profile.job.id,
                        error_type="UnhandledScoringError",
                        error_message=str(exc),
                    )
                    continue

                if score_row is None:
                    result.failed_jobs += 1
                    continue

                result.scored_jobs += 1
                result.top_matches.append(
                    TopMatch(
                        job_id=str(job_profile.job.id),
                        job_title=job_profile.job.title,
                        company_name=(
                            job_profile.company.name
                            if job_profile.company
                            else job_profile.job.company_name
                        ),
                        agent_score=float(score_row.agent_score),
                        vector_similarity_score=float(score_row.vector_similarity_score),
                        final_score=float(score_row.final_score),
                        recommendation=score_row.recommendation or "",
                        match_classification=score_row.match_classification or "",
                    )
                )

                # Best-effort AGE edge. Failure does not delete the PG score.
                self._safe_sync_graph(
                    candidate_id=candidate_id,
                    job_id=job_profile.job.id,
                    score_row=score_row,
                )

        # Order matches by final score desc
        result.top_matches.sort(key=lambda m: m.final_score, reverse=True)
        result.status = "completed"
        if result.failed_jobs > 0 and result.scored_jobs == 0:
            result.status = "failed"
        self._close_run(run.id, result)
        result.finished_at = datetime.now(timezone.utc)
        return result

    # ── Single-job entry point (used by /candidates/{id}/jobs/{id}/score) ─

    async def score_candidate_against_job(
        self,
        candidate_id: UUID,
        job_id: UUID,
        *,
        force: bool = False,
    ) -> CandidateJobScore | None:
        load_session: Session = self._session_factory()
        try:
            cand_profile = repo.get_candidate_profile(load_session, candidate_id)
            job_profile = repo.get_job_profile(load_session, job_id)
        finally:
            load_session.close()
        if cand_profile is None or job_profile is None:
            return None

        sim = self._safe_vector_similarity(candidate_id, job_id)
        decision = assess_relevance(
            cand_profile,
            job_profile,
            vector_similarity_score=sim.score,
        )
        if not decision.is_relevant and not force:
            self._safe_log_error(
                scoring_run_id=None,
                candidate_id=candidate_id,
                job_id=job_id,
                error_type="SkippedIrrelevant",
                error_message=";".join(decision.reasons),
            )
            return None

        async with httpx.AsyncClient(
            timeout=settings.scoring_request_timeout_seconds,
        ) as http_client:
            return await self._score_one_job(
                candidate_id=candidate_id,
                job_profile=job_profile,
                decision=decision,
                sim=sim,
                scoring_run_id=None,
                force_rescore=force,
                http_client=http_client,
            )

    # ── Internal helpers ───────────────────────────────────────────────

    async def _score_one_job(
        self,
        *,
        candidate_id: UUID,
        job_profile: JobFullProfile,
        decision: RelevanceDecision,
        sim: VectorSimilarityResult,
        scoring_run_id: UUID | None,
        force_rescore: bool,
        http_client: httpx.AsyncClient,
    ) -> CandidateJobScore | None:
        # Reuse-or-rescore based on `force_rescore`
        if not force_rescore:
            existing = self._fetch_existing(candidate_id, job_profile.job.id)
            if existing is not None and existing.scoring_status in {
                "completed",
                "completed_with_vector_missing",
                "completed_with_graph_sync_failed",
            }:
                return existing

        # Build the anonymized payloads (NO protected attributes pass)
        anon_session: Session = self._session_factory()
        try:
            cand_profile = repo.get_candidate_profile(anon_session, candidate_id)
        finally:
            anon_session.close()
        if cand_profile is None:
            return None

        anon_candidate = anonymize_candidate(cand_profile, candidate_id=str(candidate_id))
        anon_job = anonymize_job(job_profile, job_id=str(job_profile.job.id))

        agent_outcome = await self._agent_callable(
            anonymized_candidate=anon_candidate,
            anonymized_job=anon_job,
            client=http_client,
        )
        if isinstance(agent_outcome, AgentScoreError):
            self._safe_log_error(
                scoring_run_id=scoring_run_id,
                candidate_id=candidate_id,
                job_id=job_profile.job.id,
                error_type=agent_outcome.error_type,
                error_message=agent_outcome.error_message,
                metadata={"model": agent_outcome.model_name},
            )
            return None

        final_score = combine_scores(
            agent_outcome.agent_score,
            sim.score,
            agent_weight=settings.scoring_agent_weight,
            vector_weight=settings.scoring_vector_weight,
        )

        scoring_status = (
            "completed_with_vector_missing"
            if sim.status == "completed_with_vector_missing"
            else "completed"
        )

        # Persist
        score_data = {
            "candidate_id": candidate_id,
            "job_id": job_profile.job.id,
            "agent_score": float(agent_outcome.agent_score),
            "vector_similarity_score": float(sim.score),
            "final_score": float(final_score),
            "relevance_score": float(decision.relevance_score),
            "role_family": decision.candidate_role_family,
            "match_classification": classify_final_score(final_score),
            "criteria_breakdown": agent_outcome.criteria_breakdown,
            "matched_skills": agent_outcome.matched_skills,
            "missing_required_skills": agent_outcome.missing_required_skills,
            "missing_preferred_skills": agent_outcome.missing_preferred_skills,
            "strengths": agent_outcome.strengths,
            "weaknesses": agent_outcome.weaknesses,
            "explanation": agent_outcome.explanation,
            "recommendation": agent_outcome.recommendation
            or recommendation_for(final_score),
            "confidence": float(agent_outcome.confidence),
            "model_name": agent_outcome.model_name,
            "prompt_version": settings.scoring_prompt_version,
            "scoring_status": scoring_status,
        }
        return self._persist_score(score_data)

    def _persist_score(self, score_data: dict[str, Any]) -> CandidateJobScore | None:
        session: Session = self._session_factory()
        try:
            row = repo.upsert_candidate_job_score(session, score_data)
            session.commit()
            return row
        except Exception:
            session.rollback()
            logger.exception(
                "[Scoring] failed to persist score for candidate=%s job=%s",
                score_data.get("candidate_id"), score_data.get("job_id"),
            )
            return None
        finally:
            session.close()

    def _fetch_existing(
        self, candidate_id: UUID, job_id: UUID,
    ) -> CandidateJobScore | None:
        session: Session = self._session_factory()
        try:
            return repo.get_existing_score(session, candidate_id, job_id)
        finally:
            session.close()

    def _safe_vector_similarity(
        self, candidate_id: UUID, job_id: UUID,
    ) -> VectorSimilarityResult:
        try:
            return self._similarity_callable(candidate_id, job_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[Scoring] vector similarity call failed for %s/%s: %s",
                candidate_id, job_id, exc,
            )
            return VectorSimilarityResult(
                score=0.0,
                cosine=None,
                candidate_vector_present=False,
                job_vector_present=False,
                status="completed_with_vector_missing",
            )

    # ── Run lifecycle wrappers ─────────────────────────────────────────

    def _open_run(
        self, candidate_id: UUID, *, metadata: dict[str, Any],
    ) -> ScoringRun | None:
        session: Session = self._session_factory()
        try:
            run = repo.create_scoring_run(session, candidate_id, metadata=metadata)
            session.commit()
            session.refresh(run)
            return run
        except Exception:
            session.rollback()
            logger.exception("[Scoring] could not open scoring_runs row")
            return None
        finally:
            session.close()

    def _close_run(
        self, run_id: UUID, result: ScoreCandidateResult,
    ) -> None:
        session: Session = self._session_factory()
        try:
            run = session.get(ScoringRun, run_id)
            if run is None:
                return
            repo.finish_scoring_run(
                session,
                run,
                status=result.status,
                counts={
                    "total_relevant_jobs": result.total_relevant_jobs,
                    "scored_jobs": result.scored_jobs,
                    "skipped_jobs": result.skipped_jobs,
                    "failed_jobs": result.failed_jobs,
                },
                error_message="; ".join(result.errors[:5]) or None,
                metadata={
                    "candidate_role_family": result.candidate_role_family,
                    "top_matches": [
                        {
                            "job_id": m.job_id,
                            "final_score": m.final_score,
                            "recommendation": m.recommendation,
                        }
                        for m in result.top_matches[:10]
                    ],
                },
            )
            session.commit()
        except Exception:
            session.rollback()
            logger.exception("[Scoring] failed to finalize scoring_runs row")
        finally:
            session.close()

    def _record_skipped(
        self,
        run_id: UUID | None,
        candidate_id: UUID,
        job_id: UUID,
        decision: RelevanceDecision,
        sim: VectorSimilarityResult,
    ) -> None:
        session: Session = self._session_factory()
        try:
            repo.log_scoring_error(
                session,
                scoring_run_id=run_id,
                candidate_id=candidate_id,
                job_id=job_id,
                error_type="skipped_irrelevant",
                error_message=";".join(decision.reasons)[:1000],
                metadata={
                    "candidate_role_family": decision.candidate_role_family,
                    "job_role_family": decision.job_role_family,
                    "skill_overlap_ratio": decision.skill_overlap_ratio,
                    "vector_similarity_score": decision.vector_similarity_score,
                    "vector_status": sim.status,
                },
            )
            session.commit()
        except Exception:
            session.rollback()

    def _safe_log_error(
        self,
        *,
        scoring_run_id: UUID | None,
        candidate_id: UUID | None,
        job_id: UUID | None,
        error_type: str,
        error_message: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        session: Session = self._session_factory()
        try:
            repo.log_scoring_error(
                session,
                scoring_run_id=scoring_run_id,
                candidate_id=candidate_id,
                job_id=job_id,
                error_type=error_type,
                error_message=error_message,
                metadata=metadata,
            )
            session.commit()
        except Exception:
            session.rollback()

    # ── AGE MATCHES_JOB edge sync (best-effort) ────────────────────────

    def _safe_sync_graph(
        self,
        *,
        candidate_id: UUID,
        job_id: UUID,
        score_row: CandidateJobScore,
    ) -> None:
        session: Session = self._session_factory()
        try:
            ensure_graph(session)
            cypher = """
            MERGE (c:Candidate {candidate_id: $candidate_id})
            MERGE (j:Job {job_id: $job_id})
            MERGE (c)-[m:MATCHES_JOB]->(j)
            SET m.final_score = $final_score,
                m.agent_score = $agent_score,
                m.vector_similarity_score = $vector_similarity_score,
                m.recommendation = $recommendation,
                m.match_classification = $match_classification,
                m.updated_at = $updated_at
            RETURN m
            """
            run_cypher(
                session,
                cypher,
                {
                    "candidate_id": str(candidate_id),
                    "job_id": str(job_id),
                    "final_score": float(score_row.final_score),
                    "agent_score": float(score_row.agent_score),
                    "vector_similarity_score": float(score_row.vector_similarity_score),
                    "recommendation": score_row.recommendation or "",
                    "match_classification": score_row.match_classification or "",
                    "updated_at": (
                        score_row.updated_at or score_row.created_at
                    ).isoformat(),
                },
            )
            session.commit()
        except Exception:  # noqa: BLE001
            session.rollback()
            logger.exception(
                "[Scoring] AGE MATCHES_JOB sync failed for %s/%s — keeping PG score",
                candidate_id, job_id,
            )
            # Mark the row but never delete it
            try:
                update_session: Session = self._session_factory()
                refreshed = update_session.get(CandidateJobScore, score_row.id)
                if refreshed is not None:
                    refreshed.scoring_status = "completed_with_graph_sync_failed"
                    update_session.commit()
                update_session.close()
            except Exception:  # noqa: BLE001
                logger.exception("[Scoring] could not flag graph-sync-failed status")
        finally:
            session.close()


# ── Final-score helper ───────────────────────────────────────────────────


def combine_scores(
    agent_score: float,
    vector_similarity_score: float,
    *,
    agent_weight: float | None = None,
    vector_weight: float | None = None,
) -> float:
    """Combine the two component scores into a final 0–100 number.

    The weights are renormalized to sum to 1.0 so misconfigured env
    variables can never produce > 100 results.
    """
    a_w = settings.scoring_agent_weight if agent_weight is None else agent_weight
    v_w = settings.scoring_vector_weight if vector_weight is None else vector_weight
    total = a_w + v_w
    if total <= 0:
        a_w, v_w = 0.65, 0.35
        total = 1.0
    a_w /= total
    v_w /= total
    raw = (float(agent_score) * a_w) + (float(vector_similarity_score) * v_w)
    return round(max(0.0, min(100.0, raw)), 3)


__all__ = [
    "ScoreCandidateResult",
    "ScoringService",
    "TopMatch",
    "combine_scores",
]
