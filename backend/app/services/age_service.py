"""
PATHS Backend — Apache AGE graph service layer.

Manages the AGE extension, graph lifecycle, and Cypher query execution
through raw SQL on top of PostgreSQL.
"""

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import engine
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

GRAPH_NAME = settings.age_graph_name

# ── Session preparation ────────────────────────────────────────────────
_AGE_SESSION_SQL = text("""
    SET search_path = ag_catalog, "$user", public;
    LOAD 'age';
""")


def _prepare_age_session(conn) -> None:
    """Load AGE extension and set search path for the current session."""
    conn.execute(_AGE_SESSION_SQL)


# ── Public API ─────────────────────────────────────────────────────────

class AGEService:
    """Service for Apache AGE graph operations."""

    # ── Health / Bootstrap ─────────────────────────────────────────────

    @staticmethod
    def test_connection() -> dict:
        """Verify that the AGE extension is installed and accessible."""
        try:
            with engine.connect() as conn:
                result = conn.execute(
                    text("SELECT extname, extversion FROM pg_extension WHERE extname = 'age'")
                )
                row = result.fetchone()
                if row:
                    logger.info("AGE extension found: v%s", row[1])
                    return {"status": "healthy", "extension": row[0], "version": row[1]}
                return {"status": "unhealthy", "error": "AGE extension not installed"}
        except Exception as exc:
            logger.error("AGE connection test failed: %s", exc)
            return {"status": "unhealthy", "error": str(exc)}

    @staticmethod
    def init_graph() -> dict:
        """Create the application graph if it does not exist."""
        try:
            with engine.connect() as conn:
                _prepare_age_session(conn)

                # Check whether graph already exists
                exists = conn.execute(
                    text("SELECT count(*) FROM ag_catalog.ag_graph WHERE name = :g"),
                    {"g": GRAPH_NAME},
                ).scalar()

                if exists:
                    logger.info("Graph '%s' already exists", GRAPH_NAME)
                    conn.commit()
                    return {"status": "exists", "graph": GRAPH_NAME}

                conn.execute(text(f"SELECT create_graph('{GRAPH_NAME}')"))
                conn.commit()
                logger.info("Graph '%s' created", GRAPH_NAME)
                return {"status": "created", "graph": GRAPH_NAME}
        except Exception as exc:
            logger.error("Graph init failed: %s", exc)
            return {"status": "error", "error": str(exc)}

    # ── Cypher helpers ─────────────────────────────────────────────────

    @staticmethod
    def execute_cypher(cypher: str, params: dict[str, Any] | None = None) -> list[dict]:
        """
        Execute a Cypher query through AGE and return results as dicts.

        The query is wrapped in the ``cypher()`` function that AGE exposes
        as a PostgreSQL function.
        """
        sql = text(f"""
            SELECT * FROM cypher('{GRAPH_NAME}', $$
                {cypher}
            $$) AS (result agtype);
        """)
        try:
            with engine.connect() as conn:
                _prepare_age_session(conn)
                rows = conn.execute(sql).fetchall()
                conn.commit()
                return [{"result": str(r[0])} for r in rows]
        except Exception as exc:
            logger.error("Cypher query failed: %s — %s", cypher, exc)
            raise

    # ── Convenience methods ────────────────────────────────────────────

    @staticmethod
    def create_node(label: str, properties: dict[str, Any]) -> list[dict]:
        """Create a vertex with the given label and properties."""
        props = ", ".join(f"{k}: '{v}'" for k, v in properties.items())
        cypher = f"CREATE (n:{label} {{{props}}}) RETURN n"
        return AGEService.execute_cypher(cypher)

    @staticmethod
    def create_relationship(
        from_label: str,
        from_match: dict[str, Any],
        to_label: str,
        to_match: dict[str, Any],
        rel_type: str,
        properties: dict[str, Any] | None = None,
    ) -> list[dict]:
        """Create an edge between two matched nodes."""
        from_cond = " AND ".join(f"a.{k} = '{v}'" for k, v in from_match.items())
        to_cond = " AND ".join(f"b.{k} = '{v}'" for k, v in to_match.items())
        props = ""
        if properties:
            prop_str = ", ".join(f"{k}: '{v}'" for k, v in properties.items())
            props = f" {{{prop_str}}}"
        cypher = (
            f"MATCH (a:{from_label}), (b:{to_label}) "
            f"WHERE {from_cond} AND {to_cond} "
            f"CREATE (a)-[r:{rel_type}{props}]->(b) RETURN r"
        )
        return AGEService.execute_cypher(cypher)

    @staticmethod
    def query_subgraph(label: str, limit: int = 25) -> list[dict]:
        """Return a small subgraph of nodes with the given label."""
        cypher = f"MATCH (n:{label}) RETURN n LIMIT {limit}"
        return AGEService.execute_cypher(cypher)

    @staticmethod
    def sample_query() -> dict:
        """Run a small demo query to prove AGE is working."""
        try:
            # Create a sample Skill node and read it back
            AGEService.create_node("Skill", {"name": "Python", "category": "programming"})
            results = AGEService.query_subgraph("Skill", limit=5)
            return {"status": "ok", "sample_results": results}
        except Exception as exc:
            return {"status": "error", "error": str(exc)}
