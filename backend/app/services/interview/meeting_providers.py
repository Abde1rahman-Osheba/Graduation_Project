"""
Meeting / calendar provider abstraction (Google first; Zoom/Teams placeholders).

If Google credentials are missing, callers should fall back to a manual meeting URL
supplied by HR — the workflow must not crash.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


@dataclass
class MeetingEventResult:
    success: bool
    meeting_url: str | None = None
    calendar_event_id: str | None = None
    provider: str = "manual"
    raw: dict[str, Any] | None = None
    error_message: str | None = None


class MeetingProvider(ABC):
    name: str = "base"

    @abstractmethod
    async def create_meeting(
        self,
        *,
        title: str,
        start: datetime,
        end: datetime,
        timezone: str,
        attendees_emails: list[str],
    ) -> MeetingEventResult:
        ...

    @abstractmethod
    async def update_meeting(
        self,
        *,
        calendar_event_id: str,
        start: datetime,
        end: datetime,
        timezone: str,
    ) -> MeetingEventResult:
        ...

    @abstractmethod
    async def cancel_meeting(self, *, calendar_event_id: str) -> MeetingEventResult:
        ...


def get_join_url_from_result(result: MeetingEventResult) -> str | None:
    return result.meeting_url


class ManualMeetingProvider(MeetingProvider):
    """No API calls — use HR-provided URL or generate a placeholder."""

    name = "manual"

    async def create_meeting(
        self,
        *,
        title: str,
        start: datetime,
        end: datetime,
        timezone: str,
        attendees_emails: list[str],
    ) -> MeetingEventResult:
        token = str(uuid.uuid4())[:8]
        placeholder = f"https://paths.local/interviews/pending/{token}"
        return MeetingEventResult(
            success=True,
            meeting_url=placeholder,
            calendar_event_id=None,
            provider=self.name,
            raw={"note": "manual provider — replace URL with real link"},
        )

    async def update_meeting(
        self,
        *,
        calendar_event_id: str,
        start: datetime,
        end: datetime,
        timezone: str,
    ) -> MeetingEventResult:
        return MeetingEventResult(success=True, provider=self.name, calendar_event_id=calendar_event_id)

    async def cancel_meeting(self, *, calendar_event_id: str) -> MeetingEventResult:
        return MeetingEventResult(success=True, provider=self.name, calendar_event_id=calendar_event_id)


class GoogleMeetProvider(MeetingProvider):
    """
    Google Calendar + Meet. Requires service-account JSON path + calendar ID env vars.
    If `google_api_python_client` is not installed or config is missing, returns failure
    and callers should fall back to manual URL.
    """

    name = "google_meet"

    def _configured(self) -> bool:
        return bool(
            getattr(settings, "google_calendar_service_account_file", None)
            or getattr(settings, "google_application_credentials", None),
        )

    async def create_meeting(
        self,
        *,
        title: str,
        start: datetime,
        end: datetime,
        timezone: str,
        attendees_emails: list[str],
    ) -> MeetingEventResult:
        if not self._configured():
            return MeetingEventResult(
                success=False,
                provider=self.name,
                error_message="Google Calendar is not configured (set GOOGLE_APPLICATION_CREDENTIALS or service account file).",
            )
        try:
            from google.oauth2 import service_account  # type: ignore[import-not-found]
            from googleapiclient.discovery import (  # type: ignore[import-not-found]
                build,
            )
        except ImportError:
            return MeetingEventResult(
                success=False,
                provider=self.name,
                error_message="google-api-python-client not installed. pip install google-api-python-client google-auth",
            )

        sa_file = (
            settings.google_calendar_service_account_file
            or settings.google_application_credentials
        )
        cal_id = settings.google_calendar_id or "primary"
        try:
            scopes = ["https://www.googleapis.com/auth/calendar"]
            creds = service_account.Credentials.from_service_account_file(
                sa_file, scopes=scopes,
            )
            delegated = getattr(
                settings, "google_workspace_impersonate_user", None
            ) or None
            if delegated:
                creds = creds.with_subject(str(delegated))
            service = build("calendar", "v3", credentials=creds, cache_discovery=False)
            body: dict[str, Any] = {
                "summary": title,
                "start": {
                    "dateTime": start.isoformat(),
                    "timeZone": timezone or "UTC",
                },
                "end": {
                    "dateTime": end.isoformat(),
                    "timeZone": timezone or "UTC",
                },
                "attendees": [{"email": e} for e in attendees_emails if e],
                "conferenceData": {
                    "createRequest": {
                        "requestId": str(uuid.uuid4()),
                        "conferenceSolutionKey": {"type": "hangoutsMeet"},
                    }
                },
            }
            event = service.events().insert(
                calendarId=cal_id,
                body=body,
                conferenceDataVersion=1,
            ).execute()
            meet_link = None
            conf = (event or {}).get("conferenceData") or {}
            for ep in conf.get("entryPoints") or []:
                if ep.get("entryPointType") == "video":
                    meet_link = ep.get("uri")
                    break
            return MeetingEventResult(
                success=True,
                meeting_url=meet_link,
                calendar_event_id=event.get("id"),
                provider=self.name,
                raw=event,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Google Calendar create failed: %s", exc)
            return MeetingEventResult(
                success=False,
                provider=self.name,
                error_message=str(exc)[:500],
            )

    async def update_meeting(
        self,
        *,
        calendar_event_id: str,
        start: datetime,
        end: datetime,
        timezone: str,
    ) -> MeetingEventResult:
        if not self._configured():
            return MeetingEventResult(
                success=False, provider=self.name,
                error_message="Google Calendar is not configured.",
            )
        try:
            from google.oauth2 import service_account  # type: ignore[import-not-found]
            from googleapiclient.discovery import build  # type: ignore[import-not-found]
        except ImportError:
            return MeetingEventResult(
                success=False,
                error_message="google-api-python-client not installed",
            )
        sa_file = (
            settings.google_calendar_service_account_file
            or settings.google_application_credentials
        )
        cal_id = settings.google_calendar_id or "primary"
        try:
            scopes = ["https://www.googleapis.com/auth/calendar"]
            creds = service_account.Credentials.from_service_account_file(
                sa_file, scopes=scopes,
            )
            delegated = getattr(
                settings, "google_workspace_impersonate_user", None
            ) or None
            if delegated:
                creds = creds.with_subject(str(delegated))
            service = build("calendar", "v3", credentials=creds, cache_discovery=False)
            body = {
                "start": {"dateTime": start.isoformat(), "timeZone": timezone or "UTC"},
                "end": {"dateTime": end.isoformat(), "timeZone": timezone or "UTC"},
            }
            event = service.events().patch(
                calendarId=cal_id, eventId=calendar_event_id, body=body,
            ).execute()
            return MeetingEventResult(
                success=True,
                calendar_event_id=event.get("id", calendar_event_id),
                meeting_url=None,
                provider=self.name,
                raw=event,
            )
        except Exception as exc:  # noqa: BLE001
            return MeetingEventResult(success=False, provider=self.name, error_message=str(exc)[:500])

    async def cancel_meeting(self, *, calendar_event_id: str) -> MeetingEventResult:
        if not self._configured():
            return MeetingEventResult(success=True, provider=self.name)
        try:
            from google.oauth2 import service_account  # type: ignore[import-not-found]
            from googleapiclient.discovery import build  # type: ignore[import-not-found]
        except ImportError:
            return MeetingEventResult(success=False, error_message="google-api-python-client not installed")
        sa_file = (
            settings.google_calendar_service_account_file
            or settings.google_application_credentials
        )
        cal_id = settings.google_calendar_id or "primary"
        try:
            scopes = ["https://www.googleapis.com/auth/calendar"]
            creds = service_account.Credentials.from_service_account_file(
                sa_file, scopes=scopes,
            )
            delegated = getattr(
                settings, "google_workspace_impersonate_user", None
            ) or None
            if delegated:
                creds = creds.with_subject(str(delegated))
            service = build("calendar", "v3", credentials=creds, cache_discovery=False)
            service.events().delete(
                calendarId=cal_id, eventId=calendar_event_id,
            ).execute()
            return MeetingEventResult(success=True, provider=self.name, calendar_event_id=calendar_event_id)
        except Exception as exc:  # noqa: BLE001
            return MeetingEventResult(success=False, error_message=str(exc)[:500])


class ZoomProvider(MeetingProvider):
    name = "zoom"

    async def create_meeting(
        self,
        *,
        title: str,
        start: datetime,
        end: datetime,
        timezone: str,
        attendees_emails: list[str],
    ) -> MeetingEventResult:
        return MeetingEventResult(
            success=False,
            provider=self.name,
            error_message="Zoom integration not implemented — use meeting_provider=manual and manual_meeting_url.",
        )

    async def update_meeting(
        self,
        *,
        calendar_event_id: str,
        start: datetime,
        end: datetime,
        timezone: str,
    ) -> MeetingEventResult:
        return MeetingEventResult(success=False, provider=self.name, error_message="not implemented")

    async def cancel_meeting(self, *, calendar_event_id: str) -> MeetingEventResult:
        return MeetingEventResult(success=False, provider=self.name, error_message="not implemented")


class TeamsProvider(MeetingProvider):
    name = "teams"

    async def create_meeting(
        self,
        *,
        title: str,
        start: datetime,
        end: datetime,
        timezone: str,
        attendees_emails: list[str],
    ) -> MeetingEventResult:
        return MeetingEventResult(
            success=False,
            provider=self.name,
            error_message="Microsoft Teams integration not implemented — use manual URL.",
        )

    async def update_meeting(
        self,
        *,
        calendar_event_id: str,
        start: datetime,
        end: datetime,
        timezone: str,
    ) -> MeetingEventResult:
        return MeetingEventResult(success=False, error_message="not implemented")

    async def cancel_meeting(self, *, calendar_event_id: str) -> MeetingEventResult:
        return MeetingEventResult(success=False, error_message="not implemented")


def get_meeting_provider(provider_name: str | None) -> MeetingProvider:
    key = (provider_name or "manual").strip().lower()
    if key in ("google_meet", "google", "gcal"):
        return GoogleMeetProvider()
    if key == "zoom":
        return ZoomProvider()
    if key in ("teams", "msteams"):
        return TeamsProvider()
    return ManualMeetingProvider()
