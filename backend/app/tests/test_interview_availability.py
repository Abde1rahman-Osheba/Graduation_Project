"""Unit tests for interview scheduling helpers (no DB / LLM)."""

from datetime import datetime, timedelta, timezone

from app.services.interview.availability import list_availability


def test_list_availability_returns_slots_in_range():
    start = datetime(2030, 1, 6, 10, 0, tzinfo=timezone.utc)  # Monday
    end = start + timedelta(days=1)
    slots = list_availability(start, end, slot_minutes=30)
    assert len(slots) >= 1
    for s in slots:
        assert s["start"] < s["end"]
        assert s["timezone"] == "UTC"
