"""
PATHS Backend — Apache AGE Cypher execution helper.

Apache AGE supports parameterized Cypher via a JSON parameters argument:

    SELECT * FROM cypher('graph', $$ ... $$, $1::agtype) AS (v agtype);

Some PostgreSQL drivers don't bind agtype natively, so we serialize the
parameters as a JSON string and let AGE parse them. We additionally
sanitize values to avoid Cypher-injection issues: only primitive types
(str, int, float, bool, None, list of primitives) are allowed.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Iterable

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

GRAPH_NAME = settings.age_graph_name


_ALLOWED_GRAPH_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_PRIMITIVE_TYPES = (str, int, float, bool, type(None))


def _validate_graph_name(name: str) -> str:
    if not _ALLOWED_GRAPH_NAME.match(name):
        raise ValueError(f"unsafe AGE graph name: {name!r}")
    return name


def _coerce(value: Any) -> Any:
    """Coerce a parameter value to a JSON-serializable primitive."""
    if isinstance(value, _PRIMITIVE_TYPES):
        return value
    if isinstance(value, (list, tuple, set)):
        return [_coerce(v) for v in value]
    return str(value)


def _ensure_age_session(db: Session) -> None:
    """Load the AGE extension and set the search path for the current session."""
    db.execute(text("LOAD 'age';"))
    db.execute(text(f"SET search_path = {settings.age_schema}, \"$user\", public;"))


def ensure_graph(db: Session) -> str:
    """Create the application graph if it does not exist. Returns its name."""
    _ensure_age_session(db)
    graph = _validate_graph_name(GRAPH_NAME)
    exists = db.execute(
        text("SELECT 1 FROM ag_catalog.ag_graph WHERE name = :g"),
        {"g": graph},
    ).first()
    if not exists:
        db.execute(text(f"SELECT create_graph('{graph}')"))
        db.commit()
        logger.info("Created AGE graph %s", graph)
    return graph


def run_cypher(
    db: Session,
    cypher: str,
    params: dict[str, Any] | None = None,
    *,
    return_columns: int = 1,
) -> list[Any]:
    """Run a Cypher query against AGE with safe parameter binding.

    Args:
        db: SQLAlchemy session.
        cypher: Cypher query body (without the wrapping `cypher('...', $$...$$)`).
        params: Cypher parameters (only primitive types are allowed).
        return_columns: number of agtype columns the query returns.

    Returns:
        A list of tuples (one per row); each tuple has `return_columns` items.
    """
    _ensure_age_session(db)
    graph = _validate_graph_name(GRAPH_NAME)

    if params is None:
        params = {}
    coerced = {k: _coerce(v) for k, v in params.items()}
    json_params = json.dumps(coerced)

    columns = ", ".join(f"col{i} agtype" for i in range(return_columns))
    cypher_clean = cypher.strip()
    sql = (
        f"SELECT * FROM cypher('{graph}', $${cypher_clean}$$, "
        f"CAST(:__params AS agtype)) AS ({columns});"
    )
    try:
        result = db.execute(text(sql), {"__params": json_params})
        rows = result.fetchall()
        return [tuple(r) for r in rows]
    except Exception:
        logger.exception("AGE cypher failed: %s", cypher_clean[:200])
        raise


def cypher_count(
    db: Session, cypher: str, params: dict[str, Any] | None = None,
) -> int:
    """Convenience helper that returns row count for a Cypher query."""
    return len(run_cypher(db, cypher, params, return_columns=1))


def value_iter(rows: Iterable[Any]) -> list[str]:
    """Convert AGE result rows into plain string values (drops agtype quoting)."""
    out: list[str] = []
    for row in rows:
        for item in row:
            if item is None:
                continue
            s = str(item)
            # AGE returns strings with surrounding quotes
            if s.startswith('"') and s.endswith('"'):
                s = s[1:-1]
            out.append(s)
    return out
