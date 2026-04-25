"""add cv ingestion tables

Revision ID: b8188dd8bf77
Revises: a7077cc7ae66
Create Date: 2026-04-05 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b8188dd8bf77'
down_revision: Union[str, None] = 'a7077cc7ae66'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # enable age extension
    op.execute("CREATE EXTENSION IF NOT EXISTS age;")

    # candidates table modifications
    op.alter_column('candidates', 'canonical_name', new_column_name='full_name')
    op.add_column('candidates', sa.Column('email', sa.String(length=255), nullable=True))
    op.add_column('candidates', sa.Column('phone', sa.String(length=50), nullable=True))

    # cv entities
    op.create_table('candidate_documents',
    sa.Column('candidate_id', sa.UUID(as_uuid=True), nullable=False),
    sa.Column('document_type', sa.String(length=50), nullable=False),
    sa.Column('original_filename', sa.String(length=255), nullable=False),
    sa.Column('mime_type', sa.String(length=100), nullable=False),
    sa.Column('storage_path_or_url', sa.String(length=1024), nullable=False),
    sa.Column('raw_text', sa.Text(), nullable=True),
    sa.Column('checksum', sa.String(length=255), nullable=True),
    sa.Column('id', sa.UUID(as_uuid=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['candidate_id'], ['candidates.id'], ),
    sa.PrimaryKeyConstraint('id')
    )

    op.create_table('skills',
    sa.Column('normalized_name', sa.String(length=255), nullable=False),
    sa.Column('category', sa.String(length=100), nullable=True),
    sa.Column('id', sa.UUID(as_uuid=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('normalized_name')
    )

    op.create_table('candidate_skills',
    sa.Column('candidate_id', sa.UUID(as_uuid=True), nullable=False),
    sa.Column('skill_id', sa.UUID(as_uuid=True), nullable=False),
    sa.Column('proficiency_score', sa.Integer(), nullable=True),
    sa.Column('years_used', sa.Integer(), nullable=True),
    sa.Column('evidence_text', sa.Text(), nullable=True),
    sa.Column('id', sa.UUID(as_uuid=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['candidate_id'], ['candidates.id'], ),
    sa.ForeignKeyConstraint(['skill_id'], ['skills.id'], ),
    sa.PrimaryKeyConstraint('id')
    )

    op.create_table('candidate_experiences',
    sa.Column('candidate_id', sa.UUID(as_uuid=True), nullable=False),
    sa.Column('company_name', sa.String(length=255), nullable=False),
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('start_date', sa.String(length=50), nullable=True),
    sa.Column('end_date', sa.String(length=50), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('id', sa.UUID(as_uuid=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['candidate_id'], ['candidates.id'], ),
    sa.PrimaryKeyConstraint('id')
    )

    op.create_table('candidate_education',
    sa.Column('candidate_id', sa.UUID(as_uuid=True), nullable=False),
    sa.Column('institution', sa.String(length=255), nullable=False),
    sa.Column('degree', sa.String(length=255), nullable=True),
    sa.Column('field_of_study', sa.String(length=255), nullable=True),
    sa.Column('start_date', sa.String(length=50), nullable=True),
    sa.Column('end_date', sa.String(length=50), nullable=True),
    sa.Column('id', sa.UUID(as_uuid=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['candidate_id'], ['candidates.id'], ),
    sa.PrimaryKeyConstraint('id')
    )

    op.create_table('candidate_certifications',
    sa.Column('candidate_id', sa.UUID(as_uuid=True), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('issuer', sa.String(length=255), nullable=True),
    sa.Column('issue_date', sa.String(length=50), nullable=True),
    sa.Column('expiry_date', sa.String(length=50), nullable=True),
    sa.Column('id', sa.UUID(as_uuid=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['candidate_id'], ['candidates.id'], ),
    sa.PrimaryKeyConstraint('id')
    )

    op.create_table('ingestion_jobs',
    sa.Column('candidate_id', sa.UUID(as_uuid=True), nullable=True),
    sa.Column('document_id', sa.UUID(as_uuid=True), nullable=True),
    sa.Column('status', sa.String(length=50), nullable=False, server_default='pending'),
    sa.Column('stage', sa.String(length=100), nullable=False, server_default='uploaded'),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('metadata_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('id', sa.UUID(as_uuid=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )

    op.create_table('outbox_events',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('aggregate_type', sa.String(length=100), nullable=False),
    sa.Column('aggregate_id', sa.String(length=255), nullable=False),
    sa.Column('event_type', sa.String(length=100), nullable=False),
    sa.Column('payload_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('status', sa.String(length=50), nullable=False, server_default='pending'),
    sa.Column('processed_at', sa.String(length=50), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('outbox_events')
    op.drop_table('ingestion_jobs')
    op.drop_table('candidate_certifications')
    op.drop_table('candidate_education')
    op.drop_table('candidate_experiences')
    op.drop_table('candidate_skills')
    op.drop_table('skills')
    op.drop_table('candidate_documents')

    op.drop_column('candidates', 'phone')
    op.drop_column('candidates', 'email')
    op.alter_column('candidates', 'full_name', new_column_name='canonical_name')
