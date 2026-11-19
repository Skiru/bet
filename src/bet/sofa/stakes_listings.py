"""Refresh the cached team listings a national group's stakes flag reads
(operator 2026-11-19; display only - bet.sofa.stakes_groups).

`stakes_groups.group_events` rebuilds a national group's table from the
`last` / `next` team listings the cache already holds and never asks the
network. Measured on 2026-11-14..18 (81 national fixtures): 23 were
INCOMPLETE_GROUP (AFCON qualifiers - the October games were on no cached
page) and 5 STALE (CONCACAF Nations League B - games played days earlier
still `notstarted` in the cache). This step asks, before the coupon is
assembled, page 0 of each group team's `last` and `next` listing
(`/team/{id}/events/{kind}/0`, the route RESOLVE / SAMPLES /
backfill_listings use; written through `SofaCache.save_entity_events`, so
the listed-event index learns the finished copies too), for the day's
not-yet-started men's national group fixtures only: both sides first, then
the group's other teams as their refreshed listings name them, at most
`stakes_groups.GROUP_MAX_TEAMS` per group (the same walk `group_events`
makes). A team shared by two fixtures is asked once per run.

Freshness (UNFITTED): a page fetched within `FRESH_H` hours - by this step
(its record, `stakes_listings.json` in the day's directory, which also keeps
a 404 / empty answer) or by any other writer of the cache - is not asked
again, unless it was fetched before a group game it shows unfinished could
have ended (start + `GAME_H` <= now): that page cannot hold the result.

Refusals: a 403 / 429, the breaker open or tripped, or `MAX_ERROR_STREAK`
failures in a row stop the step at once; the coupon still builds (the flags
are display only, a missing result is STALE / INCOMPLETE_GROUP = no flag).
No fixture in scope = no client, zero requests. Changes no leg, confidence,
gate or ranking - only which games the flags' tables see - so no epoch
switch.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from bet.sofa import stakes_groups as sg
from bet.sofa.errors import CircuitOpenError, ProviderError

RECORD_FILE = "stakes_listings.json"
FRESH_H = 6.0          # a page fetched within this many hours is not re-asked
GAME_H = 2.5           # a national game is over this long after its start
MAX_ERROR_STREAK = 2   # failures in a row that stop the step
PAGES: tuple[tuple[str, int], ...] = (("last", 0), ("next", 0))
UNFITTED_CONSTANTS = ("FRESH_H", "GAME_H", "MAX_ERROR_STREAK")

# (team id, kind, page) -> the payload, None on a 404; raises ProviderError /
# CircuitOpenError like SofascoreClient.entity_events.
Ask = Callable[[int, str, int], Any]
# (team id, kind, page, payload) -> None, like SofaCache.save_entity_events.
Save = Callable[[int, str, int, dict[str, Any]], None]


def _utc(raw: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None


def _iso(t: datetime) -> str:
    return t.isoformat().replace("+00:00", "Z")


def open_national(fixtures: Iterable[Mapping[str, Any]],
                  now: datetime) -> list[Mapping[str, Any]]:
    """The day's football fixtures (02_fixtures.json rows) of a competition
    in stakes_groups.NATIONAL whose kickoff is still ahead."""
    out = []
    for f in fixtures:
        if f.get("sport") != "football" or f.get("competition_id") not in sg.NATIONAL:
            continue
        if not isinstance(f.get("sofascore_event_id"), int):
            continue
        ko = _utc(f.get("kickoff_utc"))
        if ko is not None and ko > now:
            out.append(f)
    return out


def page_fetched_at(con: sqlite3.Connection, team: int, kind: str,
                    page: int) -> datetime | None:
    try:
        row = con.execute(
            "SELECT fetched_at FROM sofa_entity_events WHERE "
            "sofascore_entity_id = ? AND kind = ? AND page = ?",
            (team, kind, page)).fetchone()
    except sqlite3.OperationalError:
        return None
    return _utc(row[0]) if row else None


def _unfinished_starts(con: sqlite3.Connection, team: int,
                       key: tuple[int, int, int], since_ts: int) -> list[int]:
    """Starts of the team's cached group games not shown finished."""
    out = []
    for e in sg.entity_events(con, team, since_ts):
        if sg.tournament_ids(e) != key:
            continue
        status = str((e.get("status") or {}).get("type") or "")
        ts = e.get("startTimestamp")
        if status != "finished" and isinstance(ts, int):
            out.append(ts)
    return out


@dataclass
class Result:
    fixtures_in_scope: int = 0
    groups: int = 0
    teams: int = 0
    requests: int = 0
    saved: int = 0
    empty: int = 0
    fresh_skipped: int = 0
    errors: int = 0
    stopped: str | None = None
    no_payload: int = 0
    out_of_group_scope: int = 0
    asked: list[str] = field(default_factory=list)

    def metrics(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if k != "asked"}


class Refresher:
    """One run over the day's fixtures; `record` is the day's
    stakes_listings.json `pages` map, updated in place."""

    def __init__(self, con: sqlite3.Connection, ask: Ask, save: Save,
                 now: datetime, record: dict[str, dict[str, Any]],
                 tripped: Callable[[], bool] = lambda: False) -> None:
        self.con, self.ask, self.save, self.now = con, ask, save, now
        self.record, self.tripped = record, tripped
        self.result = Result()
        self.done: set[int] = set()
        self.streak = 0

    def _fresh(self, team: int, kind: str, page: int,
               unfinished: Sequence[int]) -> bool:
        cut = self.now - timedelta(hours=FRESH_H)
        seen: list[datetime] = []
        rec = self.record.get(f"{team}/{kind}/{page}") or {}
        if rec.get("status") in ("OK", "EMPTY") and (
                t := _utc(rec.get("asked_at_utc"))) is not None:
            seen.append(t)
        if (t := page_fetched_at(self.con, team, kind, page)) is not None:
            seen.append(t)
        if not seen or max(seen) < cut:
            return False
        newest = max(seen).timestamp()
        over = self.now.timestamp() - GAME_H * 3600
        # a page fetched before a game it shows unfinished could have ended
        return not any(ts <= over and newest < ts + GAME_H * 3600
                       for ts in unfinished)

    def _team(self, team: int, key: tuple[int, int, int], since_ts: int) -> None:
        unfinished = _unfinished_starts(self.con, team, key, since_ts)
        for kind, page in PAGES:
            if self.result.stopped:
                return
            if self._fresh(team, kind, page, unfinished):
                self.result.fresh_skipped += 1
                continue
            self.result.requests += 1
            self.result.asked.append(f"{team}/{kind}/{page}")
            try:
                payload = self.ask(team, kind, page)
            except CircuitOpenError:
                self.result.stopped = "BREAKER_OPEN"
                return
            except ProviderError as exc:
                self.result.errors += 1
                self.streak += 1
                self.record[f"{team}/{kind}/{page}"] = {
                    "asked_at_utc": _iso(self.now), "status": "ERROR",
                    "error": str(exc)[:120]}
                if "403" in str(exc) or "429" in str(exc):
                    self.result.stopped = f"REFUSED: {exc}"
                elif self.tripped():
                    self.result.stopped = "BREAKER_TRIPPED"
                elif self.streak >= MAX_ERROR_STREAK:
                    self.result.stopped = f"{self.streak} failures in a row"
                continue
            self.streak = 0
            if isinstance(payload, dict) and payload.get("events"):
                self.save(team, kind, page, payload)
                self.result.saved += 1
                status = "OK"
            else:
                self.result.empty += 1
                status = "EMPTY"
            self.record[f"{team}/{kind}/{page}"] = {
                "asked_at_utc": _iso(self.now), "status": status}

    def fixture(self, row: Mapping[str, Any]) -> None:
        eid = int(row["sofascore_event_id"])
        payload = sg.fixture_payload(self.con, eid)
        if payload is None:
            self.result.no_payload += 1
            return
        key = sg.group_key(payload)
        me = sg.game_of(payload)
        if key is None or me is None:
            self.result.out_of_group_scope += 1
            return
        self.result.groups += 1
        since = me.ts - sg.LISTING_DAYS * 86400
        queue, seen = [me.home, me.away], {me.home, me.away}
        walked = 0
        while queue and walked < sg.GROUP_MAX_TEAMS and not self.result.stopped:
            team = queue.pop(0)
            walked += 1
            if team not in self.done:
                self.done.add(team)
                self.result.teams += 1
                self._team(team, key, since)
            for e in sg.entity_events(self.con, team, since):
                if sg.tournament_ids(e) != key:
                    continue
                for side in ("homeTeam", "awayTeam"):
                    tid = (e.get(side) or {}).get("id")
                    if isinstance(tid, int) and tid not in seen:
                        seen.add(tid)
                        queue.append(tid)

    def run(self, fixtures: Sequence[Mapping[str, Any]]) -> Result:
        scope = open_national(fixtures, self.now)
        self.result.fixtures_in_scope = len(scope)
        for row in scope:
            if self.result.stopped:
                break
            self.fixture(row)
        return self.result


def load_record(run: Path) -> dict[str, Any]:
    path = run / RECORD_FILE
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"pages": {}, "runs": []}
    if not isinstance(doc, dict):
        return {"pages": {}, "runs": []}
    doc.setdefault("pages", {})
    doc.setdefault("runs", [])
    return doc
