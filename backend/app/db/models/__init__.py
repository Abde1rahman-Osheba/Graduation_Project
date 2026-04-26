# PATHS Backend — DB models package

from app.db.models.base import Base
from app.db.models.organization import Organization
from app.db.models.user import User
from app.db.models.candidate import Candidate
from app.db.models.job import Job
from app.db.models.application import Application
from app.db.models.ingestion import IngestionJob, OutboxEvent
from app.db.models.cv_entities import CandidateDocument, Skill, CandidateSkill, CandidateExperience, CandidateEducation, CandidateCertification
from app.db.models.job_ingestion import JobSourceRun, JobRawItem, JobSkillRequirement, IngestionError, JobVectorProjectionStatus
from app.db.models.reference import Company, Location
from app.db.models.candidate_extras import CandidateContact, CandidateProject, CandidateLink
from app.db.models.sync import DBSyncStatus, AuditLog, CandidateJobMatch
from app.db.models.job_scraper import (
    JobSkillLink,
    JobRequirementText,
    JobResponsibility,
    JobImportRun,
    JobImportError,
    JobScraperState,
)
from app.db.models.scoring import (
    CandidateJobScore,
    ScoringRun,
    ScoringError,
    ScoringCriteriaConfig,
)
from app.db.models.organization_matching import (
    OrganizationJobRequest,
    OrganizationMatchingRun,
    OrganizationCandidateImport,
    OrganizationCandidateImportError,
    OrganizationBlindCandidateMap,
    OrganizationCandidateRanking,
    OrganizationOutreachMessage,
)
from app.db.models.interview import (
    Interview,
    InterviewParticipant,
    InterviewQuestionPack,
    InterviewTranscript,
    InterviewSummary,
    InterviewEvaluation,
    InterviewDecisionPacket,
    InterviewHumanDecision,
)
from app.db.models.decision_support import (
    DecisionEmail,
    DecisionScoreBreakdown,
    DecisionSupportPacket,
    DevelopmentPlan,
    HrFinalDecision,
)

__all__ = [
    "Base",
    "Organization",
    "User",
    "Candidate",
    "Job",
    "Application",
    "IngestionJob",
    "OutboxEvent",
    "CandidateDocument",
    "Skill",
    "CandidateSkill",
    "CandidateExperience",
    "CandidateEducation",
    "CandidateCertification",
    "JobSourceRun",
    "JobRawItem",
    "JobSkillRequirement",
    "IngestionError",
    "JobVectorProjectionStatus",
    # New unified-integration entities
    "Company",
    "Location",
    "CandidateContact",
    "CandidateProject",
    "CandidateLink",
    "DBSyncStatus",
    "AuditLog",
    "CandidateJobMatch",
    # Job-scraper-specific entities
    "JobSkillLink",
    "JobRequirementText",
    "JobResponsibility",
    "JobImportRun",
    "JobImportError",
    "JobScraperState",
    # Candidate-Job scoring
    "CandidateJobScore",
    "ScoringRun",
    "ScoringError",
    "ScoringCriteriaConfig",
    # Organization-side matching + outreach
    "OrganizationJobRequest",
    "OrganizationMatchingRun",
    "OrganizationCandidateImport",
    "OrganizationCandidateImportError",
    "OrganizationBlindCandidateMap",
    "OrganizationCandidateRanking",
    "OrganizationOutreachMessage",
    # Interview intelligence
    "Interview",
    "InterviewParticipant",
    "InterviewQuestionPack",
    "InterviewTranscript",
    "InterviewSummary",
    "InterviewEvaluation",
    "InterviewDecisionPacket",
    "InterviewHumanDecision",
    "DecisionSupportPacket",
    "DecisionScoreBreakdown",
    "HrFinalDecision",
    "DevelopmentPlan",
    "DecisionEmail",
]
