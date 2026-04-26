"""Append interview actions to the shared `audit_logs` table."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.db.models.sync import AuditLog


def log_interview_action(
    db: Session,
    *,
    actor_user_id: uuid.UUID | None,
    action: str,
    entity_id: uuid.UUID,
    new_value: dict[str, Any] | None = None,
    old_value: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    row = AuditLog(
        actor_user_id=actor_user_id,
        action=action,
        entity_type="interview",
        entity_id=entity_id,
        old_value=old_value,
        new_value=new_value,
        audit_metadata=extra,
    )
    db.add(row)
