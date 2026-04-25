"""
PATHS Backend — PostgreSQL service layer.

Connection testing and session utilities.
"""

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import engine
from app.core.logging import get_logger

logger = get_logger(__name__)


class PostgresService:
    """Service for PostgreSQL connectivity and diagnostics."""

    @staticmethod
    def test_connection() -> dict:
        """Test PostgreSQL connectivity and return version info."""
        try:
            with engine.connect() as conn:
                result = conn.execute(text("SELECT version()"))
                version = result.scalar()
                logger.info("PostgreSQL connection successful")
                return {"status": "healthy", "version": version}
        except Exception as exc:
            logger.error("PostgreSQL connection failed: %s", exc)
            return {"status": "unhealthy", "error": str(exc)}

    @staticmethod
    def get_current_database(db: Session) -> str | None:
        """Return the name of the currently connected database."""
        result = db.execute(text("SELECT current_database()"))
        return result.scalar()

    @staticmethod
    def get_table_count(db: Session) -> int:
        """Return the number of user-defined tables."""
        result = db.execute(
            text(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema = 'public'"
            )
        )
        return result.scalar() or 0
