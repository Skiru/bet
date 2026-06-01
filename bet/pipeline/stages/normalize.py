"""Normalize stage: convert raw events into canonical fixtures.

Pure function: input list of RawEvent -> output list of CanonicalFixture.
"""
from __future__ import annotations

from typing import List
from datetime import datetime, timezone
from dateutil import parser

from ..contracts import RawEvent, CanonicalFixture


def _parse_event_time(raw_ts):
    if raw_ts is None:
        return None
    if isinstance(raw_ts, datetime):
        if raw_ts.tzinfo is None:
            return raw_ts.replace(tzinfo=timezone.utc)
        return raw_ts.astimezone(timezone.utc)
    if isinstance(raw_ts, (int, float)):
        return datetime.fromtimestamp(raw_ts, tz=timezone.utc)
    if isinstance(raw_ts, str):
        dt = parser.isoparse(raw_ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    return None


def normalize_raw_events(raw_events: List[RawEvent]) -> List[CanonicalFixture]:
    fixtures: List[CanonicalFixture] = []
    for re in raw_events:
        d = re.data
        # conservative mapping with defensive defaults
        home = d.get("home") or d.get("home_team") or d.get("team_home") or ""
        away = d.get("away") or d.get("away_team") or d.get("team_away") or ""
        event_ts_raw = d.get("event_time") or d.get("start_time") or d.get("timestamp")
        event_ts = _parse_event_time(event_ts_raw)
        if event_ts is None:
            # fallback to fetched_at so every fixture has an event_time; could also raise
            event_ts = re.fetched_at
        fixtures.append(CanonicalFixture(external_id=re.external_id, home_team=home, away_team=away, event_time=event_ts, metadata={"raw_source": re.source}))
    return fixtures
