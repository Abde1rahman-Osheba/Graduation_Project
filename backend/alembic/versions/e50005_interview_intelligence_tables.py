"""interview intelligence tables (PATHS HITL workflow)

Revision ID: e50005intintel
Revises: d40004fedcba
Create Date: 2026-04-26

Adds: interviews, interview_participants, interview_question_packs,
interview_transcripts, interview_summaries, interview_evaluations,
interview_decision_packets, interview_human_decisions
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "e50005intintel"
down_revision: Union[str, None] = "d40004fedcba"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "interviews",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("application_id", sa.UUID(), nullable=False),
        sa.Column("candidate_id", sa.UUID(), nullable=False),
        sa.Column("job_id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("interview_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("scheduled_start_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scheduled_end_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("timezone", sa.String(64), nullable=True),
        sa.Column("meeting_provider", sa.String(64), nullable=True),
        sa.Column("meeting_url", sa.Text(), nullable=True),
        sa.Column("calendar_event_id", sa.String(512), nullable=True),
        sa.Column("raw_calendar_payload", postgresql.JSONB(), nullable=True),
        sa.Column("created_by_user_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_interviews_application_id", "interviews", ["application_id"])
    op.create_index("ix_interviews_candidate_id", "interviews", ["candidate_id"])
    op.create_index("ix_interviews_job_id", "interviews", ["job_id"])
    op.create_index("ix_interviews_organization_id", "interviews", ["organization_id"])

    op.create_table(
        "interview_participants",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("interview_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("attendance_status", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["interview_id"], ["interviews.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_interview_participants_interview_id", "interview_participants", ["interview_id"])

    op.create_table(
        "interview_question_packs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("interview_id", sa.UUID(), nullable=False),
        sa.Column("question_pack_type", sa.String(32), nullable=False),
        sa.Column("generated_by_agent", sa.String(128), nullable=True),
        sa.Column("questions_json", postgresql.JSONB(), nullable=False),
        sa.Column("approved_by_hr", sa.Boolean(), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["interview_id"], ["interviews.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_interview_question_packs_interview_id", "interview_question_packs", ["interview_id"])

    op.create_table(
        "interview_transcripts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("interview_id", sa.UUID(), nullable=False),
        sa.Column("transcript_text", sa.Text(), nullable=False),
        sa.Column("transcript_source", sa.String(64), nullable=False),
        sa.Column("language", sa.String(32), nullable=True),
        sa.Column("quality_hint", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["interview_id"], ["interviews.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_interview_transcripts_interview_id", "interview_transcripts", ["interview_id"])

    op.create_table(
        "interview_summaries",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("interview_id", sa.UUID(), nullable=False),
        sa.Column("summary_json", postgresql.JSONB(), nullable=False),
        sa.Column("generated_by_agent", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["interview_id"], ["interviews.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_interview_summaries_interview_id", "interview_summaries", ["interview_id"])

    op.create_table(
        "interview_evaluations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("interview_id", sa.UUID(), nullable=False),
        sa.Column("evaluation_type", sa.String(32), nullable=False),
        sa.Column("score_json", postgresql.JSONB(), nullable=False),
        sa.Column("strengths_json", postgresql.JSONB(), nullable=True),
        sa.Column("weaknesses_json", postgresql.JSONB(), nullable=True),
        sa.Column("evidence_json", postgresql.JSONB(), nullable=True),
        sa.Column("recommendation", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["interview_id"], ["interviews.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_interview_evaluations_interview_id", "interview_evaluations", ["interview_id"])

    op.create_table(
        "interview_decision_packets",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("interview_id", sa.UUID(), nullable=False),
        sa.Column("application_id", sa.UUID(), nullable=False),
        sa.Column("candidate_id", sa.UUID(), nullable=False),
        sa.Column("job_id", sa.UUID(), nullable=False),
        sa.Column("recommendation", sa.String(80), nullable=True),
        sa.Column("final_score", sa.Float(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("decision_packet_json", postgresql.JSONB(), nullable=False),
        sa.Column("human_review_required", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["interview_id"], ["interviews.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_interview_decision_packets_interview_id", "interview_decision_packets", ["interview_id"])

    op.create_table(
        "interview_human_decisions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("interview_id", sa.UUID(), nullable=False),
        sa.Column("decided_by", sa.UUID(), nullable=False),
        sa.Column("final_decision", sa.String(32), nullable=False),
        sa.Column("hr_notes", sa.Text(), nullable=True),
        sa.Column("override_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["interview_id"], ["interviews.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["decided_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_interview_human_decisions_interview_id", "interview_human_decisions", ["interview_id"])


def downgrade() -> None:
    op.drop_index("ix_interview_human_decisions_interview_id", table_name="interview_human_decisions")
    op.drop_table("interview_human_decisions")
    op.drop_index("ix_interview_decision_packets_interview_id", table_name="interview_decision_packets")
    op.drop_table("interview_decision_packets")
    op.drop_index("ix_interview_evaluations_interview_id", table_name="interview_evaluations")
    op.drop_table("interview_evaluations")
    op.drop_index("ix_interview_summaries_interview_id", table_name="interview_summaries")
    op.drop_table("interview_summaries")
    op.drop_index("ix_interview_transcripts_interview_id", table_name="interview_transcripts")
    op.drop_table("interview_transcripts")
    op.drop_index("ix_interview_question_packs_interview_id", table_name="interview_question_packs")
    op.drop_table("interview_question_packs")
    op.drop_index("ix_interview_participants_interview_id", table_name="interview_participants")
    op.drop_table("interview_participants")
    op.drop_index("ix_interviews_organization_id", table_name="interviews")
    op.drop_index("ix_interviews_job_id", table_name="interviews")
    op.drop_index("ix_interviews_candidate_id", table_name="interviews")
    op.drop_index("ix_interviews_application_id", table_name="interviews")
    op.drop_table("interviews")
