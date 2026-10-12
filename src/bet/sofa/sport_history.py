"""Keep the measured sports' game history current (hockey, basketball, volleyball).

Why this exists. The score model of SPORT_CONFIDENCE and the sport fits
(`fit_sport_confidence.py`, the morning `refresh_line_evidence.py`) read the
sport's history from the cached team listings and the listed-event index
(`score_model.load_events`). Football and tennis keep theirs current because
SAMPLES re-asks every board team's `last` pages each day; the measured sports
have no SAMPLES. SPORT_IDENTITY asks the teams' listings *before* the game, so a
game entered the cache as `notstarted` (or not at all) and its result never
did: of the settled Superbet games of 2026-10-07..10-11 only 0-30% were in the
history (hockey 10-07: 0 of 68), the live model priced 10-12 from a history that
stopped on 10-04, and the line evidence was fitted on the few games it still
saw.

This asks Sofascore `/event/{id}` once for every game of the sport that should
have ended (started > `min_age_h` ago, inside `days`) and that the history does
not hold as finished - candidates from the cached `next` / `last` pages, the
index itself and the day's pinned SPORT_IDENTITY ids - and writes the answer
into the listed-event index as a `last`-listing member of both teams
(`listing_index.index_page`, the newer fetch wins). A game still not finished
(postponed, in play) is written too: the reader keeps only finished games.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from bet.sofa.listing_index import LISTED_EVENT, event_sport, index_page

# Sofascore sport slugs of the measured sports with a score-model history.
SLUGS: dict[str, str] = {"hockey": "ice-hockey", "basketball": "basketball",
                         "volleyball": "volleyball"}
# A game is asked for only once it should be over (start + this).
MIN_AGE_H = 3.0
DAYS = 14


def _finished(event: Mapping[str, Any]) -> bool:
    return ((event.get("status") or {}).get("type")) == "finished"


def _events_of(payload: Any) -> list[dict[str, Any]]:
    events = payload.get("events") if isinstance(payload, dict) else None
    return [e for e in events or [] if isinstance(e, dict)
            and isinstance(e.get("id"), int)]


@dataclass
class Candidates:
    """Event ids per sport slug that should be asked, and why."""
    ids: dict[str, set[int]] = field(default_factory=dict)
    already_finished: dict[str, int] = field(default_factory=dict)

    def total(self) -> int:
        return sum(len(v) for v in self.ids.values())


def candidates(conn: sqlite3.Connection, slugs: Iterable[str], lo_ts: int,
               hi_ts: int, pinned: Mapping[str, Iterable[int]] | None = None
               ) -> Candidates:
    """Games of `slugs` started in [lo_ts, hi_ts] that the index does not hold
    as finished: from the cached team listings (`next` and `last`), the index
    and `pinned` (slug -> Sofascore ids SPORT_IDENTITY pinned)."""
    wanted = set(slugs)
    finished: dict[str, set[int]] = {s: set() for s in wanted}
    seen: dict[str, set[int]] = {s: set() for s in wanted}
    for event_id, sport, event_json in conn.execute(
            f"SELECT event_id, sport, event_json FROM {LISTED_EVENT} "
            "WHERE start_ts BETWEEN ? AND ?", (lo_ts, hi_ts)):
        if sport not in wanted:
            continue
        try:
            event = json.loads(event_json)
        except (TypeError, ValueError):
            continue
        (finished if _finished(event) else seen)[sport].add(int(event_id))
    for (events_json,) in conn.execute(
            "SELECT events_json FROM sofa_entity_events "
            "WHERE kind IN ('next', 'last')"):
        try:
            payload = json.loads(events_json)
        except (TypeError, ValueError):
            continue
        for event in _events_of(payload):
            sport = event_sport(event)
            start = event.get("startTimestamp")
            if sport in wanted and isinstance(start, int) \
                    and lo_ts <= start <= hi_ts:
                seen[sport].add(int(event["id"]))
    for sport, ids in (pinned or {}).items():
        if sport in wanted:
            seen[sport].update(int(i) for i in ids)
    out = Candidates()
    for sport in sorted(wanted):
        out.ids[sport] = seen[sport] - finished[sport]
        out.already_finished[sport] = len(finished[sport])
    return out


def pinned_ids(runs_dir: str | Path, sport_key: str, dates: Iterable[str]
               ) -> set[int]:
    """Sofascore ids SPORT_IDENTITY pinned for the sport on `dates`
    (runs/sofa/<d>/sport_fixtures.json)."""
    out: set[int] = set()
    for day in dates:
        path = Path(runs_dir) / day / "sport_fixtures.json"
        if not path.exists():
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for row in _fixture_rows(doc):
            if row.get("sport") == sport_key and isinstance(
                    row.get("sofascore_event_id"), int):
                out.add(int(row["sofascore_event_id"]))
    return out


def _fixture_rows(doc: Any) -> list[dict[str, Any]]:
    if isinstance(doc, list):
        return [r for r in doc if isinstance(r, dict)]
    if not isinstance(doc, dict):
        return []
    rows: list[dict[str, Any]] = []
    for value in doc.values():
        if isinstance(value, list):
            rows.extend(r for r in value if isinstance(r, dict))
        elif isinstance(value, dict):
            rows.extend(_fixture_rows(value))
    return rows


def store_event(conn: sqlite3.Connection, event: Mapping[str, Any],
                fetched_at: str) -> int:
    """Index one `/event/{id}` payload as a `last`-listing member of both
    teams; the caller commits. Returns rows written (0 when unusable)."""
    try:
        teams = (int(event["homeTeam"]["id"]), int(event["awayTeam"]["id"]))
    except (KeyError, TypeError, ValueError):
        return 0
    written = 0
    for team in teams:
        written = index_page(conn, team, "last", fetched_at,
                             {"events": [dict(event)]})
    return written


@dataclass
class Result:
    asked: int = 0
    finished: int = 0
    not_finished: int = 0
    missing: int = 0  # Sofascore answered nothing (404 / error)
    stopped: str | None = None


def refresh(conn: sqlite3.Connection, ids: Iterable[int],
            fetch: Callable[[int], Any], now_iso: Callable[[], str],
            deadline: Callable[[], bool] = lambda: False) -> Result:
    """Ask each id, store what answers, commit after each write. `fetch`
    returns the `/event/{id}` payload or None; it may raise to stop (the
    breaker), which is recorded and ends the run."""
    out = Result()
    for event_id in sorted(ids):
        if deadline():
            out.stopped = "deadline"
            break
        try:
            payload = fetch(event_id)
        except Exception as exc:  # noqa: BLE001 - the breaker or the bridge: stop
            out.stopped = f"{type(exc).__name__}: {exc}"
            break
        out.asked += 1
        event = payload.get("event") if isinstance(payload, dict) else None
        if not isinstance(event, dict) or event.get("id") != event_id:
            out.missing += 1
            continue
        if store_event(conn, event, now_iso()):
            conn.commit()
        if _finished(event):
            out.finished += 1
        else:
            out.not_finished += 1
    return out


def coverage(conn: sqlite3.Connection, ids: Iterable[int]) -> tuple[int, int]:
    """(finished in the history, asked about) for Sofascore ids - the day
    status' check that the score model knows yesterday's games."""
    wanted = sorted(set(int(i) for i in ids))
    done = 0
    for i in range(0, len(wanted), 500):
        chunk = wanted[i:i + 500]
        marks = ",".join("?" * len(chunk))
        for (event_json,) in conn.execute(
                f"SELECT event_json FROM {LISTED_EVENT} "
                f"WHERE event_id IN ({marks})", chunk):
            try:
                if _finished(json.loads(event_json)):
                    done += 1
            except (TypeError, ValueError):
                continue
    return done, len(wanted)
