"""
Alembic environment configuration.

Reads the SQLAlchemy URL from the application settings and binds
the metadata from our models so ``--autogenerate`` works.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import get_settings
from app.db.models.base import Base

# Import all models so Alembic sees them for autogenerate
from app.db.models.organization import Organization  # noqa: F401
from app.db.models.user import User  # noqa: F401
from app.db.models.candidate import Candidate  # noqa: F401
from app.db.models.job import Job  # noqa: F401
from app.db.models.application import Application, OrganizationMember, AuditEvent  # noqa: F401
from app.db.models.cv_entities import CandidateDocument, Skill, CandidateSkill, CandidateExperience, CandidateEducation, CandidateCertification  # noqa: F401
from app.db.models.ingestion import IngestionJob, OutboxEvent  # noqa: F401
from app.db.models.job_ingestion import JobSourceRun, JobRawItem, JobSkillRequirement, IngestionError, JobVectorProjectionStatus  # noqa: F401
from app.db.models.reference import Company, Location  # noqa: F401
from app.db.models.candidate_extras import CandidateContact, CandidateProject, CandidateLink  # noqa: F401
from app.db.models.sync import DBSyncStatus, AuditLog, CandidateJobMatch  # noqa: F401
from app.db.models.job_scraper import (  # noqa: F401
    JobSkillLink,
    JobRequirementText,
    JobResponsibility,
    JobImportRun,
    JobImportError,
    JobScraperState,
)
from app.db.models.scoring import (  # noqa: F401
    CandidateJobScore,
    ScoringRun,
    ScoringError,
    ScoringCriteriaConfig,
)
from app.db.models.organization_matching import (  # noqa: F401
    OrganizationJobRequest,
    OrganizationMatchingRun,
    OrganizationCandidateImport,
    OrganizationCandidateImportError,
    OrganizationBlindCandidateMap,
    OrganizationCandidateRanking,
    OrganizationOutreachMessage,
)
from app.db.models.interview import (  # noqa: F401
    Interview,
    InterviewParticipant,
    InterviewQuestionPack,
    InterviewTranscript,
    InterviewSummary,
    InterviewEvaluation,
    InterviewDecisionPacket,
    InterviewHumanDecision,
)
from app.db.models.decision_support import (  # noqa: F401
    DecisionEmail,
    DecisionScoreBreakdown,
    DecisionSupportPacket,
    DevelopmentPlan,
    HrFinalDecision,
)

config = context.config

# Override the sqlalchemy.url from settings
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
