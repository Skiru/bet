"""What a national football side and a tennis Finals player play for - a
display-only stakes flag (epochs.STAKES_GROUPS_FROM_UTC, operator 2026-11-18).

Never a gate, never a confidence, never in `confidence.read_value`, no
ledger group: the flags join `bet.sofa.stakes`' list on the leg (`stakes`)
and are shown on the PDF / HTML / md and in the analysts' dossier.

**National football** (pre-registration
docs/sofa/evidence/stakes_prereg_football_2026-11-18.md, D1: national teams
get the flag only, no correction, no exam). Each side's state as of the
kickoff - MUST_WIN (NEED_POINT pooled in, D4), ALIVE, SECURED, DEAD; an
AMBIGUOUS side gets no flag - by `bet.sofa.stakes_state` (the frozen
module) on the group's table rebuilt from the results the cache already
holds (the sides' cached `last` / `next` listings, walked through the group's
opponents; no request). The competitions and their boundaries are section
4.2's (`NATIONAL`, `national_bounds`, as `inventory.py` codes them); the
group is (uniqueTournament, season, tournament), league / group rounds only,
every pair met the same m <= 4 times (the missing meetings, at most 25 %,
inferred as still to play), at least three teams, men only. Head-to-head
first only for the Nations League and the EURO qualifiers.

One guard the inventory did not need (it read the past): a group game that
started before this kickoff and is not finished in the cache means the
cache has not seen its result yet - the table would be wrong, so no flag
(`STALE`), never a guess.

**Tennis** (docs/sofa/evidence/stakes_prereg_cs2_tennis_2026-11-18.md,
section 5): only `RR_DECIDED_SIDE` - a singles Finals group (ATP / WTA /
Next Gen Finals: `tournament.isGroup`, "Finals" in the stage name, no
"Doubles"), the side with exactly two finished group matches before the
kickoff at 2-0 or 0-2. Left out as not derivable reliably at build time:
`TIE_DEAD_RUBBER` / `TIE_CLINCHER` (a tie has no id - countries and a 6-day
window are an unmeasured approximation - its number of rubbers is not in the
data, and the same day's earlier rubbers are not settled in the cache when
the coupon is built), and every CS2 flag (`cs2_series` and the esports
listing hold only finished series, fetched the next morning: no same-day
Swiss / GSL record, no published bracket, no `roundInfo`).
"""

from __future__ import annotations

import itertools
import json
import sqlite3
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from bet.sofa.stakes_state import H2H, final_state

NATIONAL_PREFIX = "STAKES_NATIONAL_"
MUST_WIN = "STAKES_NATIONAL_MUST_WIN"
ALIVE = "STAKES_NATIONAL_ALIVE"
SECURED = "STAKES_NATIONAL_SECURED"
DEAD = "STAKES_NATIONAL_DEAD"
RR_DECIDED_SIDE = "RR_DECIDED_SIDE"
TB_MARK = "tb"

# uniqueTournament id -> (boundary rule, head-to-head first?) - section 4.2
# of the pre-registration, as inventory.py codes it (frozen).
NATIONAL: dict[int, tuple[str, bool]] = {
    10783: ("unl", True),          # UEFA Nations League
    27: ("top12", True),           # EURO qualification
    11: ("top12", False),          # World Cup qualification, UEFA
    13: ("top12", False),          # World Cup qualification, CAF
    1848: ("top2", False),         # Africa Cup of Nations qualification
    14100: ("first_last", False),  # CONCACAF Nations League
    295: ("conmebol", False),      # World Cup qualification, CONMEBOL
}
MAX_LEGS_PER_PAIR = 4
MAX_INFERRED_SHARE = 0.25
MIN_GROUP_TEAMS = 3
GROUP_MAX_TEAMS = 14  # listings walked to rebuild one group (CONMEBOL: 10)
LISTING_DAYS = 800    # how far back a side's listings are read
UNFITTED_CONSTANTS = ("GROUP_MAX_TEAMS", "LISTING_DAYS")

# The sentence each flag carries (Polish, the operator's page).
TEXT = {
    MUST_WIN: "gra o cel w grupie - bez wygranej (lub punktu) cel przepada",
    ALIVE: "cel w grupie otwarty, ten mecz go nie rozstrzyga",
    SECURED: "cel w grupie już zapewniony",
    DEAD: "w grupie nie ma już o co grać",
    RR_DECIDED_SIDE: "bilans w grupie przed ostatnim meczem",
}
TB_TEXT = " (zależnie od kryteriów przy równej liczbie punktów)"
STATE_FLAG = {"MUST_WIN": MUST_WIN, "ALIVE": ALIVE, "SECURED": SECURED,
              "DEAD": DEAD}


def national_bounds(rule: str, n: int, stage_name: str) -> list[int]:
    """Section 4.2's boundaries ("finish in the top k") of a group of n."""
    if rule == "unl":
        return [1] if "League D" in stage_name else list(range(1, n))
    if rule == "top12":
        return [1, 2]
    if rule == "top2":
        return [2]
    if rule == "first_last":
        return sorted({1, n - 1})
    if rule == "conmebol":
        return [6, 7]
    raise ValueError(rule)


@dataclass(frozen=True)
class Game:
    """One listed game of a group, from its Sofascore payload."""

    event_id: int
    ts: int
    home: int
    away: int
    status: str
    hg: int | None
    ag: int | None
    winner: int | None
    home_name: str
    away_name: str


def _ids(event: Mapping[str, Any]) -> tuple[int | None, int | None, int | None]:
    tour = event.get("tournament") or {}
    ut = (tour.get("uniqueTournament") or {}).get("id")
    season = (event.get("season") or {}).get("id")
    tid = tour.get("id")
    return (ut if isinstance(ut, int) else None,
            season if isinstance(season, int) else None,
            tid if isinstance(tid, int) else None)


def _score(node: Any) -> int | None:
    if not isinstance(node, Mapping):
        return None
    for key in ("normaltime", "current"):
        v = node.get(key)
        if isinstance(v, int):
            return v
    return None


def game_of(event: Mapping[str, Any]) -> Game | None:
    """The payload as a Game, None without ids or a start."""
    home = (event.get("homeTeam") or {})
    away = (event.get("awayTeam") or {})
    eid, ts = event.get("id"), event.get("startTimestamp")
    hid, aid = home.get("id"), away.get("id")
    if not (isinstance(eid, int) and isinstance(ts, int)
            and isinstance(hid, int) and isinstance(aid, int)):
        return None
    winner = event.get("winnerCode")
    return Game(eid, ts, hid, aid,
                str((event.get("status") or {}).get("type") or ""),
                _score(event.get("homeScore")), _score(event.get("awayScore")),
                winner if isinstance(winner, int) else None,
                str(home.get("name") or ""), str(away.get("name") or ""))


def _league_round(event: Mapping[str, Any]) -> bool:
    info = event.get("roundInfo") or {}
    return not info.get("name") and info.get("cupRoundType") is None


def national_states(
    fixture: Mapping[str, Any], events: Iterable[Mapping[str, Any]],
) -> dict[int, tuple[str, bool]] | str:
    """{side id: (state, tiebreak-dependent)} of a national group fixture
    as of its kickoff, or why not (a short reason). `fixture` is the match's
    own Sofascore payload, `events` every cached payload of its group (more
    is fine: other stages are filtered out here)."""
    ut, season, tid = _ids(fixture)
    if ut not in NATIONAL or season is None or tid is None:
        return "NOT_IN_SCOPE"
    if not _league_round(fixture):
        return "NOT_GROUP_ROUND"
    if (fixture.get("homeTeam") or {}).get("gender") == "F":
        return "NOT_IN_SCOPE"
    me = game_of(fixture)
    if me is None:
        return "NO_IDS"
    group: dict[int, Game] = {}
    for e in events:
        if _ids(e) != (ut, season, tid) or not _league_round(e):
            continue
        g = game_of(e)
        if g is None or g.status not in ("finished", "notstarted"):
            continue
        if g.status == "finished" and (g.hg is None or g.ag is None):
            continue
        old = group.get(g.event_id)
        # a finished state is never reverted: keep it over a stale copy
        if old is None or (g.status == "finished" and old.status != "finished"):
            group[g.event_id] = g
    group[me.event_id] = me
    games = list(group.values())
    teams = sorted({g.home for g in games} | {g.away for g in games})
    n = len(teams)
    if n < MIN_GROUP_TEAMS:
        return "SMALL_GROUP"
    pc = Counter(frozenset((g.home, g.away)) for g in games)
    m = max(pc.values())
    pairs = [frozenset(p) for p in itertools.combinations(teams, 2)]
    missing = sum(m - pc[p] for p in pairs)
    if m > MAX_LEGS_PER_PAIR or missing > MAX_INFERRED_SHARE * m * len(pairs):
        return "INCOMPLETE_GROUP"
    kickoff = me.ts
    if any(g.event_id != me.event_id and g.status != "finished" and g.ts < kickoff
           for g in games):
        return "STALE"
    before = [g for g in games if g.status == "finished" and g.ts < kickoff]
    pts = {t: 0 for t in teams}
    for g in before:
        assert g.hg is not None and g.ag is not None
        pts[g.home] += 3 if g.hg > g.ag else 1 if g.hg == g.ag else 0
        pts[g.away] += 3 if g.ag > g.hg else 1 if g.hg == g.ag else 0
    others = [(g.home, g.away) for g in games
              if g.event_id != me.event_id
              and not (g.status == "finished" and g.ts < kickoff)]
    for p in pairs:
        x, y = sorted(p)
        others += [(x, y)] * (m - pc[p])
    rule, h2h_first = NATIONAL[ut]
    stage = str((fixture.get("tournament") or {}).get("name") or "")
    bounds = national_bounds(rule, n, stage)
    h2h = H2H([(g.home, g.away, int(g.hg or 0), int(g.ag or 0)) for g in before],
              m) if h2h_first else None
    match = (me.home, me.away)
    return {side: final_state(pts, others, match, side, bounds, h2h)
            for side in match}


def national_flags(fixture: Mapping[str, Any],
                   events: Iterable[Mapping[str, Any]]) -> list[str]:
    """STAKES_NATIONAL_* flags of both sides (home first); AMBIGUOUS or a
    group that cannot be rebuilt = no flag."""
    states = national_states(fixture, events)
    if isinstance(states, str):
        return []
    me = game_of(fixture)
    assert me is not None
    names = {me.home: me.home_name, me.away: me.away_name}
    out: list[str] = []
    for side in (me.home, me.away):
        state, tb = states[side]
        flag = STATE_FLAG.get(state)
        if flag is None:
            continue
        detail = names[side] + (f"; {TB_MARK}" if tb else "")
        out.append(f"{flag}({detail})")
    return out


def _rr_scope(fixture: Mapping[str, Any]) -> bool:
    tour = fixture.get("tournament") or {}
    name = str(tour.get("name") or "")
    return bool(tour.get("isGroup")) and "Finals" in name and "Doubles" not in name


def rr_flags(fixture: Mapping[str, Any],
             events_of: Callable[[int], Iterable[Mapping[str, Any]]]) -> list[str]:
    """RR_DECIDED_SIDE of a singles Finals group match: a side with exactly
    two finished group matches before the kickoff at 2-0 or 0-2. A group
    game of the side that started before and is not finished or cancelled
    in the cache = no flag for that side."""
    if not _rr_scope(fixture):
        return []
    me = game_of(fixture)
    _, season, tid = _ids(fixture)
    if me is None or season is None or tid is None:
        return []
    out: list[str] = []
    for side, name in ((me.home, me.home_name), (me.away, me.away_name)):
        games: dict[int, Game] = {}
        for e in events_of(side):
            if _ids(e)[1:] != (season, tid):
                continue
            g = game_of(e)
            if g is None or g.event_id == me.event_id or g.ts >= me.ts:
                continue
            old = games.get(g.event_id)
            if old is None or (g.status == "finished" and old.status != "finished"):
                games[g.event_id] = g
        if any(g.status not in ("finished", "canceled") for g in games.values()):
            continue
        played = [g for g in games.values() if g.status == "finished"]
        if len(played) != 2 or any(g.winner not in (1, 2) for g in played):
            continue
        wins = sum(1 for g in played
                   if (g.winner == 1) == (g.home == side))
        if wins in (0, 2):
            out.append(f"{RR_DECIDED_SIDE}({name} {wins}-{2 - wins})")
    return out


def flag_text(flag: str) -> str | None:
    """The Polish sentence of one of this module's flags, None for another."""
    key, _, rest = str(flag).partition("(")
    if key not in TEXT:
        return None
    detail = rest.rstrip(")")
    tb = detail.endswith(f"; {TB_MARK}")
    if tb:
        detail = detail[: -len(f"; {TB_MARK}")]
    if key == RR_DECIDED_SIDE:
        name, _, record = detail.rpartition(" ")
        return f"{name}: {TEXT[key]} {record}"
    return f"{detail}: {TEXT[key]}" + (TB_TEXT if tb else "")


# --- the cache ------------------------------------------------------------


def _payload(raw: Any) -> dict[str, Any] | None:
    try:
        event = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if isinstance(event, dict) and isinstance(event.get("event"), dict):
        event = event["event"]
    return event if isinstance(event, dict) else None


def fixture_payload(con: sqlite3.Connection, event_id: int) -> dict[str, Any] | None:
    """The match's own payload: the cached /event, else its listed copy."""
    for sql in (
            "SELECT detail_json FROM sofa_event_detail WHERE sofascore_event_id = ?",
            "SELECT event_json FROM sofa_listed_event WHERE event_id = ?"):
        try:
            row = con.execute(sql, (event_id,)).fetchone()
        except sqlite3.OperationalError:
            continue
        if row and (event := _payload(row[0])) is not None:
            return event
    return None


def entity_events(con: sqlite3.Connection, entity_id: int,
                  since_ts: int) -> list[dict[str, Any]]:
    """Every cached `last` / `next` listing payload of one side from
    `since_ts`: the listing index first, then the raw pages."""
    out: list[dict[str, Any]] = []
    try:
        rows = con.execute(
            "SELECT e.event_json FROM sofa_listing_event m "
            "JOIN sofa_listed_event e ON e.event_id = m.event_id "
            "WHERE m.entity_id = ? AND m.start_ts >= ?",
            (entity_id, since_ts)).fetchall()
    except sqlite3.OperationalError:
        rows = []
    for (raw,) in rows:
        if (event := _payload(raw)) is not None:
            out.append(event)
    try:
        pages = con.execute(
            "SELECT events_json FROM sofa_entity_events "
            "WHERE sofascore_entity_id = ?", (entity_id,)).fetchall()
    except sqlite3.OperationalError:
        pages = []
    for (raw,) in pages:
        try:
            events = json.loads(raw).get("events") or []
        except (TypeError, ValueError, AttributeError):
            continue
        out.extend(e for e in events if isinstance(e, dict)
                   and isinstance(e.get("startTimestamp"), int)
                   and e["startTimestamp"] >= since_ts)
    return out


def group_events(con: sqlite3.Connection, fixture: Mapping[str, Any],
                 since_ts: int) -> list[dict[str, Any]]:
    """The cached games of the fixture's group, walked from its two sides'
    listings through the group's other teams (at most GROUP_MAX_TEAMS)."""
    key = _ids(fixture)
    me = game_of(fixture)
    if me is None:
        return []
    queue, seen = [me.home, me.away], {me.home, me.away}
    found: list[dict[str, Any]] = []
    walked = 0
    while queue and walked < GROUP_MAX_TEAMS:
        team = queue.pop(0)
        walked += 1
        for e in entity_events(con, team, since_ts):
            if _ids(e) != key:
                continue
            found.append(e)
            for side in ("homeTeam", "awayTeam"):
                tid = (e.get(side) or {}).get("id")
                if isinstance(tid, int) and tid not in seen:
                    seen.add(tid)
                    queue.append(tid)
    return found


def _kickoff_ts(row: Mapping[str, Any]) -> int | None:
    try:
        return int(datetime.fromisoformat(
            str(row["kickoff_utc"]).replace("Z", "+00:00")).timestamp())
    except (KeyError, TypeError, ValueError):
        return None


def for_day(con: sqlite3.Connection,
            fixtures: Sequence[Mapping[str, Any]]) -> dict[int, list[str]]:
    """sofascore_event_id -> this module's flags for the day's football /
    tennis fixtures (02_fixtures.json rows) that have any. Read-only."""
    out: dict[int, list[str]] = {}
    for f in fixtures:
        sport = f.get("sport")
        eid = f.get("sofascore_event_id")
        ts = _kickoff_ts(f)
        if not isinstance(eid, int) or ts is None:
            continue
        if sport == "football" and f.get("competition_id") in NATIONAL:
            fixture = fixture_payload(con, eid)
            if fixture is None:
                continue
            got = national_flags(
                fixture, group_events(con, fixture, ts - LISTING_DAYS * 86400))
        elif sport == "tennis":
            fixture = fixture_payload(con, eid)
            if fixture is None or not _rr_scope(fixture):
                continue
            since = ts - 60 * 86400
            got = rr_flags(fixture, lambda side: entity_events(con, side, since))
        else:
            continue
        if got:
            out[eid] = got
    return out


def from_db(db_path: Any,
            fixtures: Sequence[Mapping[str, Any]]) -> dict[int, list[str]] | str:
    """for_day on the database opened read-only, or the error as a string
    (the coupon is then built without these flags, never refused)."""
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        return f"{type(exc).__name__}: {exc}"
    try:
        return for_day(con, fixtures)
    except (sqlite3.Error, ValueError, TypeError, KeyError) as exc:
        return f"{type(exc).__name__}: {exc}"
    finally:
        con.close()


def merge(a: Mapping[int, Sequence[str]],
          b: Mapping[int, Sequence[str]]) -> dict[int, list[str]]:
    """Two event -> flags maps as one (a's flags first)."""
    out = {k: list(v) for k, v in a.items()}
    for k, v in b.items():
        out.setdefault(k, []).extend(x for x in v if x not in out[k])
    return out
