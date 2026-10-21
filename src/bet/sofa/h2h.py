"""Head-to-head meetings asked of Sofascore for every match an analyst reads.

Operator 2026-10-21 (Real Madrid - RB Leipzig): the dossier's h2h was empty
because it searched only the cached team listings - Real's begin 2024-04-30,
the last meeting was 2024-03-06 - and nothing said the cache stopped short.
"Musi pobierać h2h zawsze": every read-set writer now asks
`/event/{customId}/h2h/events` for its matches first and keeps the answer in
`runs/sofa/<d>/h2h.json`; each finished meeting's statistics and incidents go
into the cache like any past match's, so the dossier can show the legs'
metrics in the meetings.

Display only: the dossier reads this file; SAMPLES, a confidence and every
gate never do (an h2h pool in a sample is SAMPLES' own, from its listings).
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from bet.sofa.atomic import write_atomic
from bet.sofa.errors import CircuitOpenError, SofaError

FILE = "h2h.json"
MEETINGS_N = 6  # newest finished meetings whose statistics are fetched
OK = "OK"


class Client(Protocol):
    def event(self, id: int) -> Any | None: ...
    def event_h2h_events(self, custom_id: str) -> Any | None: ...
    def event_statistics(self, id: int) -> Any | None: ...
    def event_incidents(self, id: int) -> Any | None: ...


class Cache(Protocol):
    def get_event_detail(self, sofascore_event_id: int) -> dict[str, Any] | None: ...
    def get_event_stats(
        self, sofascore_event_id: int, kickoff_ts: int | None = None
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None, str] | None: ...
    def save_event_stats(
        self,
        sofascore_event_id: int,
        statistics: dict[str, Any] | None,
        incidents: dict[str, Any] | None,
        status_type: str,
    ) -> None: ...


def path(run: Path) -> Path:
    return run / FILE


def load(run: Path) -> dict[str, dict[str, Any]]:
    """{event id (str): entry}; {} when the file is missing or unreadable."""
    try:
        doc = json.loads(path(run).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    events = doc.get("events") if isinstance(doc, dict) else None
    return events if isinstance(events, dict) else {}


def _event(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    event = payload.get("event", payload)
    return event if isinstance(event, dict) else None


def meetings_of(payload: Any, event_id: int) -> list[dict[str, Any]]:
    """Finished meetings of the h2h answer, newest first, the fixture itself
    and unfinished games left out."""
    events = payload.get("events") if isinstance(payload, dict) else None
    out = [
        e
        for e in events or []
        if isinstance(e, dict)
        and isinstance(e.get("id"), int)
        and e["id"] != event_id
        and isinstance(e.get("startTimestamp"), int)
        and (e.get("status") or {}).get("type") == "finished"
    ]
    return sorted(out, key=lambda e: -int(e["startTimestamp"]))


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_one(client: Client, cache: Cache, event_id: int) -> dict[str, Any]:
    """One match's h2h entry. Raises CircuitOpenError (the caller stops);
    any other provider error is the entry's status."""
    entry: dict[str, Any] = {"fetched_at_utc": _now()}
    try:
        detail = _event(cache.get_event_detail(event_id)) or _event(
            client.event(event_id))
        custom_id = (detail or {}).get("customId")
        if not isinstance(custom_id, str) or not custom_id:
            return {**entry, "status": "NO_CUSTOM_ID", "meetings": []}
        entry["custom_id"] = custom_id
        meetings = meetings_of(client.event_h2h_events(custom_id), event_id)
        entry["meetings"] = meetings
        stats_missing = []
        for meeting in meetings[:MEETINGS_N]:
            mid = int(meeting["id"])
            if cache.get_event_stats(mid) is not None:
                continue
            statistics = client.event_statistics(mid)
            incidents = client.event_incidents(mid)
            if statistics is None and incidents is None:
                stats_missing.append(mid)
                continue
            cache.save_event_stats(mid, statistics, incidents, "finished")
        if stats_missing:
            entry["stats_missing"] = stats_missing
        entry["status"] = OK
        return entry
    except CircuitOpenError:
        raise
    except SofaError as exc:
        return {**entry, "status": f"FAILED {type(exc).__name__}: {exc}",
                "meetings": entry.get("meetings", [])}


def fetch(
    run: Path, event_ids: Iterable[int], client: Client, cache: Cache
) -> dict[str, int]:
    """Ask the h2h of every match not yet answered OK today; every old entry
    kept. Writes h2h.json after each match (a stopped run keeps its answers).
    Returns a status count."""
    entries = load(run)
    counts: dict[str, int] = {}
    todo = [e for e in dict.fromkeys(event_ids)
            if (entries.get(str(e)) or {}).get("status") != OK]
    for i, event_id in enumerate(todo):
        try:
            entry = fetch_one(client, cache, event_id)
        except CircuitOpenError:
            for rest in todo[i:]:
                entries.setdefault(str(rest), {}).update(
                    fetched_at_utc=_now(), status="FAILED breaker open")
            counts["FAILED"] = counts.get("FAILED", 0) + len(todo) - i
            break
        entries[str(event_id)] = entry
        key = entry["status"].split(" ")[0]
        counts[key] = counts.get(key, 0) + 1
        _write(run, entries)
    _write(run, entries)
    counts["cached"] = len(set(map(str, event_ids))) - len(todo)
    return counts


def _write(run: Path, entries: Mapping[str, Any]) -> None:
    write_atomic(path(run), json.dumps(
        {"source": "Sofascore /event/{customId}/h2h/events", "events": entries},
        ensure_ascii=False, indent=1) + "\n")


def fetch_for_legs(run: Path, legs: Iterable[Mapping[str, Any]]) -> str:
    """fetch for a read-set writer, through the bridge: one line for its
    output. A failure is reported, never raised - the dossier then says the
    h2h was not asked and the web checklist asks for it."""
    ids = [int(x["sofascore_event_id"]) for x in legs
           if isinstance(x.get("sofascore_event_id"), int)]
    if not ids:
        return "h2h: brak meczów"
    try:
        from bet.sofa.cache import SofaCache
        from bet.sofa.client import SofascoreClient
        from bet.sofa.config import SofaConfig

        config = SofaConfig.from_env()
        counts = fetch(run, ids, SofascoreClient(config), SofaCache(config))
    except Exception as exc:  # noqa: BLE001 - reported, the read set goes on
        return f"h2h: BŁĄD {type(exc).__name__}: {exc} - dossier bez pobranego h2h"
    return "h2h: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items()))
