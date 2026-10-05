"""Pre-match Sofascore identity of hockey, basketball, volleyball and CS2
Superbet events (plan 2026-10-05, F1).

SHADOW and CS2 read Superbet only, and the cache has no upcoming games of
these sports, so before a leg of theirs can be on the coupon its Sofascore
event must be found - once a day, one request per match, through the bridge.
That id is then pinned: SETTLE grades the leg by it and never searches again.

Per Superbet event of the day:

1. C5 first: a team name (folded) in two or more Superbet events whose starts
   are under DUPLICATE_WINDOW apart makes every one of them
   DUPLICATE_SUPERBET_TEAM - out of the coupon, never graded (10-05: Vitality
   Academy in two series at 10:30Z).
2. The teams' Sofascore ids offline: hockey / basketball / volleyball as
   player_model.resolve_team (RESOLVE's verified entity, else an exact
   normalised name naming one team in the listed games); CS2 an exact folded
   name naming one team in cs2_series.
3. One listing request, `team/<id>/events/next/0`, for team1 (team2 when
   team1 has no id), cached with the events TTL (SofaCache). A refusal (403,
   any provider error, an open breaker) aborts the run: no retry, every event
   not yet tried is NOT_IDENTIFIED (BRIDGE_ABORTED).
4. In the response, the one event that is this game: the sport's category,
   Sofascore's start within MAX_START_GAP of Superbet's, the gender of the
   board, and BOTH sides named - a side's Sofascore id equal to the id
   resolved for it, or its name scoring above NAME_MATCH_THRESHOLD against
   it (resolve.name_score over normalize_name, which carries the aliases);
   CS2 through cs2.pick_event (both names above the threshold with
   cs2.esports_score) and the same start rule. Two fitting events, or one
   that reads both ways round, is AMBIGUOUS.
5. Unique in the day: two Superbet events found as one Sofascore id are both
   DUPLICATE_SOFASCORE_ID.

Anything else is NOT_IDENTIFIED, with the reason, and stays off the coupon.
"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

from bet.sofa import cs2
from bet.sofa.comparability import competition_id
from bet.sofa.errors import CircuitOpenError, ProviderError
from bet.sofa.names import normalize_name
from bet.sofa.player_model import resolve_team, team_name_index
from bet.sofa.resolve import (
    NAME_MATCH_THRESHOLD,
    name_score,
    sofascore_gender,
    superbet_gender,
)
from bet.sofa.shadow import SPORTS

FIXTURES_FILE = "sport_fixtures.json"
SPORT_KEYS = ("hockey", "basketball", "volleyball", "cs2")
MAX_START_GAP = timedelta(hours=1)
DUPLICATE_WINDOW = timedelta(hours=3)

IDENTIFIED = "IDENTIFIED"
NOT_IDENTIFIED = "NOT_IDENTIFIED"
DUPLICATE_SUPERBET_TEAM = "DUPLICATE_SUPERBET_TEAM"
DUPLICATE_SOFASCORE_ID = "DUPLICATE_SOFASCORE_ID"


class ListingClient(Protocol):
    def entity_events(self, entity_id: int, kind: Any, page: int) -> Any | None: ...


class ListingCache(Protocol):
    def get_entity_events(self, sofascore_entity_id: int, kind: str, page: int
                          ) -> dict[str, Any] | None: ...

    def save_entity_events(self, sofascore_entity_id: int, kind: str, page: int,
                           events: dict[str, Any]) -> None: ...


@dataclass(frozen=True)
class BoardEvent:
    """One Superbet event as the day's snapshots last described it."""

    sport: str
    superbet_event_id: str
    match_name: str
    team1: str
    team2: str
    kickoff_utc: str
    tournament: str | None
    source_date: str | None = None

    @property
    def kickoff(self) -> datetime:
        return _utc(self.kickoff_utc)


def _utc(raw: str) -> datetime:
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


def iso(at: datetime) -> str:
    return at.astimezone(UTC).isoformat().replace("+00:00", "Z")


def day_window(date: str) -> tuple[datetime, datetime]:
    """[D 00:00Z, D+1 00:00Z): the day a sport leg belongs to."""
    start = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=UTC)
    return start, start + timedelta(days=1)


def board_events(runs_dir: str, sport: str, date: str) -> list[BoardEvent]:
    """The sport's Superbet events of D's and D+1's snapshot files
    (sport_coupon.day_events: the newest record of an event wins)."""
    from bet.sofa import sport_coupon

    events, _ = sport_coupon.day_events(runs_dir, sport, date)  # type: ignore[arg-type]
    return [BoardEvent(sport, str(ev.superbet_event_id), ev.match_name, ev.team1,
                       ev.team2, ev.kickoff_utc, ev.tournament,
                       getattr(ev, "source_date", None))
            for ev in events.values()]


def fold_team(sport: str, name: str) -> str:
    return cs2.esports_name(name) if sport == "cs2" else normalize_name(name)


def duplicate_team_events(events: Iterable[BoardEvent]) -> dict[str, str]:
    """C5: Superbet event id -> the team name it shares with another event
    of the same sport starting under DUPLICATE_WINDOW apart."""
    by_name: dict[tuple[str, str], list[BoardEvent]] = defaultdict(list)
    for ev in events:
        for name in (ev.team1, ev.team2):
            key = fold_team(ev.sport, name)
            if key:
                by_name[(ev.sport, key)].append(ev)
    out: dict[str, str] = {}
    for (_, key), evs in by_name.items():
        for a in evs:
            for b in evs:
                if (a.superbet_event_id != b.superbet_event_id
                        and abs(a.kickoff - b.kickoff) < DUPLICATE_WINDOW):
                    out[a.superbet_event_id] = key
    return out


# --- team ids, offline ------------------------------------------------------------


def cs2_team_index(conn: sqlite3.Connection) -> dict[str, set[int]]:
    """Folded CS2 team name -> Sofascore team ids, from cs2_series."""
    index: dict[str, set[int]] = defaultdict(set)
    try:
        rows = conn.execute(
            "SELECT home_id, home_name FROM cs2_series "
            "UNION SELECT away_id, away_name FROM cs2_series").fetchall()
    except sqlite3.Error:
        return {}
    for tid, name in rows:
        if tid is not None and name:
            index[cs2.esports_name(str(name))].add(int(tid))
    return dict(index)


@dataclass
class TeamResolver:
    """Superbet team name -> Sofascore team id, offline, never fuzzy."""

    conn: sqlite3.Connection
    now_ts: int
    _indexes: dict[str, dict[str, set[int]]] = field(default_factory=dict)

    def team_id(self, sport: str, name: str) -> int | None:
        if sport == "cs2":
            if "cs2" not in self._indexes:
                self._indexes["cs2"] = cs2_team_index(self.conn)
            ids = self._indexes["cs2"].get(cs2.esports_name(name)) or set()
            return next(iter(ids)) if len(ids) == 1 else None
        slug = SPORTS[sport].sofascore_slug  # type: ignore[index]
        try:
            tid = resolve_team(self.conn, slug, name, {})
            if tid is not None:
                return tid
            if slug not in self._indexes:
                self._indexes[slug] = team_name_index(self.conn, slug, self.now_ts)
            return resolve_team(self.conn, slug, name, self._indexes[slug])
        except sqlite3.Error:
            return None


# --- the listing ------------------------------------------------------------------


class BridgeAbortedError(Exception):
    """The provider refused a request; the run stops asking."""


def next_listing(client: ListingClient, cache: ListingCache | None, team_id: int
                 ) -> tuple[list[dict[str, Any]], bool]:
    """(the team's upcoming events, served from the cache). One request at
    most; a refusal raises BridgeAbortedError and is never retried."""
    if cache is not None:
        cached = cache.get_entity_events(team_id, "next", 0)
        if cached is not None:
            return list(cached.get("events") or []), True
    try:
        payload = client.entity_events(team_id, "next", 0)
    except (ProviderError, CircuitOpenError) as exc:
        raise BridgeAbortedError(str(exc)) from exc
    if payload is None:  # 404: the team has no upcoming games
        payload = {"events": []}
    if cache is not None and isinstance(payload, dict):
        cache.save_entity_events(team_id, "next", 0, payload)
    return list((payload or {}).get("events") or []), False


def _start(event: Mapping[str, Any]) -> datetime | None:
    ts = event.get("startTimestamp")
    return datetime.fromtimestamp(int(ts), UTC) if isinstance(ts, int) else None


def _side(event: Mapping[str, Any], key: str) -> tuple[int | None, str]:
    team = event.get(key) or {}
    tid = team.get("id")
    return (int(tid) if isinstance(tid, int) else None, str(team.get("name") or ""))


def _side_ok(board_name: str, board_id: int | None, ev_id: int | None,
             ev_name: str) -> tuple[bool, float]:
    score = name_score(normalize_name(board_name), normalize_name(ev_name))
    by_id = board_id is not None and ev_id == board_id
    return by_id or score > NAME_MATCH_THRESHOLD, round(score, 1)


def match_shadow(ev: BoardEvent, candidates: Iterable[dict[str, Any]],
                 t1_id: int | None, t2_id: int | None) -> dict[str, Any]:
    """The one listed event that is this Superbet game, or why not."""
    slug = SPORTS[ev.sport].sofascore_slug  # type: ignore[index]
    gender = "W" if "W" in {superbet_gender(ev.team1), superbet_gender(ev.team2)} \
        else "M"
    fits: list[dict[str, Any]] = []
    near = 0
    for e in candidates:
        sport_slug = (((e.get("tournament") or {}).get("category") or {})
                      .get("sport") or {}).get("slug")
        if sport_slug != slug:
            continue
        start = _start(e)
        if start is None or abs(start - ev.kickoff) > MAX_START_GAP:
            continue
        near += 1
        if sofascore_gender(e) != gender:
            continue
        (hid, hname), (aid, aname) = _side(e, "homeTeam"), _side(e, "awayTeam")
        s_h1, sc_h1 = _side_ok(ev.team1, t1_id, hid, hname)
        s_a2, sc_a2 = _side_ok(ev.team2, t2_id, aid, aname)
        c_a1, sc_a1 = _side_ok(ev.team1, t1_id, aid, aname)
        c_h2, sc_h2 = _side_ok(ev.team2, t2_id, hid, hname)
        straight, crossed = s_h1 and s_a2, c_a1 and c_h2
        if straight and crossed:
            return {"status": NOT_IDENTIFIED, "reason": "AMBIGUOUS_ORIENTATION"}
        if not (straight or crossed):
            continue
        by_id = (t1_id is not None and t1_id in (hid, aid)) or (
            t2_id is not None and t2_id in (hid, aid))
        fits.append({
            "event": e,
            "home_is_team1": straight,
            "name_scores": ({"team1": sc_h1, "team2": sc_a2} if straight
                            else {"team1": sc_a1, "team2": sc_h2}),
            "match_method": "LISTING_ID_AND_NAME" if by_id else "LISTING_NAMES",
        })
    if len(fits) > 1:
        return {"status": NOT_IDENTIFIED, "reason": "AMBIGUOUS"}
    if not fits:
        return {"status": NOT_IDENTIFIED,
                "reason": "NO_MATCH_IN_LISTING" if near else "NO_GAME_WITHIN_1H"}
    return {"status": IDENTIFIED, **fits[0]}


def match_cs2(ev: BoardEvent, candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """cs2.pick_event over the team's upcoming series, then the start rule."""
    found = cs2.pick_event(candidates, ev.team1, ev.team2, ev.kickoff)
    if found == "AMBIGUOUS":
        return {"status": NOT_IDENTIFIED, "reason": "AMBIGUOUS"}
    if found is None:
        return {"status": NOT_IDENTIFIED, "reason": "NO_MATCH_IN_LISTING"}
    event, home_is_t1 = found
    start = _start(event)
    if start is None or abs(start - ev.kickoff) > MAX_START_GAP:
        return {"status": NOT_IDENTIFIED, "reason": "START_GAP_OVER_1H",
                "candidate_event_id": event.get("id")}
    home = cs2.esports_name(str((event.get("homeTeam") or {}).get("name") or ""))
    away = cs2.esports_name(str((event.get("awayTeam") or {}).get("name") or ""))
    t1, t2 = cs2.esports_name(ev.team1), cs2.esports_name(ev.team2)
    a, b = (home, away) if home_is_t1 else (away, home)
    scores = {"team1": cs2.esports_score(t1, a), "team2": cs2.esports_score(t2, b)}
    return {"status": IDENTIFIED, "event": event, "home_is_team1": home_is_t1,
            "name_scores": {k: round(v, 1) for k, v in scores.items()},
            "match_method": "CS2_PICK_EVENT"}


def _record(ev: BoardEvent, at: datetime, **extra: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "superbet_event_id": ev.superbet_event_id, "sport": ev.sport,
        "match_name": ev.match_name, "team1": ev.team1, "team2": ev.team2,
        "kickoff_utc": ev.kickoff_utc, "tournament": ev.tournament,
        "source_date": ev.source_date,
        "sofascore_event_id": None, "home_id": None, "away_id": None,
        "home_is_team1": None, "competition_id": None, "match_method": None,
        "name_scores": None, "start_gap_h": None, "matched_at_utc": iso(at),
    }
    base.update(extra)
    return base


def identify_event(ev: BoardEvent, client: ListingClient, cache: ListingCache | None,
                   teams: Callable[[str, str], int | None], at: datetime
                   ) -> dict[str, Any]:
    t1_id, t2_id = teams(ev.sport, ev.team1), teams(ev.sport, ev.team2)
    query = t1_id if t1_id is not None else t2_id
    if query is None:
        return _record(ev, at, status=NOT_IDENTIFIED, reason="TEAM_UNRESOLVED")
    listing, cached = next_listing(client, cache, query)
    found = (match_cs2(ev, listing) if ev.sport == "cs2"
             else match_shadow(ev, listing, t1_id, t2_id))
    extra = {"queried_team_id": query, "listing_from_cache": cached,
             "team1_id": t1_id, "team2_id": t2_id}
    if found["status"] != IDENTIFIED:
        return _record(ev, at, **{k: v for k, v in found.items() if k != "event"},
                       **extra)
    event = found["event"]
    hid, _ = _side(event, "homeTeam")
    aid, _ = _side(event, "awayTeam")
    start = _start(event)
    assert start is not None
    tournament = event.get("tournament") or {}
    rec = _record(
        ev, at, status=IDENTIFIED, reason=None,
        sofascore_event_id=int(event["id"]), home_id=hid, away_id=aid,
        home_is_team1=bool(found["home_is_team1"]),
        competition_id=competition_id(event) or tournament.get("id"),
        match_method=found["match_method"], name_scores=found["name_scores"],
        start_gap_h=round((start - ev.kickoff).total_seconds() / 3600, 2),
        sofascore_start_utc=iso(start),
        sofascore_match=f"{(event.get('homeTeam') or {}).get('name')} - "
                        f"{(event.get('awayTeam') or {}).get('name')}",
        sofascore_tournament=tournament.get("name"),
        **extra)
    if ev.sport == "cs2":
        best_of = event.get("bestOf")
        rec["best_of"] = int(best_of) if isinstance(best_of, int) else None
    return rec


def identify(events: list[BoardEvent], client: ListingClient,
             cache: ListingCache | None, teams: Callable[[str, str], int | None],
             at: datetime, date: str,
             pinned: Mapping[str, dict[str, Any]] | None = None
             ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Every event of the day's window identified or refused, and the
    per-sport counts. `pinned`: records of an earlier run that were
    IDENTIFIED - kept as they are, never asked again."""
    start, end = day_window(date)
    in_day = [ev for ev in events if start <= ev.kickoff < end]
    dup = duplicate_team_events(events)
    pinned = pinned or {}
    records: list[dict[str, Any]] = []
    aborted: str | None = None
    for ev in sorted(in_day, key=lambda e: (e.kickoff_utc, e.superbet_event_id)):
        prev = pinned.get(ev.superbet_event_id)
        if ev.superbet_event_id in dup:
            records.append(_record(ev, at, status=DUPLICATE_SUPERBET_TEAM,
                                   reason=f"team '{dup[ev.superbet_event_id]}' "
                                          "in another event < 3 h apart"))
            continue
        if prev is not None and prev.get("status") == IDENTIFIED:
            records.append({**prev, "pinned": True})
            continue
        if aborted is not None:
            records.append(_record(ev, at, status=NOT_IDENTIFIED,
                                   reason="BRIDGE_ABORTED"))
            continue
        try:
            records.append(identify_event(ev, client, cache, teams, at))
        except BridgeAbortedError as exc:
            aborted = str(exc)
            records.append(_record(ev, at, status=NOT_IDENTIFIED,
                                   reason="BRIDGE_ABORTED", error=aborted))
    by_id: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for r in records:
        if r["status"] == IDENTIFIED:
            by_id[(r["sport"], int(r["sofascore_event_id"]))].append(r)
    for (_, sid), group in by_id.items():
        if len(group) > 1:
            for r in group:
                r["status"] = DUPLICATE_SOFASCORE_ID
                r["reason"] = "one Sofascore event for " + ", ".join(
                    g["superbet_event_id"] for g in group)
                r["duplicate_of"] = sid
    counts: dict[str, Any] = {}
    for sport in SPORT_KEYS:
        mine = [r for r in records if r["sport"] == sport]
        refused: dict[str, int] = defaultdict(int)
        for r in mine:
            if r["status"] != IDENTIFIED:
                refused[str(r.get("reason") or r["status"])
                        if r["status"] == NOT_IDENTIFIED else r["status"]] += 1
        counts[sport] = {"events": len(mine),
                         "identified": sum(r["status"] == IDENTIFIED for r in mine),
                         "refused": dict(sorted(refused.items()))}
    return records, {"sports": counts, "aborted": aborted}


def load_fixtures(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    doc: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return doc


def fixtures_by_event(doc: Mapping[str, Any] | None
                      ) -> dict[tuple[str, str], dict[str, Any]]:
    """(sport, superbet_event_id) -> its record."""
    return {(str(r["sport"]), str(r["superbet_event_id"])): dict(r)
            for r in ((doc or {}).get("fixtures") or [])}
