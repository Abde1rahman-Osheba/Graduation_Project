"""decision support system (DSS) tables

Revision ID: f60006dss
Revises: e50005intintel
Create Date: 2026-04-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "f60006dss"
down_revision: Union[str, None] = "e50005intintel"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "decision_support_packets",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("job_id", sa.UUID(), nullable=False),
        sa.Column("candidate_id", sa.UUID(), nullable=False),
        sa.Column("application_id", sa.UUID(), nullable=False),
        sa.Column("generated_by_agent", sa.String(120), nullable=True),
        sa.Column("model_provider", sa.String(64), nullable=True),
        sa.Column("model_name", sa.String(200), nullable=True),
        sa.Column("final_journey_score", sa.Float(), nullable=True),
        sa.Column("recommendation", sa.String(80), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("packet_json", postgresql.JSONB(), nullable=False),
        sa.Column("evidence_json", postgresql.JSONB(), nullable=True),
        sa.Column("compliance_status", sa.String(32), nullable=True),
        sa.Column("human_review_required", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_dss_packets_org", "decision_support_packets", ["organization_id"])
    op.create_index("ix_dss_packets_app", "decision_support_packets", ["application_id"])
    op.create_index("ix_dss_packets_cand", "decision_support_packets", ["candidate_id"])
    op.create_index("ix_dss_packets_job", "decision_support_packets", ["job_id"])

    op.create_table(
        "decision_score_breakdowns",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("decision_packet_id", sa.UUID(), nullable=False),
        sa.Column("candidate_job_match_score", sa.Float(), nullable=True),
        sa.Column("assessment_score", sa.Float(), nullable=True),
        sa.Column("technical_interview_score", sa.Float(), nullable=True),
        sa.Column("hr_interview_score", sa.Float(), nullable=True),
        sa.Column("experience_alignment_score", sa.Float(), nullable=True),
        sa.Column("evidence_confidence_score", sa.Float(), nullable=True),
        sa.Column("final_journey_score", sa.Float(), nullable=True),
        sa.Column("scoring_formula_version", sa.String(32), nullable=False),
        sa.Column("explanation_json", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["decision_packet_id"], ["decision_support_packets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_dss_score_breakdown_packet", "decision_score_breakdowns", ["decision_packet_id"])

    op.create_table(
        "hr_final_decisions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("decision_packet_id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("job_id", sa.UUID(), nullable=False),
        sa.Column("candidate_id", sa.UUID(), nullable=False),
        sa.Column("application_id", sa.UUID(), nullable=False),
        sa.Column("decided_by_user_id", sa.UUID(), nullable=False),
        sa.Column("ai_recommendation", sa.Text(), nullable=True),
        sa.Column("final_hr_decision", sa.String(64), nullable=False),
        sa.Column("override_reason", sa.Text(), nullable=True),
        sa.Column("hr_notes", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["decision_packet_id"], ["decision_support_packets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["decided_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_hr_final_decisions_packet", "hr_final_decisions", ["decision_packet_id"])
    op.create_index("ix_hr_final_decisions_app", "hr_final_decisions", ["application_id"])

    op.create_table(
        "development_plans",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("decision_packet_id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("job_id", sa.UUID(), nullable=False),
        sa.Column("candidate_id", sa.UUID(), nullable=False),
        sa.Column("application_id", sa.UUID(), nullable=False),
        sa.Column("plan_type", sa.String(64), nullable=False),
        sa.Column("generated_by_agent", sa.String(120), nullable=True),
        sa.Column("model_provider", sa.String(64), nullable=True),
        sa.Column("model_name", sa.String(200), nullable=True),
        sa.Column("plan_json", postgresql.JSONB(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["decision_packet_id"], ["decision_support_packets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_dev_plans_packet", "development_plans", ["decision_packet_id"])

    op.create_table(
        "decision_emails",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("decision_packet_id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("candidate_id", sa.UUID(), nullable=False),
        sa.Column("job_id", sa.UUID(), nullable=False),
        sa.Column("application_id", sa.UUID(), nullable=False),
        sa.Column("email_type", sa.String(32), nullable=False),
        sa.Column("subject", sa.String(500), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("generated_by_agent", sa.String(120), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("approved_by_user_id", sa.UUID(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["decision_packet_id"], ["decision_support_packets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_decision_emails_packet", "decision_emails", ["decision_packet_id"])


def downgrade() -> None:
    op.drop_index("ix_decision_emails_packet", table_name="decision_emails")
    op.drop_table("decision_emails")
    op.drop_index("ix_dev_plans_packet", table_name="development_plans")
    op.drop_table("development_plans")
    op.drop_index("ix_hr_final_decisions_app", table_name="hr_final_decisions")
    op.drop_index("ix_hr_final_decisions_packet", table_name="hr_final_decisions")
    op.drop_table("hr_final_decisions")
    op.drop_index("ix_dss_score_breakdown_packet", table_name="decision_score_breakdowns")
    op.drop_table("decision_score_breakdowns")
    op.drop_index("ix_dss_packets_job", table_name="decision_support_packets")
    op.drop_index("ix_dss_packets_cand", table_name="decision_support_packets")
    op.drop_index("ix_dss_packets_app", table_name="decision_support_packets")
    op.drop_index("ix_dss_packets_org", table_name="decision_support_packets")
    op.drop_table("decision_support_packets")
