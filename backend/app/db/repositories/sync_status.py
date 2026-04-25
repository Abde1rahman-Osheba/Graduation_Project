"""
PATHS Backend — db_sync_status / audit_logs repository.

Centralizes the spec-required helpers used by sync orchestrators:
  - create_or_update_sync_status(...)
  - mark_graph_success / mark_graph_failed
  - mark_vector_success / mark_vector_failed
  - write_audit_log(...)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.sync import AuditLog, DBSyncStatus


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def get_sync_status(
    db: Session, entity_type: str, entity_id: UUID | str,
) -> DBSyncStatus | None:
    return db.execute(
        select(DBSyncStatus).where(
            DBSyncStatus.entity_type == entity_type,
            DBSyncStatus.entity_id == UUID(str(entity_id)),
        )
    ).scalar_one_or_none()


def create_or_update_sync_status(
    db: Session,
    entity_type: str,
    entity_id: UUID | str,
    *,
    graph_status: str | None = None,
    vector_status: str | None = None,
    graph_error: str | None = None,
    vector_error: str | None = None,
    source_hash: str | None = None,
    increment_retry: bool = False,
) -> DBSyncStatus:
    existing = get_sync_status(db, entity_type, entity_id)
    eid = UUID(str(entity_id))
    if existing is None:
        existing = DBSyncStatus(entity_type=entity_type, entity_id=eid)
        db.add(existing)

    if graph_status:
        existing.graph_sync_status = graph_status
        if graph_status == "success":
            existing.graph_last_synced_at = _utcnow()
            existing.graph_error = None
        else:
            existing.graph_error = graph_error
    if vector_status:
        existing.vector_sync_status = vector_status
        if vector_status == "success":
            existing.vector_last_synced_at = _utcnow()
            existing.vector_error = None
        else:
            existing.vector_error = vector_error
    if source_hash:
        existing.source_hash = source_hash
    if increment_retry:
        existing.retry_count = (existing.retry_count or 0) + 1

    db.flush()
    return existing


def mark_graph_success(db: Session, entity_type: str, entity_id: UUID | str) -> None:
    create_or_update_sync_status(
        db, entity_type, entity_id, graph_status="success",
    )


def mark_graph_failed(
    db: Session, entity_type: str, entity_id: UUID | str, *, error: str,
) -> None:
    create_or_update_sync_status(
        db, entity_type, entity_id, graph_status="failed", graph_error=error,
    )


def mark_vector_success(
    db: Session,
    entity_type: str,
    entity_id: UUID | str,
    *,
    source_hash: str | None = None,
) -> None:
    create_or_update_sync_status(
        db,
        entity_type,
        entity_id,
        vector_status="success",
        source_hash=source_hash,
    )


def mark_vector_failed(
    db: Session, entity_type: str, entity_id: UUID | str, *, error: str,
) -> None:
    create_or_update_sync_status(
        db, entity_type, entity_id, vector_status="failed", vector_error=error,
    )


def write_audit_log(
    db: Session,
    *,
    action: str,
    entity_type: str,
    entity_id: UUID | str | None = None,
    actor_user_id: UUID | str | None = None,
    old_value: dict[str, Any] | None = None,
    new_value: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditLog:
    log = AuditLog(
        action=action,
        entity_type=entity_type,
        entity_id=UUID(str(entity_id)) if entity_id else None,
        actor_user_id=UUID(str(actor_user_id)) if actor_user_id else None,
        old_value=old_value,
        new_value=new_value,
        audit_metadata=metadata,
    )
    db.add(log)
    db.flush()
    return log
