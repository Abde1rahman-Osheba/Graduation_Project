"""
PATHS Backend — Ingestion Models.
"""

import uuid
from sqlalchemy import ForeignKey, String, BigInteger, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

class IngestionJob(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "ingestion_jobs"

    candidate_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    stage: Mapped[str] = mapped_column(String(100), nullable=False, default="uploaded")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class OutboxEvent(Base, TimestampMixin):
    __tablename__ = "outbox_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    aggregate_type: Mapped[str] = mapped_column(String(100), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    processed_at: Mapped[str | None] = mapped_column(String(50), nullable=True) # ISO format or can be DateTime
