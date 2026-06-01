"""Tests for normalize stage edge cases."""
from __future__ import annotations

from datetime import datetime, timezone

from bet.pipeline.stages.normalize import normalize_raw_events
from bet.pipeline.contracts import RawEvent


def test_normalize_fallback_to_fetched_at():
    re = RawEvent(source="s", external_id="e1", data={}, fetched_at=datetime(2026,6,1,12,0,tzinfo=timezone.utc))
    res = normalize_raw_events([re])
    assert res[0].event_time == re.fetched_at


def test_normalize_parses_string_timestamp():
    re = RawEvent(source="s", external_id="e2", data={"event_time": "2026-06-01T18:00:00+02:00"}, fetched_at=datetime.now(timezone.utc))
    res = normalize_raw_events([re])
    assert res[0].event_time.tzinfo is not None
