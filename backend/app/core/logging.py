"""
PATHS Backend — Logging configuration.

Sets up structured logging for the application with configurable levels.
"""

import logging
import sys

from app.core.config import get_settings


def setup_logging() -> None:
    """Configure root and application loggers."""
    settings = get_settings()
    level = logging.DEBUG if settings.debug else logging.INFO

    fmt = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    formatter = logging.Formatter(fmt, datefmt="%Y-%m-%d %H:%M:%S")

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(handler)

    # Quiet noisy libraries
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)


def get_logger(name: str) -> logging.Logger:
    """Return a named logger."""
    return logging.getLogger(name)
