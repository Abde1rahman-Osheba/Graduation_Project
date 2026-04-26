from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.db.models.sync import AuditLog


def log_dss(
    db: Session,
    *,
    actor_user_id: uuid.UUID | None,
    action: str,
    entity_id: uuid.UUID,
    new_value: dict[str, Any] | None = None,
) -> None:
    db.add(
        AuditLog(
            actor_user_id=actor_user_id,
            action=action,
            entity_type="decision_support",
            entity_id=entity_id,
            new_value=new_value,
        ),
    )
