"""job scraper import tables and jobs spec columns

Revision ID: d20002cdef012
Revises: d10001abcdef
Create Date: 2026-04-25 22:00:00.000000

This migration is purely additive. It augments the `jobs` table with
the spec-required columns and creates the new tables that back the
hourly Job_Scraper-main import pipeline:

  - job_skills           (canonical job ↔ skill link table)
  - job_requirements     (free-text requirement bullets)
  - job_responsibilities (free-text responsibility bullets)
  - job_import_runs      (one row per scheduler run)
  - job_import_errors    (per-record import failures)
  - job_scraper_state    (rolling cursor over the company list)

No existing tables, columns or constraints are removed.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d20002cdef012"
down_revision: Union[str, None] = "d10001abcdef"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── jobs: add spec columns ──────────────────────────────────────────
    op.add_column("jobs", sa.Column("source_platform", sa.String(length=50), nullable=True))
    op.create_index("ix_jobs_source_platform", "jobs", ["source_platform"], unique=False)
    op.add_column("jobs", sa.Column("source_external_id", sa.String(length=255), nullable=True))

    op.add_column("jobs", sa.Column("company_id", sa.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_jobs_company_id_companies", "jobs", "companies", ["company_id"], ["id"],
    )
    op.create_index("ix_jobs_company_id", "jobs", ["company_id"], unique=False)

    op.add_column("jobs", sa.Column("summary", sa.Text(), nullable=True))
    op.add_column("jobs", sa.Column("min_years_experience", sa.Integer(), nullable=True))
    op.add_column("jobs", sa.Column("max_years_experience", sa.Integer(), nullable=True))
    op.add_column("jobs", sa.Column("workplace_type", sa.String(length=20), nullable=True))
    op.add_column("jobs", sa.Column("scraped_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "jobs",
        sa.Column("graph_sync_status", sa.String(length=20), nullable=True, server_default="pending"),
    )
    op.add_column(
        "jobs",
        sa.Column("vector_sync_status", sa.String(length=20), nullable=True, server_default="pending"),
    )
    op.add_column("jobs", sa.Column("last_graph_sync_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("jobs", sa.Column("last_vector_sync_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("jobs", sa.Column("last_imported_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("jobs", sa.Column("text_hash", sa.String(length=128), nullable=True))

    # Composite uniqueness on (source_platform, source_url) per spec
    op.create_index(
        "ux_jobs_source_platform_url",
        "jobs",
        ["source_platform", "source_url"],
        unique=True,
        postgresql_where=sa.text("source_platform IS NOT NULL AND source_url IS NOT NULL"),
    )

    # ── job_skills ─────────────────────────────────────────────────────
    op.create_table(
        "job_skills",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("skill_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("requirement_type", sa.String(length=20), nullable=False),
        sa.Column("importance_score", sa.Numeric(6, 3), nullable=True, server_default="1.0"),
        sa.Column("years_required", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "job_id", "skill_id", "requirement_type",
            name="uq_job_skill_requirement",
        ),
    )
    op.create_index("ix_job_skills_job_id", "job_skills", ["job_id"], unique=False)
    op.create_index("ix_job_skills_skill_id", "job_skills", ["skill_id"], unique=False)

    # ── job_requirements ───────────────────────────────────────────────
    op.create_table(
        "job_requirements",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("requirement_text", sa.Text(), nullable=False),
        sa.Column(
            "requirement_type",
            sa.String(length=50),
            nullable=False,
            server_default="general",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_job_requirements_job_id", "job_requirements", ["job_id"], unique=False,
    )

    # ── job_responsibilities ───────────────────────────────────────────
    op.create_table(
        "job_responsibilities",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("responsibility_text", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_job_responsibilities_job_id",
        "job_responsibilities",
        ["job_id"],
        unique=False,
    )

    # ── job_import_runs ────────────────────────────────────────────────
    op.create_table(
        "job_import_runs",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("source_platform", sa.String(length=50), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("requested_limit", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("scraped_count", sa.Integer(), server_default="0"),
        sa.Column("valid_count", sa.Integer(), server_default="0"),
        sa.Column("inserted_count", sa.Integer(), server_default="0"),
        sa.Column("updated_count", sa.Integer(), server_default="0"),
        sa.Column("skipped_count", sa.Integer(), server_default="0"),
        sa.Column("failed_count", sa.Integer(), server_default="0"),
        sa.Column("graph_synced_count", sa.Integer(), server_default="0"),
        sa.Column("vector_synced_count", sa.Integer(), server_default="0"),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="running"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_job_import_runs_started_at",
        "job_import_runs",
        ["started_at"],
        unique=False,
    )

    # ── job_import_errors ──────────────────────────────────────────────
    op.create_table(
        "job_import_errors",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("import_run_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("source_platform", sa.String(length=50), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("job_title", sa.String(length=500), nullable=True),
        sa.Column("company_name", sa.String(length=500), nullable=True),
        sa.Column("error_type", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["import_run_id"], ["job_import_runs.id"], ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_job_import_errors_import_run_id",
        "job_import_errors",
        ["import_run_id"],
        unique=False,
    )

    # ── job_scraper_state ──────────────────────────────────────────────
    op.create_table(
        "job_scraper_state",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("source_platform", sa.String(length=50), nullable=False),
        sa.Column("company_offset", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_imported_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_platform", name="uq_job_scraper_state_source"),
    )
    op.create_index(
        "ix_job_scraper_state_source_platform",
        "job_scraper_state",
        ["source_platform"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_job_scraper_state_source_platform", table_name="job_scraper_state")
    op.drop_table("job_scraper_state")

    op.drop_index("ix_job_import_errors_import_run_id", table_name="job_import_errors")
    op.drop_table("job_import_errors")

    op.drop_index("ix_job_import_runs_started_at", table_name="job_import_runs")
    op.drop_table("job_import_runs")

    op.drop_index("ix_job_responsibilities_job_id", table_name="job_responsibilities")
    op.drop_table("job_responsibilities")

    op.drop_index("ix_job_requirements_job_id", table_name="job_requirements")
    op.drop_table("job_requirements")

    op.drop_index("ix_job_skills_skill_id", table_name="job_skills")
    op.drop_index("ix_job_skills_job_id", table_name="job_skills")
    op.drop_table("job_skills")

    op.drop_index("ux_jobs_source_platform_url", table_name="jobs")
    op.drop_column("jobs", "text_hash")
    op.drop_column("jobs", "last_imported_at")
    op.drop_column("jobs", "last_vector_sync_at")
    op.drop_column("jobs", "last_graph_sync_at")
    op.drop_column("jobs", "vector_sync_status")
    op.drop_column("jobs", "graph_sync_status")
    op.drop_column("jobs", "scraped_at")
    op.drop_column("jobs", "workplace_type")
    op.drop_column("jobs", "max_years_experience")
    op.drop_column("jobs", "min_years_experience")
    op.drop_column("jobs", "summary")
    op.drop_index("ix_jobs_company_id", table_name="jobs")
    op.drop_constraint("fk_jobs_company_id_companies", "jobs", type_="foreignkey")
    op.drop_column("jobs", "company_id")
    op.drop_column("jobs", "source_external_id")
    op.drop_index("ix_jobs_source_platform", table_name="jobs")
    op.drop_column("jobs", "source_platform")
