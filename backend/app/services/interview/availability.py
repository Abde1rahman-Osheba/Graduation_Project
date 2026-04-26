"""Slot generation (deterministic) — no DB or LLM dependencies."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any


def list_availability(
    from_dt: datetime | None,
    to_dt: datetime | None,
    slot_minutes: int = 30,
) -> list[dict[str, Any]]:
    start = (from_dt or datetime.now(timezone.utc)).astimezone(timezone.utc)
    end = (to_dt or (start + timedelta(days=7))).astimezone(timezone.utc)
    if end <= start:
        end = start + timedelta(days=1)
    out: list[dict[str, Any]] = []
    step = max(15, int(slot_minutes))
    day: date = start.date()
    end_day: date = end.date()
    while day <= end_day and len(out) < 200:
        day_start = datetime.combine(day, time(9, 0, tzinfo=timezone.utc))
        day_end = datetime.combine(day, time(17, 0, tzinfo=timezone.utc))
        cur = day_start
        while cur + timedelta(minutes=step) <= day_end and len(out) < 200:
            slot_end = cur + timedelta(minutes=step)
            if cur >= start and slot_end <= end:
                out.append({"start": cur, "end": slot_end, "timezone": "UTC"})
            cur += timedelta(minutes=step)
        day = day + timedelta(days=1)
    return out
