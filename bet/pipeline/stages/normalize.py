"""Normalize stage: convert raw events into canonical fixtures.

Pure function: input list of RawEvent -> output list of CanonicalFixture.
"""
from __future__ import annotations

from typing import List
from ..contracts import RawEvent, CanonicalFixture


def normalize_raw_events(raw_events: List[RawEvent]) -> List[CanonicalFixture]:
    fixtures: List[CanonicalFixture] = []
    for re in raw_events:
        d = re.data
        # conservative mapping with defensive defaults
        home = d.get("home") or d.get("home_team") or d.get("team_home") or ""
        away = d.get("away") or d.get("away_team") or d.get("team_away") or ""
        event_ts = d.get("event_time") or d.get("start_time") or d.get("timestamp")
        # if event_ts is str or numeric, callers/tests should provide datetime in adapters; keep as-is here
        fixtures.append(CanonicalFixture(external_id=re.external_id, home_team=home, away_team=away, event_time=event_ts, metadata={"raw_source": re.source}))
    return fixtures
