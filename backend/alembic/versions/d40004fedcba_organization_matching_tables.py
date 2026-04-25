"""organization-side matching, anonymization & outreach tables

Revision ID: d40004fedcba
Revises: d30003abcdef
Create Date: 2026-04-25 23:55:00.000000

Adds the 7 spec-required tables that back the organization-side
candidate-search + outreach workflow:

  - organization_job_requests
  - organization_matching_runs
  - organization_candidate_imports
  - organization_candidate_import_errors
  - organization_blind_candidate_maps
  - organization_candidate_rankings
  - organization_outreach_messages

Purely additive — no existing tables are touched.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d40004fedcba"
down_revision: Union[str, None] = "d30003abcdef"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── organization_job_requests ───────────────────────────────────────
    op.create_table(
        "organization_job_requests",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("responsibilities", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("requirements", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("required_skills", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("preferred_skills", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("education_requirements", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("min_years_experience", sa.Integer(), nullable=True),
        sa.Column("max_years_experience", sa.Integer(), nullable=True),
        sa.Column("seniority_level", sa.String(length=50), nullable=True),
        sa.Column("location_text", sa.String(length=255), nullable=True),
        sa.Column("workplace_type", sa.String(length=20), nullable=True),
        sa.Column("employment_type", sa.String(length=50), nullable=True),
        sa.Column("salary_min", sa.Numeric(12, 2), nullable=True),
        sa.Column("salary_max", sa.Numeric(12, 2), nullable=True),
        sa.Column("salary_currency", sa.String(length=10), nullable=True),
        sa.Column("role_family", sa.String(length=80), nullable=True),
        sa.Column("top_k", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("source_type", sa.String(length=50), nullable=False, server_default="manual"),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="created"),
        sa.Column("created_by", sa.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_org_job_requests_organization_id",
        "organization_job_requests",
        ["organization_id"],
    )
    op.create_index(
        "ix_org_job_requests_job_id",
        "organization_job_requests",
        ["job_id"],
    )

    # ── organization_matching_runs ──────────────────────────────────────
    op.create_table(
        "organization_matching_runs",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("job_request_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("job_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("path_type", sa.String(length=50), nullable=False),
        sa.Column("top_k", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("total_candidates", sa.Integer(), server_default="0"),
        sa.Column("relevant_candidates", sa.Integer(), server_default="0"),
        sa.Column("scored_candidates", sa.Integer(), server_default="0"),
        sa.Column("shortlisted_candidates", sa.Integer(), server_default="0"),
        sa.Column("failed_candidates", sa.Integer(), server_default="0"),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="running"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "path_type IN ('database_search', 'csv_candidate_list')",
            name="ck_org_matching_run_path_type",
        ),
        sa.ForeignKeyConstraint(
            ["job_request_id"], ["organization_job_requests.id"], ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_org_matching_runs_organization_id",
        "organization_matching_runs",
        ["organization_id"],
    )
    op.create_index(
        "ix_org_matching_runs_job_request_id",
        "organization_matching_runs",
        ["job_request_id"],
    )
    op.create_index(
        "ix_org_matching_runs_started_at",
        "organization_matching_runs",
        ["started_at"],
    )

    # ── organization_candidate_imports ──────────────────────────────────
    op.create_table(
        "organization_candidate_imports",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("matching_run_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("file_name", sa.String(length=500), nullable=True),
        sa.Column("total_rows", sa.Integer(), server_default="0"),
        sa.Column("valid_rows", sa.Integer(), server_default="0"),
        sa.Column("imported_candidates", sa.Integer(), server_default="0"),
        sa.Column("updated_candidates", sa.Integer(), server_default="0"),
        sa.Column("failed_rows", sa.Integer(), server_default="0"),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="running"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["matching_run_id"], ["organization_matching_runs.id"], ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_org_candidate_imports_matching_run_id",
        "organization_candidate_imports",
        ["matching_run_id"],
    )

    # ── organization_candidate_import_errors ────────────────────────────
    op.create_table(
        "organization_candidate_import_errors",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("import_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("matching_run_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("row_number", sa.Integer(), nullable=True),
        sa.Column("cv_url", sa.Text(), nullable=True),
        sa.Column("error_type", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("raw_row", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["import_id"], ["organization_candidate_imports.id"], ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["matching_run_id"], ["organization_matching_runs.id"], ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_org_candidate_import_errors_import_id",
        "organization_candidate_import_errors",
        ["import_id"],
    )

    # ── organization_blind_candidate_maps ───────────────────────────────
    op.create_table(
        "organization_blind_candidate_maps",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("matching_run_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("blind_candidate_id", sa.String(length=80), nullable=False),
        sa.Column("de_anonymized", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("de_anonymized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("de_anonymized_by", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("de_anonymization_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["matching_run_id"], ["organization_matching_runs.id"], ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"], ["candidates.id"], ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "matching_run_id", "candidate_id",
            name="uq_org_blind_run_candidate",
        ),
        sa.UniqueConstraint(
            "matching_run_id", "blind_candidate_id",
            name="uq_org_blind_run_blind_id",
        ),
    )
    op.create_index(
        "ix_org_blind_candidate_maps_run",
        "organization_blind_candidate_maps",
        ["matching_run_id"],
    )

    # ── organization_candidate_rankings ─────────────────────────────────
    op.create_table(
        "organization_candidate_rankings",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("matching_run_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("job_request_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("job_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("candidate_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("blind_candidate_id", sa.String(length=80), nullable=False),
        sa.Column("rank_position", sa.Integer(), nullable=True),
        sa.Column("agent_score", sa.Numeric(6, 3), nullable=False),
        sa.Column("vector_similarity_score", sa.Numeric(6, 3), nullable=False),
        sa.Column("final_score", sa.Numeric(6, 3), nullable=False),
        sa.Column("relevance_score", sa.Numeric(6, 3), nullable=True),
        sa.Column("criteria_breakdown", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("matched_skills", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("missing_required_skills", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("missing_preferred_skills", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("strengths", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("weaknesses", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("recommendation", sa.String(length=50), nullable=True),
        sa.Column("match_classification", sa.String(length=50), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="ranked"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["matching_run_id"], ["organization_matching_runs.id"], ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["job_request_id"], ["organization_job_requests.id"], ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "matching_run_id", "candidate_id",
            name="uq_org_ranking_run_candidate",
        ),
    )
    op.create_index(
        "ix_org_candidate_rankings_run", "organization_candidate_rankings",
        ["matching_run_id"],
    )
    op.create_index(
        "ix_org_candidate_rankings_final_score",
        "organization_candidate_rankings",
        ["final_score"],
    )

    # ── organization_outreach_messages ──────────────────────────────────
    op.create_table(
        "organization_outreach_messages",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("matching_run_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("ranking_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("job_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("candidate_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("blind_candidate_id", sa.String(length=80), nullable=False),
        sa.Column("recipient_email", sa.String(length=320), nullable=True),
        sa.Column("subject", sa.String(length=500), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("booking_link", sa.Text(), nullable=True),
        sa.Column("reply_deadline_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="draft"),
        sa.Column("provider", sa.String(length=50), nullable=True),
        sa.Column("provider_message_id", sa.String(length=255), nullable=True),
        sa.Column("approved_by", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["matching_run_id"], ["organization_matching_runs.id"], ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["ranking_id"], ["organization_candidate_rankings.id"], ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["candidate_id"], ["candidates.id"], ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_org_outreach_messages_run",
        "organization_outreach_messages",
        ["matching_run_id"],
    )
    op.create_index(
        "ix_org_outreach_messages_status",
        "organization_outreach_messages",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_org_outreach_messages_status", table_name="organization_outreach_messages",
    )
    op.drop_index(
        "ix_org_outreach_messages_run", table_name="organization_outreach_messages",
    )
    op.drop_table("organization_outreach_messages")

    op.drop_index(
        "ix_org_candidate_rankings_final_score",
        table_name="organization_candidate_rankings",
    )
    op.drop_index(
        "ix_org_candidate_rankings_run", table_name="organization_candidate_rankings",
    )
    op.drop_table("organization_candidate_rankings")

    op.drop_index(
        "ix_org_blind_candidate_maps_run",
        table_name="organization_blind_candidate_maps",
    )
    op.drop_table("organization_blind_candidate_maps")

    op.drop_index(
        "ix_org_candidate_import_errors_import_id",
        table_name="organization_candidate_import_errors",
    )
    op.drop_table("organization_candidate_import_errors")

    op.drop_index(
        "ix_org_candidate_imports_matching_run_id",
        table_name="organization_candidate_imports",
    )
    op.drop_table("organization_candidate_imports")

    op.drop_index(
        "ix_org_matching_runs_started_at", table_name="organization_matching_runs",
    )
    op.drop_index(
        "ix_org_matching_runs_job_request_id", table_name="organization_matching_runs",
    )
    op.drop_index(
        "ix_org_matching_runs_organization_id", table_name="organization_matching_runs",
    )
    op.drop_table("organization_matching_runs")

    op.drop_index(
        "ix_org_job_requests_job_id", table_name="organization_job_requests",
    )
    op.drop_index(
        "ix_org_job_requests_organization_id",
        table_name="organization_job_requests",
    )
    op.drop_table("organization_job_requests")
