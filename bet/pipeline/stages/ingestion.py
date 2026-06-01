"""Ingestion stage: fetches raw events from adapters and returns RawEvent objects.

This stage is pure with respect to business logic: it calls adapters to fetch
raw payloads, wraps them in RawEvent dataclasses and returns the list.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from ..contracts import RawEvent


class BookmakerAdapterProtocol:
    def fetch_events(self, date) -> List[dict]:
        """Adapter must return a list of raw dict payloads for the given date."""
        raise NotImplementedError


def ingest_events(date, adapter: BookmakerAdapterProtocol, source_name: str = "bookmaker") -> List[RawEvent]:
    raw = adapter.fetch_events(date)
    events: List[RawEvent] = []
    for payload in raw:
        external_id = str(payload.get("id") or payload.get("external_id", ""))
        fetched_at = datetime.now(timezone.utc)
        evt = RawEvent(source=source_name, external_id=external_id, data=payload, fetched_at=fetched_at)
        events.append(evt)
    return events
