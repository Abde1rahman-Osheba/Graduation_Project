"""add job ingestion tables

Revision ID: c01234567890
Revises: b8188dd8bf77
Create Date: 2026-04-09 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c01234567890'
down_revision: Union[str, None] = '42430ef650e8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # Modify jobs table
    op.alter_column('jobs', 'organization_id',
               existing_type=sa.UUID(),
               nullable=True)
    
    op.add_column('jobs', sa.Column('source_type', sa.String(length=50), server_default='manual', nullable=True))
    op.add_column('jobs', sa.Column('source_name', sa.String(length=100), nullable=True))
    op.add_column('jobs', sa.Column('source_job_id', sa.String(length=255), nullable=True))
    op.add_column('jobs', sa.Column('source_url', sa.Text(), nullable=True))
    op.add_column('jobs', sa.Column('canonical_hash', sa.String(length=64), nullable=True))
    op.create_index(op.f('ix_jobs_canonical_hash'), 'jobs', ['canonical_hash'], unique=True)
    
    op.add_column('jobs', sa.Column('company_name', sa.String(length=255), nullable=True))
    op.add_column('jobs', sa.Column('company_normalized', sa.String(length=255), nullable=True))
    op.create_index(op.f('ix_jobs_company_normalized'), 'jobs', ['company_normalized'], unique=False)
    
    op.add_column('jobs', sa.Column('title_normalized', sa.String(length=255), nullable=True))
    op.create_index(op.f('ix_jobs_title_normalized'), 'jobs', ['title_normalized'], unique=False)
    
    op.add_column('jobs', sa.Column('description_text', sa.Text(), nullable=True))
    op.add_column('jobs', sa.Column('description_html', sa.Text(), nullable=True))
    op.add_column('jobs', sa.Column('seniority_level', sa.String(length=50), nullable=True))
    op.add_column('jobs', sa.Column('location_text', sa.String(length=255), nullable=True))
    op.add_column('jobs', sa.Column('location_normalized', sa.String(length=255), nullable=True))
    op.add_column('jobs', sa.Column('country_code', sa.String(length=2), nullable=True))
    op.add_column('jobs', sa.Column('city', sa.String(length=100), nullable=True))
    op.add_column('jobs', sa.Column('department', sa.String(length=100), nullable=True))
    
    op.add_column('jobs', sa.Column('salary_min', sa.Float(), nullable=True))
    op.add_column('jobs', sa.Column('salary_max', sa.Float(), nullable=True))
    op.add_column('jobs', sa.Column('salary_currency', sa.String(length=3), nullable=True))
    op.add_column('jobs', sa.Column('posted_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f('ix_jobs_posted_at'), 'jobs', ['posted_at'], unique=False)
    
    op.add_column('jobs', sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True))
    
    op.add_column('jobs', sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False))
    op.create_index(op.f('ix_jobs_is_active'), 'jobs', ['is_active'], unique=False)
    
    op.add_column('jobs', sa.Column('ingestion_status', sa.String(length=50), server_default='active', nullable=True))
    op.add_column('jobs', sa.Column('raw_payload_jsonb', postgresql.JSONB(astext_type=sa.Text()), nullable=True))

    # Create new tables
    op.create_table('job_source_runs',
    sa.Column('id', sa.UUID(as_uuid=True), nullable=False),
    sa.Column('source_type', sa.String(length=50), nullable=False),
    sa.Column('source_name', sa.String(length=100), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('status', sa.String(length=50), nullable=False, server_default='running'),
    sa.Column('fetched_count', sa.Integer(), nullable=False, server_default='0'),
    sa.Column('normalized_count', sa.Integer(), nullable=False, server_default='0'),
    sa.Column('inserted_count', sa.Integer(), nullable=False, server_default='0'),
    sa.Column('updated_count', sa.Integer(), nullable=False, server_default='0'),
    sa.Column('duplicate_count', sa.Integer(), nullable=False, server_default='0'),
    sa.Column('failed_count', sa.Integer(), nullable=False, server_default='0'),
    sa.Column('error_summary_jsonb', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_by', sa.String(length=100), nullable=True, server_default='system'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )

    op.create_table('job_raw_items',
    sa.Column('id', sa.UUID(as_uuid=True), nullable=False),
    sa.Column('source_run_id', sa.UUID(as_uuid=True), nullable=False),
    sa.Column('source_type', sa.String(length=50), nullable=False),
    sa.Column('source_name', sa.String(length=100), nullable=False),
    sa.Column('source_job_id', sa.String(length=255), nullable=True),
    sa.Column('source_url', sa.Text(), nullable=True),
    sa.Column('raw_payload_jsonb', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('fetch_status', sa.String(length=50), nullable=False, server_default='success'),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['source_run_id'], ['job_source_runs.id'], ),
    sa.PrimaryKeyConstraint('id')
    )

    op.create_table('job_skill_requirements',
    sa.Column('id', sa.UUID(as_uuid=True), nullable=False),
    sa.Column('job_id', sa.UUID(as_uuid=True), nullable=False),
    sa.Column('skill_name_raw', sa.String(length=255), nullable=False),
    sa.Column('skill_name_normalized', sa.String(length=255), nullable=False),
    sa.Column('importance_weight', sa.Float(), nullable=False, server_default='1.0'),
    sa.Column('is_required', sa.Boolean(), nullable=False, server_default=sa.text('false')),
    sa.Column('extracted_by', sa.String(length=50), nullable=False, server_default='rule'),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ),
    sa.PrimaryKeyConstraint('id')
    )

    op.create_table('ingestion_errors',
    sa.Column('id', sa.UUID(as_uuid=True), nullable=False),
    sa.Column('source_run_id', sa.UUID(as_uuid=True), nullable=True),
    sa.Column('source_type', sa.String(length=50), nullable=False),
    sa.Column('source_name', sa.String(length=100), nullable=False),
    sa.Column('source_url', sa.Text(), nullable=True),
    sa.Column('stage', sa.String(length=50), nullable=False),
    sa.Column('error_type', sa.String(length=100), nullable=False),
    sa.Column('error_message', sa.Text(), nullable=False),
    sa.Column('details_jsonb', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['source_run_id'], ['job_source_runs.id'], ),
    sa.PrimaryKeyConstraint('id')
    )

    op.create_table('job_vector_projection_status',
    sa.Column('id', sa.UUID(as_uuid=True), nullable=False),
    sa.Column('job_id', sa.UUID(as_uuid=True), nullable=False),
    sa.Column('vector_backend', sa.String(length=50), nullable=False, server_default='qdrant'),
    sa.Column('collection_name', sa.String(length=100), nullable=False),
    sa.Column('point_id', sa.String(length=255), nullable=False),
    sa.Column('embedding_model', sa.String(length=100), nullable=False),
    sa.Column('projection_status', sa.String(length=50), nullable=False, server_default='pending'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('job_vector_projection_status')
    op.drop_table('ingestion_errors')
    op.drop_table('job_skill_requirements')
    op.drop_table('job_raw_items')
    op.drop_table('job_source_runs')

    op.drop_column('jobs', 'raw_payload_jsonb')
    op.drop_column('jobs', 'ingestion_status')
    op.drop_index(op.f('ix_jobs_is_active'), table_name='jobs')
    op.drop_column('jobs', 'is_active')
    op.drop_column('jobs', 'expires_at')
    
    op.drop_index(op.f('ix_jobs_posted_at'), table_name='jobs')
    op.drop_column('jobs', 'posted_at')
    op.drop_column('jobs', 'salary_currency')
    op.drop_column('jobs', 'salary_max')
    op.drop_column('jobs', 'salary_min')
    op.drop_column('jobs', 'department')
    op.drop_column('jobs', 'city')
    op.drop_column('jobs', 'country_code')
    op.drop_column('jobs', 'location_normalized')
    op.drop_column('jobs', 'location_text')
    op.drop_column('jobs', 'seniority_level')
    op.drop_column('jobs', 'description_html')
    op.drop_column('jobs', 'description_text')
    
    op.drop_index(op.f('ix_jobs_title_normalized'), table_name='jobs')
    op.drop_column('jobs', 'title_normalized')
    
    op.drop_index(op.f('ix_jobs_company_normalized'), table_name='jobs')
    op.drop_column('jobs', 'company_normalized')
    op.drop_column('jobs', 'company_name')
    
    op.drop_index(op.f('ix_jobs_canonical_hash'), table_name='jobs')
    op.drop_column('jobs', 'canonical_hash')
    op.drop_column('jobs', 'source_url')
    op.drop_column('jobs', 'source_job_id')
    op.drop_column('jobs', 'source_name')
    op.drop_column('jobs', 'source_type')

    op.alter_column('jobs', 'organization_id',
               existing_type=sa.UUID(),
               nullable=False)
