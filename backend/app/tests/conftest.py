"""
PATHS Backend — Shared testing fixtures.
"""

import os
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.database import get_db
from app.db.models.base import Base
from app.main import app
from app.repositories.user_repo import UserRepository

settings = get_settings()

# For tests, we use the same URL but append `_test` to DB name if you wish, 
# but per instructions, project runs against postgres locally.
# We will use the same database connection for integration testing in this demo.
# Note: For real world use a separate test DB and Drop/Create is advised.
engine = create_engine(settings.database_url, echo=False)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="session")
def setup_test_db():
    """Create all tables before tests run; drop them after."""
    # Base.metadata.drop_all(bind=engine)
    # Base.metadata.create_all(bind=engine)
    yield
    # Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session(setup_test_db) -> Generator[Session, None, None]:
    """Provide a transactional DB session for tests."""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """Test client with dependency overrides."""
    
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
