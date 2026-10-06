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
   Academy in two series at 10:30Z). CS2 only when the two events are the
   same PAIR of teams (a 1x1 loop, a rematch no start can tell apart): a CS2
   team plays two series a day against two opponents, and pick_event names
   both sides of each (F1.2: on 09-28..10-04 the team-only rule refused 79
   series the settle had found on Sofascore). Hockey / basketball /
   volleyball keep the team rule: one club cannot play twice in 3 h.
2. The teams' Sofascore ids offline: hockey / basketball / volleyball as
   player_model.resolve_team (RESOLVE's verified entity, else an exact
   normalised name naming one team in the listed games of the last
   IDENTITY_NAME_WINDOW_S - 120 days left every NBA team unresolved in the
   off-season on 10-05); CS2 an exact folded name naming one team in
   cs2_series, else the same with the esports affixes dropped ("BetBoom" -
   "BetBoom Team"). A side with no exact id may still give the team to ASK
   (TeamResolver.query_id, never an id match): the one team of the index
   whose marker-free name scores above NAME_MATCH_THRESHOLD at the same
   gender and a compatible squad level.
3. One listing request, `team/<id>/events/next/0`, for team1 (team2 when
   team1 has no id; a query-only team after both), cached with the events TTL
   (SofaCache). A refusal (403, any provider error, an open breaker) aborts
   the run: no retry, every event not yet tried is NOT_IDENTIFIED
   (BRIDGE_ABORTED).
4. In the response, the one event that is this game: the sport's category,
   Sofascore's start within MAX_START_GAP of Superbet's, the gender of the
   board, not postponed or cancelled (fixture_status.NOT_AS_SCHEDULED: on
   10-05 Partizan - Mega and Bedzin - Bielsko were each listed twice, once
   postponed), and BOTH sides named: a side's Sofascore id equal to the id
   resolved for it (a different resolved id refuses the side whatever the
   name), or, with no id to compare, its marker-free name (resolve.part_score
   over normalize_name, which carries the aliases) above NAME_MATCH_THRESHOLD
   at a compatible squad level; or one side by its id and the other, with no
   id of its own, confirmed by resolve.shadow_opponent_agrees - the settle's
   own opponent rule (LISTING_ID_AND_OPPONENT). CS2 through cs2.pick_event
   (both names above the threshold with cs2.esports_score) and the same start
   rule. Two fitting events, or one that reads both ways round, is AMBIGUOUS.
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
from bet.sofa.fixture_status import NOT_AS_SCHEDULED
from bet.sofa.names import levels_compatible, normalize_name
from bet.sofa.player_model import resolve_team, team_name_index
from bet.sofa.resolve import (
    NAME_MATCH_THRESHOLD,
    part_score,
    shadow_opponent_agrees,
    sofascore_gender,
    superbet_gender,
)
from bet.sofa.shadow import SPORTS

FIXTURES_FILE = "sport_fixtures.json"
SPORT_KEYS = ("hockey", "basketball", "volleyball", "cs2")
MAX_START_GAP = timedelta(hours=1)
DUPLICATE_WINDOW = timedelta(hours=3)
# The listed games the offline resolver reads team names from: longer than
# player_model's 120 days, so an off-season (NBA: April - October) does not
# empty the index. A name must still name one team only.
IDENTITY_NAME_WINDOW_S = 400 * 86400

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


def _newest(ev: Any) -> datetime:
    return max((_utc(t) for t in ev.fetched_at.values()),
               default=datetime.min.replace(tzinfo=UTC))


def snapshot_events(runs_dir: str, sport: str, date: str,
                    at: datetime | None = None) -> dict[str, Any]:
    """Each Superbet event of D's and D+1's snapshot files as its last
    pre-start record quoted it, tagged with the file (`source_date`), as
    sport_day.day_events reads them - but only records fetched at or
    before `at`: a replay under SOFA_NOW must not read a price taken after
    its own clock. An event in both files keeps the newer record."""
    from bet.sofa import sport_day

    out: dict[str, Any] = {}
    nxt = (datetime.strptime(date, "%Y-%m-%d") + timedelta(days=1)).strftime(
        "%Y-%m-%d")
    for source in (date, nxt):
        path = sport_day.day_dir(runs_dir, sport, source) / cs2.SNAPSHOTS_FILE  # type: ignore[arg-type]
        snaps = sport_day.load_snapshots(path)
        if at is not None:
            snaps = [s for s in snaps if _utc(str(s["fetched_at_utc"])) <= at]
        for eid, ev in sport_day.latest_events(sport, snaps).items():  # type: ignore[arg-type]
            ev.source_date = source
            have = out.get(eid)
            if have is None or _newest(ev) > _newest(have):
                out[eid] = ev
    return out


def board_events(runs_dir: str, sport: str, date: str,
                 at: datetime | None = None) -> list[BoardEvent]:
    """The sport's Superbet events of D's and D+1's snapshot files."""
    events = snapshot_events(runs_dir, sport, date, at)
    return [BoardEvent(sport, str(ev.superbet_event_id), ev.match_name, ev.team1,
                       ev.team2, ev.kickoff_utc, ev.tournament,
                       getattr(ev, "source_date", None))
            for ev in events.values()]


def fold_team(sport: str, name: str) -> str:
    return cs2.esports_name(name) if sport == "cs2" else normalize_name(name)


def _pair(ev: BoardEvent) -> frozenset[str]:
    return frozenset({fold_team(ev.sport, ev.team1), fold_team(ev.sport, ev.team2)})


def duplicate_team_events(events: Iterable[BoardEvent]) -> dict[str, str]:
    """C5: Superbet event id -> the team name it shares with another event
    of the same sport starting under DUPLICATE_WINDOW apart; in CS2 only an
    event of the same pair of teams counts."""
    by_name: dict[tuple[str, str], list[BoardEvent]] = defaultdict(list)
    for ev in events:
        for name in (ev.team1, ev.team2):
            key = fold_team(ev.sport, name)
            if key:
                by_name[(ev.sport, key)].append(ev)
    out: dict[str, str] = {}
    for (sport, key), evs in by_name.items():
        for a in evs:
            for b in evs:
                if (a.superbet_event_id != b.superbet_event_id
                        and abs(a.kickoff - b.kickoff) < DUPLICATE_WINDOW
                        and (sport != "cs2" or _pair(a) == _pair(b))):
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


def cs2_core(name: str) -> str:
    """A folded CS2 name without the esports affixes ("BetBoom Team" ->
    "betboom"); roster and women's markers stay, so "Aurora Young Blood"
    is never "Aurora"."""
    folded = cs2.esports_name(name)
    words = [w for w in folded.split() if w not in cs2.ESPORTS_AFFIXES]
    return " ".join(words) if words else folded


def cs2_core_index(index: Mapping[str, set[int]]) -> dict[str, set[int]]:
    """cs2_core(name) -> Sofascore team ids, from cs2_team_index's keys."""
    out: dict[str, set[int]] = defaultdict(set)
    for key, ids in index.items():
        out[cs2_core(key)] |= ids
    return dict(out)


@dataclass
class TeamResolver:
    """Superbet team name -> Sofascore team id, offline, never fuzzy."""

    conn: sqlite3.Connection
    now_ts: int
    _indexes: dict[str, dict[str, set[int]]] = field(default_factory=dict)

    def _index(self, slug: str) -> dict[str, set[int]]:
        if slug not in self._indexes:
            self._indexes[slug] = team_name_index(
                self.conn, slug, self.now_ts, window_s=IDENTITY_NAME_WINDOW_S)
        return self._indexes[slug]

    def team_id(self, sport: str, name: str) -> int | None:
        if sport == "cs2":
            if "cs2" not in self._indexes:
                self._indexes["cs2"] = cs2_team_index(self.conn)
                self._indexes["cs2_core"] = cs2_core_index(self._indexes["cs2"])
            ids = self._indexes["cs2"].get(cs2.esports_name(name)) or set()
            if not ids:
                ids = self._indexes["cs2_core"].get(cs2_core(name)) or set()
            return next(iter(ids)) if len(ids) == 1 else None
        slug = SPORTS[sport].sofascore_slug  # type: ignore[index]
        try:
            tid = resolve_team(self.conn, slug, name, {})
            if tid is not None:
                return tid
            return resolve_team(self.conn, slug, name, self._index(slug))
        except sqlite3.Error:
            return None

    def query_id(self, sport: str, name: str) -> int | None:
        """The team to ASK about when `name` has no exact id: the one team of
        the index whose marker-free name scores above NAME_MATCH_THRESHOLD at
        the same gender and a compatible squad level. Never an identity - the
        listing it returns must still name both sides (match_shadow gets no
        id for that side)."""
        if sport == "cs2":
            return None
        slug = SPORTS[sport].sofascore_slug  # type: ignore[index]
        try:
            index = self._index(slug)
        except sqlite3.Error:
            return None
        norm = normalize_name(name)
        women = norm.endswith("(w)")
        ids: set[int] = set()
        for key, key_ids in index.items():
            if key.endswith("(w)") != women or not same_squad(norm, key):
                continue
            if part_score(norm, key) > NAME_MATCH_THRESHOLD:
                ids |= key_ids
                if len(ids) > 1:
                    return None
        return next(iter(ids)) if len(ids) == 1 else None


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


# Words that make another squad of the same club, which levels_compatible
# does not read (it knows "(r)", "II", "B" and the age groups): "Kataja
# Talents" is Kataja Basket's 1. Division B side, and the shared "kataja" let
# the opponent rule read it as Kataja Basket (09-29, F1.2). A name with one and
# a name without it are two teams. cs2.ROSTER_MARKERS plus club-sport words.
SQUAD_WORDS = cs2.ROSTER_MARKERS | frozenset(
    {"talents", "akademia", "akademie", "academia", "jugend", "juvenil"})


def _squad_words(norm: str) -> frozenset[str]:
    return frozenset(w for w in norm.replace("/", " ").split() if w in SQUAD_WORDS)


def same_squad(a: str, b: str) -> bool:
    """Two normalised names could be the same squad: levels_compatible and
    the same SQUAD_WORDS on both."""
    return levels_compatible(a, b) and _squad_words(a) == _squad_words(b)


def _side_ok(board_name: str, board_id: int | None, ev_id: int | None,
             ev_name: str) -> tuple[bool, float]:
    """This side names this team: its Sofascore id is the one resolved for
    it (a different resolved id refuses it, whatever the name scores), or -
    with no id to compare - its marker-free name scores above the threshold
    at a compatible squad level. The women's / reserve markers are read by
    the gender gate and levels_compatible, not by the score: "Helios VS (K)"
    scored 81.8 against "Helios VS Basket" on the marker alone."""
    a, b = normalize_name(board_name), normalize_name(ev_name)
    score = part_score(a, b)
    if board_id is not None and ev_id is not None:
        return ev_id == board_id, round(score, 1)
    return score > NAME_MATCH_THRESHOLD and same_squad(a, b), round(score, 1)


def _anchored(board_id: int | None, ev_id: int | None, board_name: str,
              ev_name: str, other_board: str, other_board_id: int | None,
              other_ev_id: int | None, other_ev: str, gap_s: float) -> bool:
    """One side by its resolved id, the other - which has no resolved id to
    compare - confirmed by the settle's opponent rule
    (resolve.shadow_opponent_agrees: the full marker-free score, or one shared
    distinctive word when the two clocks agree within 15 minutes) at a
    compatible squad level."""
    if board_id is None or ev_id != board_id:
        return False
    if other_board_id is not None and other_ev_id is not None:
        return False
    a, b = normalize_name(other_board), normalize_name(other_ev)
    return same_squad(a, b) and shadow_opponent_agrees(
        a, b, gap_s, searched=normalize_name(board_name),
        searched_side=normalize_name(ev_name))


def match_shadow(ev: BoardEvent, candidates: Iterable[dict[str, Any]],
                 t1_id: int | None, t2_id: int | None) -> dict[str, Any]:
    """The one listed event that is this Superbet game, or why not."""
    slug = SPORTS[ev.sport].sofascore_slug  # type: ignore[index]
    gender = "W" if "W" in {superbet_gender(ev.team1), superbet_gender(ev.team2)} \
        else "M"
    fits: list[dict[str, Any]] = []
    near = 0
    off_schedule = 0
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
        if str((e.get("status") or {}).get("type") or "") in NOT_AS_SCHEDULED:
            off_schedule += 1
            continue
        gap_s = abs((start - ev.kickoff).total_seconds())
        (hid, hname), (aid, aname) = _side(e, "homeTeam"), _side(e, "awayTeam")
        s_h1, sc_h1 = _side_ok(ev.team1, t1_id, hid, hname)
        s_a2, sc_a2 = _side_ok(ev.team2, t2_id, aid, aname)
        c_a1, sc_a1 = _side_ok(ev.team1, t1_id, aid, aname)
        c_h2, sc_h2 = _side_ok(ev.team2, t2_id, hid, hname)
        straight, crossed = s_h1 and s_a2, c_a1 and c_h2
        method: str | None = None
        if not (straight or crossed):
            straight = (
                _anchored(t1_id, hid, ev.team1, hname, ev.team2, t2_id, aid,
                          aname, gap_s)
                or _anchored(t2_id, aid, ev.team2, aname, ev.team1, t1_id, hid,
                             hname, gap_s))
            crossed = (
                _anchored(t1_id, aid, ev.team1, aname, ev.team2, t2_id, hid,
                          hname, gap_s)
                or _anchored(t2_id, hid, ev.team2, hname, ev.team1, t1_id, aid,
                             aname, gap_s))
            method = "LISTING_ID_AND_OPPONENT"
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
            "match_method": method or (
                "LISTING_ID_AND_NAME" if by_id else "LISTING_NAMES"),
        })
    if len(fits) > 1:
        return {"status": NOT_IDENTIFIED, "reason": "AMBIGUOUS"}
    if not fits:
        if off_schedule and off_schedule == near:
            return {"status": NOT_IDENTIFIED, "reason": "NOT_AS_SCHEDULED"}
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
                   teams: Callable[[str, str], int | None], at: datetime,
                   query_teams: Callable[[str, str], int | None] | None = None
                   ) -> dict[str, Any]:
    """`query_teams` (TeamResolver.query_id): the team to ask about when
    neither side has an exact id; its id is never an id match."""
    t1_id, t2_id = teams(ev.sport, ev.team1), teams(ev.sport, ev.team2)
    query = t1_id if t1_id is not None else t2_id
    query_only = False
    if query is None and query_teams is not None:
        query = query_teams(ev.sport, ev.team1)
        if query is None:
            query = query_teams(ev.sport, ev.team2)
        query_only = query is not None
    if query is None:
        return _record(ev, at, status=NOT_IDENTIFIED, reason="TEAM_UNRESOLVED")
    listing, cached = next_listing(client, cache, query)
    found = (match_cs2(ev, listing) if ev.sport == "cs2"
             else match_shadow(ev, listing, t1_id, t2_id))
    extra = {"queried_team_id": query, "listing_from_cache": cached,
             "team1_id": t1_id, "team2_id": t2_id}
    if query_only:
        extra["query_only"] = True
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
             pinned: Mapping[str, dict[str, Any]] | None = None,
             query_teams: Callable[[str, str], int | None] | None = None
             ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Every event of the day's window identified or refused, and the
    per-sport counts. `pinned`: records of an earlier run that were
    IDENTIFIED - kept as they are, never asked again. `query_teams`: see
    identify_event."""
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
            records.append(identify_event(ev, client, cache, teams, at,
                                          query_teams))
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
