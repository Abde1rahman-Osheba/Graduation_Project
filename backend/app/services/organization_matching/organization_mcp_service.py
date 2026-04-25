"""
Optional Google Calendar / Gmail MCP bridges — not required for the core
workflow (`OUTREACH_DEFAULT_BOOKING_LINK` + SMTP is enough).
"""

from __future__ import annotations

from app.core.config import get_settings

settings = get_settings()


def calendar_mcp_link_hint() -> str | None:
    if settings.mcp_enabled and settings.mcp_google_calendar_enabled:
        return "mcp:google-calendar"
    return None


def gmail_mcp_hint() -> str | None:
    if settings.mcp_enabled and settings.mcp_gmail_enabled:
        return "mcp:gmail"
    return None
