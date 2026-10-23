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
from datetime import datetime
from pathlib import Path
from typing import Any

from bet.sofa import epochs
from bet.sofa.listing_index import (
    LISTED_EVENT,
    LISTING_EVENT,
    event_sport,
    index_page,
)

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
               hi_ts: int, pinned: Mapping[str, Mapping[int, int]] | None = None
               ) -> Candidates:
    """Games of `slugs` started in [lo_ts, hi_ts] that the index does not hold
    as finished: from the cached team listings (`next` and `last`), the index
    and `pinned` (slug -> {Sofascore id: Superbet start ts} SPORT_IDENTITY
    pinned; only those started inside the window)."""
    wanted = set(slugs)
    finished: dict[str, set[int]] = {s: set() for s in wanted}
    seen: dict[str, set[int]] = {s: set() for s in wanted}
    # Finished anywhere in the index (not only inside the window): a pinned
    # game whose stored start drifted out of the window is not re-asked.
    marks = ",".join("?" * len(wanted))
    for event_id, sport, start_ts, event_json in conn.execute(
            f"SELECT event_id, sport, start_ts, event_json FROM {LISTED_EVENT} "
            f"WHERE sport IN ({marks})", sorted(wanted)):
        try:
            event = json.loads(event_json)
        except (TypeError, ValueError):
            continue
        if _finished(event):
            finished[sport].add(int(event_id))
        elif isinstance(start_ts, int) and lo_ts <= start_ts <= hi_ts:
            seen[sport].add(int(event_id))
    for sport in sorted(wanted):
        # The slug prefilter keeps the scan off football / tennis pages
        # (score_model.load_events does the same).
        for (events_json,) in conn.execute(
                "SELECT events_json FROM sofa_entity_events "
                "WHERE kind IN ('next', 'last') AND events_json LIKE ?",
                (f'%"slug": "{sport}"%',)):
            try:
                payload = json.loads(events_json)
            except (TypeError, ValueError):
                continue
            for event in _events_of(payload):
                start = event.get("startTimestamp")
                if event_sport(event) == sport and isinstance(start, int) \
                        and lo_ts <= start <= hi_ts:
                    seen[sport].add(int(event["id"]))
    for sport, pins in (pinned or {}).items():
        if sport in wanted:
            # Only a pinned game that should have ended: today's games are
            # asked once they are over, never before (bridge budget).
            seen[sport].update(int(i) for i, start in pins.items()
                               if lo_ts <= start <= hi_ts)
    out = Candidates()
    for sport in sorted(wanted):
        out.ids[sport] = seen[sport] - finished[sport]
        out.already_finished[sport] = len(finished[sport])
    return out


def pinned_ids(runs_dir: str | Path, sport_key: str, dates: Iterable[str]
               ) -> dict[int, int]:
    """{Sofascore id: start ts} SPORT_IDENTITY pinned for the sport on
    `dates` (runs/sofa/<d>/sport_fixtures.json); the start is the record's
    kickoff_utc, or 0 when it has none (never asked then)."""
    out: dict[int, int] = {}
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
                out[int(row["sofascore_event_id"])] = _ts(row.get("kickoff_utc"))
    return out


def _ts(raw: Any) -> int:
    if not isinstance(raw, str) or not raw:
        return 0
    try:
        return int(datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp())
    except ValueError:
        return 0


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
    missing: int = 0  # Sofascore answered nothing (404: a deleted game)
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


# --- a game in both teams' lists (audit 2026-10-23 B9 / P9) -----------------
#
# A `last` page indexes its events under the page's OWNER only
# (listing_index.index_page), and `candidates` takes a game the index holds as
# finished as done - so a game seen only on one team's page never reaches the
# other team's list (store_event, which writes both, is never called for it).
# player_model.listed_games reads a team's games from its own list, so that
# team's players lose the game: Vancouver @ Florida 16546356 (2026-10-15
# 23:00Z) is in Florida's list (3687) and not Vancouver's (3692). Counted
# 2026-10-23 on data/sofa.db (finished games, one side missing): 42,892 sides
# in the whole index, 8,514 with a start in the last 400 days (hockey 1,241,
# basketball 7,273 games).
#
# The fix needs no network: the stored payload names both teams. The missing
# side is written under its own kind, OPPONENT_KIND, never `last` - no reader
# that asks for `last` (SAMPLES' entity_indexed_events, the refits, the
# one-time fill's checks) sees a row it did not see before, and a reader
# switched by epochs.player_both_sides_listed reads both (listed_rows).
OPPONENT_KIND = "last_side"
# The sports whose player model reads team lists (player_model: hockey and
# basketball).
BOTH_SIDES_SLUGS: tuple[str, ...] = ("ice-hockey", "basketball")


@dataclass(frozen=True)
class MissingSide:
    event_id: int
    team_id: int
    start_ts: int | None
    fetched_at: str


def missing_sides(conn: sqlite3.Connection,
                  slugs: Iterable[str] = BOTH_SIDES_SLUGS
                  ) -> list[MissingSide]:
    """Every finished indexed game of `slugs` whose payload names a team
    (home or away) with neither a `last` nor an OPPONENT_KIND row for it in
    the listing index, oldest first. Read-only."""
    wanted = sorted(set(slugs))
    if not wanted:
        return []
    marks = ",".join("?" * len(wanted))
    out: list[MissingSide] = []
    # json_extract in SQL: no payload crosses into Python; each side's check
    # is a seek on the members' primary key (entity_id, kind, event_id).
    sql = f"""
        WITH ev AS (
            SELECT event_id, start_ts, fetched_at,
                   json_extract(event_json, '$.homeTeam.id') AS home,
                   json_extract(event_json, '$.awayTeam.id') AS away
            FROM {LISTED_EVENT}
            WHERE sport IN ({marks})
              AND json_valid(event_json)
              AND json_extract(event_json, '$.status.type') = 'finished')
        SELECT s.event_id, s.start_ts, s.fetched_at, s.team FROM (
            SELECT event_id, start_ts, fetched_at, home AS team, 0 AS side FROM ev
            UNION ALL
            SELECT event_id, start_ts, fetched_at, away AS team, 1 AS side FROM ev
        ) AS s
        WHERE typeof(s.team) = 'integer'
          AND NOT EXISTS (
            SELECT 1 FROM {LISTING_EVENT} m
            WHERE m.entity_id = s.team AND m.kind IN ('last', ?)
              AND m.event_id = s.event_id)
        ORDER BY s.start_ts, s.event_id, s.side"""
    for event_id, start_ts, fetched_at, team in conn.execute(
            sql, (*wanted, OPPONENT_KIND)):
        out.append(MissingSide(int(event_id), int(team),
                               start_ts if isinstance(start_ts, int) else None,
                               str(fetched_at)))
    return out


def list_both_sides(conn: sqlite3.Connection,
                    slugs: Iterable[str] = BOTH_SIDES_SLUGS) -> int:
    """Write every missing side (missing_sides) as an OPPONENT_KIND member of
    that team's list, stamped with the payload's own fetch; the caller
    commits. Offline, idempotent: a second run writes nothing. Returns rows
    written."""
    rows = [(m.team_id, OPPONENT_KIND, m.event_id, m.start_ts, m.fetched_at)
            for m in missing_sides(conn, slugs)]
    conn.executemany(
        f"INSERT OR IGNORE INTO {LISTING_EVENT} "
        "(entity_id, kind, event_id, start_ts, fetched_at) VALUES (?, ?, ?, ?, ?)",
        rows)
    return len(rows)


def listing_kinds(date: str, build_at: datetime | None = None
                  ) -> tuple[str, ...]:
    """The list kinds a team's games are read from on `date` at `build_at`:
    `last` alone, and OPPONENT_KIND too from
    epochs.PLAYER_BOTH_SIDES_LISTED_FROM_UTC."""
    if epochs.player_both_sides_listed(date, build_at):
        return ("last", OPPONENT_KIND)
    return ("last",)


def listed_rows(conn: sqlite3.Connection, team_id: int, before_ts: int,
                limit: int, kinds: Iterable[str] = ("last",)
                ) -> list[tuple[int, int, str | None]]:
    """(event id, start, payload JSON or None) of a team's newest listed games
    before `before_ts`, newest first, one row per game - the query
    player_model.listed_games ran, over `kinds` (listing_kinds). With
    ("last",) the rows are exactly the old query's."""
    kind_list = sorted(set(kinds))
    marks = ",".join("?" * len(kind_list))
    rows = conn.execute(
        "SELECT l.event_id, MIN(l.start_ts), e.event_json "
        f"FROM {LISTING_EVENT} l "
        f"LEFT JOIN {LISTED_EVENT} e ON e.event_id = l.event_id "
        f"WHERE l.entity_id = ? AND l.kind IN ({marks}) AND l.start_ts < ? "
        "GROUP BY l.event_id "
        "ORDER BY MIN(l.start_ts) DESC LIMIT ?",
        (int(team_id), *kind_list, int(before_ts), int(limit)),
    ).fetchall() if len(kind_list) > 1 else conn.execute(
        "SELECT l.event_id, l.start_ts, e.event_json "
        f"FROM {LISTING_EVENT} l "
        f"LEFT JOIN {LISTED_EVENT} e ON e.event_id = l.event_id "
        "WHERE l.entity_id = ? AND l.kind = ? AND l.start_ts < ? "
        "ORDER BY l.start_ts DESC LIMIT ?",
        (int(team_id), kind_list[0], int(before_ts), int(limit)),
    ).fetchall()
    return [(int(r[0]), int(r[1]), r[2]) for r in rows]

