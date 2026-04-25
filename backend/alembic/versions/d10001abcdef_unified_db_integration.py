"""unified database integration: companies, locations, candidate extras, sync, audit, matches

Revision ID: d10001abcdef
Revises: 80a2c3cb4e2f
Create Date: 2026-04-25 21:00:00.000000

This migration is purely additive. It adds the spec-required tables for the
unified PostgreSQL <-> Apache AGE <-> Qdrant integration without dropping or
renaming any existing tables or columns.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d10001abcdef"
down_revision: Union[str, None] = "80a2c3cb4e2f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── companies ───────────────────────────────────────────────────────
    op.create_table(
        "companies",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("normalized_name", sa.String(length=255), nullable=False),
        sa.Column("website_url", sa.String(length=1024), nullable=True),
        sa.Column("industry", sa.String(length=255), nullable=True),
        sa.Column("country", sa.String(length=100), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("normalized_name", name="uq_companies_normalized_name"),
    )
    op.create_index(
        "ix_companies_normalized_name", "companies", ["normalized_name"], unique=False,
    )

    # ── locations ───────────────────────────────────────────────────────
    op.create_table(
        "locations",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("country", sa.String(length=100), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=True),
        sa.Column("region", sa.String(length=100), nullable=True),
        sa.Column("remote_type", sa.String(length=50), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── candidate_contacts ─────────────────────────────────────────────
    op.create_table(
        "candidate_contacts",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("contact_type", sa.String(length=50), nullable=False),
        sa.Column("contact_value", sa.String(length=1024), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("confidence", sa.Numeric(5, 2), nullable=True),
        sa.Column("source", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "candidate_id", "contact_type", "contact_value",
            name="uq_candidate_contact_value",
        ),
    )
    op.create_index(
        "ix_candidate_contacts_candidate_id",
        "candidate_contacts",
        ["candidate_id"],
        unique=False,
    )

    # ── candidate_projects ─────────────────────────────────────────────
    op.create_table(
        "candidate_projects",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("project_url", sa.String(length=1024), nullable=True),
        sa.Column("repository_url", sa.String(length=1024), nullable=True),
        sa.Column("technologies", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("start_date", sa.String(length=50), nullable=True),
        sa.Column("end_date", sa.String(length=50), nullable=True),
        sa.Column("source", sa.String(length=100), nullable=True),
        sa.Column("confidence", sa.Numeric(5, 2), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_candidate_projects_candidate_id",
        "candidate_projects",
        ["candidate_id"],
        unique=False,
    )

    # ── candidate_links ────────────────────────────────────────────────
    op.create_table(
        "candidate_links",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("link_type", sa.String(length=50), nullable=False),
        sa.Column("url", sa.String(length=1024), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_candidate_links_candidate_id",
        "candidate_links",
        ["candidate_id"],
        unique=False,
    )

    # ── db_sync_status ─────────────────────────────────────────────────
    op.create_table(
        "db_sync_status",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("entity_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "graph_sync_status",
            sa.String(length=50),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "vector_sync_status",
            sa.String(length=50),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("graph_last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("vector_last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("graph_error", sa.Text(), nullable=True),
        sa.Column("vector_error", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_hash", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("entity_type", "entity_id", name="uq_db_sync_entity"),
    )
    op.create_index(
        "ix_db_sync_status_entity_type",
        "db_sync_status",
        ["entity_type"],
        unique=False,
    )
    op.create_index(
        "ix_db_sync_status_entity_id",
        "db_sync_status",
        ["entity_id"],
        unique=False,
    )

    # ── audit_logs ─────────────────────────────────────────────────────
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("entity_type", sa.String(length=100), nullable=False),
        sa.Column("entity_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("old_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("new_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"], unique=False)
    op.create_index(
        "ix_audit_logs_entity_type", "audit_logs", ["entity_type"], unique=False,
    )
    op.create_index(
        "ix_audit_logs_entity_id", "audit_logs", ["entity_id"], unique=False,
    )

    # ── candidate_job_matches ──────────────────────────────────────────
    op.create_table(
        "candidate_job_matches",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("application_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("overall_score", sa.Numeric(6, 3), nullable=True),
        sa.Column("skill_score", sa.Numeric(6, 3), nullable=True),
        sa.Column("experience_score", sa.Numeric(6, 3), nullable=True),
        sa.Column("education_score", sa.Numeric(6, 3), nullable=True),
        sa.Column("semantic_score", sa.Numeric(6, 3), nullable=True),
        sa.Column("graph_score", sa.Numeric(6, 3), nullable=True),
        sa.Column("fairness_adjusted_score", sa.Numeric(6, 3), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("model_version", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"]),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "candidate_id", "job_id", "model_version",
            name="uq_match_candidate_job_model",
        ),
    )
    op.create_index(
        "ix_candidate_job_matches_candidate_id",
        "candidate_job_matches",
        ["candidate_id"],
        unique=False,
    )
    op.create_index(
        "ix_candidate_job_matches_job_id",
        "candidate_job_matches",
        ["job_id"],
        unique=False,
    )

    # ── Ensure AGE extension exists (idempotent, safe) ─────────────────
    op.execute("CREATE EXTENSION IF NOT EXISTS age;")


def downgrade() -> None:
    op.drop_index("ix_candidate_job_matches_job_id", table_name="candidate_job_matches")
    op.drop_index(
        "ix_candidate_job_matches_candidate_id", table_name="candidate_job_matches",
    )
    op.drop_table("candidate_job_matches")

    op.drop_index("ix_audit_logs_entity_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_entity_type", table_name="audit_logs")
    op.drop_index("ix_audit_logs_action", table_name="audit_logs")
    op.drop_table("audit_logs")

    op.drop_index("ix_db_sync_status_entity_id", table_name="db_sync_status")
    op.drop_index("ix_db_sync_status_entity_type", table_name="db_sync_status")
    op.drop_table("db_sync_status")

    op.drop_index("ix_candidate_links_candidate_id", table_name="candidate_links")
    op.drop_table("candidate_links")

    op.drop_index("ix_candidate_projects_candidate_id", table_name="candidate_projects")
    op.drop_table("candidate_projects")

    op.drop_index("ix_candidate_contacts_candidate_id", table_name="candidate_contacts")
    op.drop_table("candidate_contacts")

    op.drop_table("locations")

    op.drop_index("ix_companies_normalized_name", table_name="companies")
    op.drop_table("companies")
