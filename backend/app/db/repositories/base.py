"""
PATHS Backend — Generic CRUD repository.

Provides a reusable base class for database operations that
concrete repositories can extend.
"""

from typing import Any, Generic, Sequence, TypeVar
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """Generic CRUD repository for SQLAlchemy models."""

    def __init__(self, model: type[ModelT], db: Session) -> None:
        self.model = model
        self.db = db

    def get_by_id(self, entity_id: UUID) -> ModelT | None:
        return self.db.get(self.model, entity_id)

    def get_all(self, *, skip: int = 0, limit: int = 100) -> Sequence[ModelT]:
        stmt = select(self.model).offset(skip).limit(limit)
        return self.db.scalars(stmt).all()

    def create(self, **kwargs: Any) -> ModelT:
        instance = self.model(**kwargs)
        self.db.add(instance)
        self.db.commit()
        self.db.refresh(instance)
        return instance

    def update(self, entity_id: UUID, **kwargs: Any) -> ModelT | None:
        instance = self.get_by_id(entity_id)
        if instance is None:
            return None
        for key, value in kwargs.items():
            setattr(instance, key, value)
        self.db.commit()
        self.db.refresh(instance)
        return instance

    def delete(self, entity_id: UUID) -> bool:
        instance = self.get_by_id(entity_id)
        if instance is None:
            return False
        self.db.delete(instance)
        self.db.commit()
        return True
