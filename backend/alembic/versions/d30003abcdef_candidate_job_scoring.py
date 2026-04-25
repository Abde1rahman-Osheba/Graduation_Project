"""candidate-job scoring tables

Revision ID: d30003abcdef
Revises: d20002cdef012
Create Date: 2026-04-25 23:30:00.000000

Adds the spec-required tables that back the LlamaAgent scoring service:

  - candidate_job_scores  — per (candidate, job) saved match
  - scoring_runs          — one row per scoring execution
  - scoring_errors        — per-job failures captured during a run
  - scoring_criteria      — optional admin-overridable criteria

The legacy `candidate_job_matches` table (general-purpose multi-score
record) is intentionally NOT modified.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d30003abcdef"
down_revision: Union[str, None] = "d20002cdef012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "candidate_job_scores",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_score", sa.Numeric(6, 3), nullable=False),
        sa.Column("vector_similarity_score", sa.Numeric(6, 3), nullable=False),
        sa.Column("final_score", sa.Numeric(6, 3), nullable=False),
        sa.Column("relevance_score", sa.Numeric(6, 3), nullable=True),
        sa.Column("role_family", sa.String(length=80), nullable=True),
        sa.Column("match_classification", sa.String(length=50), nullable=True),
        sa.Column("criteria_breakdown", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("matched_skills", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("missing_required_skills", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("missing_preferred_skills", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("strengths", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("weaknesses", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("recommendation", sa.String(length=50), nullable=True),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=True),
        sa.Column("model_name", sa.String(length=255), nullable=True),
        sa.Column("prompt_version", sa.String(length=20), nullable=False, server_default="v1"),
        sa.Column("scoring_status", sa.String(length=50), nullable=False, server_default="completed"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("candidate_id", "job_id", name="uq_candidate_job_score"),
    )
    op.create_index(
        "ix_candidate_job_scores_candidate_id",
        "candidate_job_scores",
        ["candidate_id"],
        unique=False,
    )
    op.create_index(
        "ix_candidate_job_scores_job_id",
        "candidate_job_scores",
        ["job_id"],
        unique=False,
    )
    op.create_index(
        "ix_candidate_job_scores_final_score",
        "candidate_job_scores",
        ["final_score"],
        unique=False,
    )

    op.create_table(
        "scoring_runs",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_relevant_jobs", sa.Integer(), server_default="0"),
        sa.Column("scored_jobs", sa.Integer(), server_default="0"),
        sa.Column("skipped_jobs", sa.Integer(), server_default="0"),
        sa.Column("failed_jobs", sa.Integer(), server_default="0"),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="running"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_scoring_runs_candidate_id", "scoring_runs", ["candidate_id"], unique=False,
    )
    op.create_index(
        "ix_scoring_runs_started_at", "scoring_runs", ["started_at"], unique=False,
    )

    op.create_table(
        "scoring_errors",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("scoring_run_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("candidate_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("job_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("error_type", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["scoring_run_id"], ["scoring_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_scoring_errors_scoring_run_id",
        "scoring_errors",
        ["scoring_run_id"],
        unique=False,
    )

    op.create_table(
        "scoring_criteria",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("weight", sa.Numeric(6, 3), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_scoring_criteria_name"),
    )


def downgrade() -> None:
    op.drop_table("scoring_criteria")
    op.drop_index("ix_scoring_errors_scoring_run_id", table_name="scoring_errors")
    op.drop_table("scoring_errors")
    op.drop_index("ix_scoring_runs_started_at", table_name="scoring_runs")
    op.drop_index("ix_scoring_runs_candidate_id", table_name="scoring_runs")
    op.drop_table("scoring_runs")
    op.drop_index("ix_candidate_job_scores_final_score", table_name="candidate_job_scores")
    op.drop_index("ix_candidate_job_scores_job_id", table_name="candidate_job_scores")
    op.drop_index("ix_candidate_job_scores_candidate_id", table_name="candidate_job_scores")
    op.drop_table("candidate_job_scores")
