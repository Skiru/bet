"""Schedule / fatigue features of a football side or a tennis player, as of a
kick-off - the one function the history replay and SHEET read (pre-registration
``docs/sofa/evidence/schedule_context_prereg_2026-11-09.md`` section 4; review
``r3_final_review.md`` D7).

Pure: the calendar is built from event payloads (``sofa_listed_event`` rows -
the union over every listing, never one side's own pages) by ``Calendar.add``;
``football_side`` / ``tennis_player`` read only matches that started strictly
before the kick-off (``cont_next4`` reads the side's next fixture, known at
the kick-off). A day's forecasts do not depend on the order its matches are
added (they read nothing at or after the kick-off).

Rules frozen by the pre-registration:
  * only ``finished`` matches are load (postponed / cancelled / interrupted
    are not), friendlies are out (``comparability.is_friendly_event`` - the
    rule ``schedule.side_schedule`` uses for the display);
  * rest is hours / 24 (``rest_d``); a side with no match in the calendar in
    the ``COVERAGE_DAYS`` before the kick-off has ``coverage=False`` (fit:
    dropped; live: x1);
  * tennis: singles only (a payload with ``subTeams`` is a doubles pair).

Display only until a switch in ``bet.sofa.epochs`` reads it; nothing here
changes what ``schedule.py`` shows.
"""

from __future__ import annotations

import bisect
import json
import sqlite3
from collections import defaultdict
from collections.abc import Collection, Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any

from bet.sofa.comparability import competition_id, is_friendly_event
from bet.sofa.metrics import played_extra_time

DAY_S = 86400
COVERAGE_DAYS = 120
# Rest buckets (days, hours / 24): R1 < 3.5, R2 3.5-5.5, R3 5.5-8.5 (reference),
# R4 8.5-20.5, R5 >= 20.5.
REST_EDGES: tuple[float, ...] = (3.5, 5.5, 8.5, 20.5)
REST_BUCKETS: tuple[str, ...] = ("R1", "R2", "R3", "R4", "R5")
REST_REFERENCE = "R3"
# A gap holding a day with this many finished senior national-team matches
# is an international break.
INTL_DAY_MATCHES = 30
CONTINENTAL_WINDOW_S = 96 * 3600
DENSE14_MATCHES = 4
ET_PREV_DAYS = 7
WINTER_MONTH_DAY = (12, 25)
# Tennis
TENNIS_LOAD_WINDOW_S = 78 * 3600
TENNIS_WEEK_S = 7 * DAY_S
TENNIS_LAYOFF_DAYS = 21
TENNIS_RET_DAYS = 14
_RETIRED = frozenset({"retired", "walkover", "defaulted"})


def rest_bucket(rest_d: float | None) -> str | None:
    if rest_d is None:
        return None
    return REST_BUCKETS[bisect.bisect_right(REST_EDGES, rest_d)]


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _status(event: Mapping[str, Any]) -> tuple[str, str]:
    status = event.get("status")
    if not isinstance(status, Mapping):
        return "", ""
    return str(status.get("type") or ""), str(status.get("description") or "").lower()


def _team(event: Mapping[str, Any], side: str) -> Mapping[str, Any]:
    team = event.get(side)
    return team if isinstance(team, Mapping) else {}


def _games(score: Any) -> int:
    if not isinstance(score, Mapping):
        return 0
    total = 0
    for i in range(1, 6):
        g = _int(score.get(f"period{i}"))
        if g is not None:
            total += g
    return total


@dataclass(frozen=True)
class CalendarMatch:
    event_id: int
    ts: int
    home_id: int
    away_id: int
    status: str  # Sofascore status type ("finished", "notstarted", ...)
    competition_id: int | None
    season_id: int | None
    tournament_id: int | None
    friendly: bool
    national: bool
    extra_time: bool
    # tennis
    home_games: int = 0
    away_games: int = 0
    winner: int | None = None  # 1 home, 2 away
    abnormal: bool = False  # retired / walkover / defaulted
    surface: str | None = None
    qualifying: bool = False

    @property
    def finished(self) -> bool:
        return self.status == "finished"


def match_from_event(event: Mapping[str, Any], sport: str) -> CalendarMatch | None:
    """One calendar entry from a listing payload; None for a payload without
    both side ids or a start, or a tennis doubles pair."""
    eid, ts = _int(event.get("id")), _int(event.get("startTimestamp"))
    home, away = _team(event, "homeTeam"), _team(event, "awayTeam")
    hid, aid = _int(home.get("id")), _int(away.get("id"))
    if eid is None or ts is None or hid is None or aid is None:
        return None
    if sport == "tennis" and (home.get("subTeams") or away.get("subTeams")):
        return None
    stype, sdesc = _status(event)
    season = event.get("season")
    tour = event.get("tournament")
    tour_m = tour if isinstance(tour, Mapping) else {}
    names = " ".join(
        str(x) for x in (tour_m.get("name"), (event.get("roundInfo") or {}).get("name")
                         if isinstance(event.get("roundInfo"), Mapping) else None) if x)
    surface: str | None = None
    if sport == "tennis":
        from bet.sofa.tennis_rating import surface_family  # local: heavy module

        surface = surface_family(event.get("groundType"))
    extra = False
    if sport == "football" and stype == "finished":
        try:
            extra = played_extra_time(dict(event))
        except (TypeError, KeyError, AttributeError):
            extra = False
    return CalendarMatch(
        event_id=eid,
        ts=ts,
        home_id=hid,
        away_id=aid,
        status=stype,
        competition_id=competition_id(event),
        season_id=_int(season.get("id")) if isinstance(season, Mapping) else None,
        tournament_id=_int(tour_m.get("id")),
        friendly=is_friendly_event(event, sport),
        national=bool(home.get("national")) or bool(away.get("national")),
        extra_time=extra,
        home_games=_games(event.get("homeScore")) if sport == "tennis" else 0,
        away_games=_games(event.get("awayScore")) if sport == "tennis" else 0,
        winner=_int(event.get("winnerCode")),
        abnormal=sdesc in _RETIRED,
        surface=surface,
        qualifying="qualif" in names.lower(),
    )


@dataclass(frozen=True)
class FootballSideFeatures:
    coverage: bool
    rest_d: float | None
    rest_bucket: str | None
    intl_return: bool
    layoff_kind: str | None  # season_start / winter / other (R5 only)
    cont_prev4: bool
    et_prev: bool
    dense14: bool
    cont_next4: bool
    matches_7d: int
    matches_14d: int

    def indicators(self) -> dict[str, int]:
        """The pre-registered 0/1 design columns (reference R3); all 0
        without coverage."""
        if not self.coverage:
            return dict.fromkeys(FOOTBALL_COLUMNS, 0)
        b = self.rest_bucket
        out = {
            "R1": int(b == "R1"),
            "R2": int(b == "R2"),
            "R4_intl": int(b == "R4" and self.intl_return),
            "R4_other": int(b == "R4" and not self.intl_return),
            "R5_season_start": int(b == "R5" and self.layoff_kind == "season_start"),
            "R5_winter": int(b == "R5" and self.layoff_kind == "winter"),
            "R5_other": int(b == "R5" and self.layoff_kind == "other"),
            "cont_prev4": int(self.cont_prev4),
            "cont_prev4_x_R1": int(self.cont_prev4 and b == "R1"),
            "et_prev": int(self.et_prev),
            "dense14": int(self.dense14),
            "cont_next4": int(self.cont_next4),
        }
        return out


FOOTBALL_COLUMNS: tuple[str, ...] = (
    "R1", "R2", "R4_intl", "R4_other", "R5_season_start", "R5_winter", "R5_other",
    "cont_prev4", "cont_prev4_x_R1", "et_prev", "dense14", "cont_next4",
)


@dataclass(frozen=True)
class TennisPlayerFeatures:
    coverage: bool
    games78: float  # games in the 78 h before / 10
    games7d_prev: float  # games in 7 d in earlier tournaments / 10
    rounds_cur: int  # matches won in the current tournament
    layoff21: bool
    ret14: bool
    surface_switch: bool
    dom_prev: float | None  # share of games won in the previous match
    qual: bool

    def columns(self) -> dict[str, float]:
        if not self.coverage:
            return dict.fromkeys(TENNIS_COLUMNS, 0.0)
        return {
            "games78": self.games78,
            "games7d_prev": self.games7d_prev,
            "rounds_cur": float(self.rounds_cur),
            "layoff21": float(self.layoff21),
            "ret14": float(self.ret14),
            "surface_switch": float(self.surface_switch),
            "dom_prev": self.dom_prev if self.dom_prev is not None else 0.5,
            "qual": float(self.qual),
        }


TENNIS_COLUMNS: tuple[str, ...] = (
    "games78", "games7d_prev", "rounds_cur", "layoff21", "ret14",
    "surface_switch", "dom_prev", "qual",
)


@dataclass
class Calendar:
    """Every side's matches by start; an event id is kept once (the newest
    ``add`` wins)."""

    sport: str
    continental: frozenset[int] = frozenset()
    _by_id: dict[int, CalendarMatch] = field(default_factory=dict)
    _sides: dict[int, list[tuple[int, int]]] | None = None
    _intl_days: frozenset[int] | None = None

    def add(self, match: CalendarMatch) -> None:
        self._by_id[match.event_id] = match
        self._sides = None
        self._intl_days = None

    def extend(self, matches: Iterable[CalendarMatch]) -> None:
        for m in matches:
            self.add(m)

    def __len__(self) -> int:
        return len(self._by_id)

    def get(self, event_id: int) -> CalendarMatch | None:
        """The calendar's entry of an event id (None: not listed)."""
        return self._by_id.get(event_id)

    def _index(self) -> dict[int, list[tuple[int, int]]]:
        if self._sides is None:
            sides: dict[int, list[tuple[int, int]]] = defaultdict(list)
            for m in self._by_id.values():
                sides[m.home_id].append((m.ts, m.event_id))
                sides[m.away_id].append((m.ts, m.event_id))
            for lst in sides.values():
                lst.sort()
            self._sides = dict(sides)
        return self._sides

    def intl_days(self) -> frozenset[int]:
        if self._intl_days is None:
            per_day: dict[int, int] = defaultdict(int)
            for m in self._by_id.values():
                if m.national and m.finished and not m.friendly:
                    per_day[m.ts // DAY_S] += 1
            self._intl_days = frozenset(
                d for d, n in per_day.items() if n >= INTL_DAY_MATCHES)
        return self._intl_days

    def history(self, side_id: int, kickoff_ts: int) -> list[CalendarMatch]:
        """The side's finished, non-friendly matches started strictly before
        the kick-off, oldest first."""
        lst = self._index().get(side_id, [])
        cut = bisect.bisect_left(lst, (kickoff_ts, -1))
        out = []
        for _, eid in lst[:cut]:
            m = self._by_id[eid]
            if m.finished and not m.friendly:
                out.append(m)
        return out

    def upcoming(self, side_id: int, kickoff_ts: int,
                 horizon_s: int) -> list[CalendarMatch]:
        """The side's non-friendly fixtures starting in (kick-off, kick-off +
        horizon], finished or not yet started (never postponed / cancelled)."""
        lst = self._index().get(side_id, [])
        lo = bisect.bisect_right(lst, (kickoff_ts, 2**62))
        out = []
        for ts, eid in lst[lo:]:
            if ts > kickoff_ts + horizon_s:
                break
            m = self._by_id[eid]
            if m.status in ("finished", "notstarted", "inprogress") and not m.friendly:
                out.append(m)
        return out

    def football_side(
        self, side_id: int, kickoff_ts: int, competition: int | None,
        season: int | None,
    ) -> FootballSideFeatures:
        past = self.history(side_id, kickoff_ts)
        last = past[-1] if past else None
        coverage = last is not None and kickoff_ts - last.ts <= COVERAGE_DAYS * DAY_S
        rest = (kickoff_ts - last.ts) / DAY_S if last is not None else None
        bucket = rest_bucket(rest)
        intl = False
        kind: str | None = None
        if last is not None and bucket in ("R4", "R5"):
            days = range(last.ts // DAY_S + 1, kickoff_ts // DAY_S)
            intl_days = self.intl_days()
            intl = any(d in intl_days for d in days)
        if last is not None and bucket == "R5":
            seen = any(m.competition_id == competition and m.season_id == season
                       for m in past)
            first_of_season = (competition is not None and season is not None
                               and not seen)
            if first_of_season:
                kind = "season_start"
            elif _spans_winter(last.ts, kickoff_ts):
                kind = "winter"
            else:
                kind = "other"
        cont_prev = any(
            m.competition_id in self.continental
            and kickoff_ts - m.ts <= CONTINENTAL_WINDOW_S
            for m in past[-3:])
        et_prev = (last is not None and last.extra_time
                   and kickoff_ts - last.ts <= ET_PREV_DAYS * DAY_S)
        m7 = sum(1 for m in past if kickoff_ts - m.ts <= 7 * DAY_S)
        m14 = sum(1 for m in past if kickoff_ts - m.ts <= 14 * DAY_S)
        nxt = self.upcoming(side_id, kickoff_ts, CONTINENTAL_WINDOW_S)
        cont_next = bool(nxt) and nxt[0].competition_id in self.continental
        return FootballSideFeatures(
            coverage=coverage,
            rest_d=rest,
            rest_bucket=bucket,
            intl_return=intl,
            layoff_kind=kind,
            cont_prev4=cont_prev,
            et_prev=bool(et_prev),
            dense14=m14 >= DENSE14_MATCHES,
            cont_next4=cont_next,
            matches_7d=m7,
            matches_14d=m14,
        )

    def tennis_player(self, player_id: int, kickoff_ts: int,
                      tournament: int | None, surface: str | None,
                      qualifying: bool = False) -> TennisPlayerFeatures:
        past = self.history(player_id, kickoff_ts)
        last = past[-1] if past else None
        coverage = last is not None and kickoff_ts - last.ts <= COVERAGE_DAYS * DAY_S
        g78 = g7 = 0
        rounds = 0
        for m in past:
            age = kickoff_ts - m.ts
            games = m.home_games + m.away_games
            if age <= TENNIS_LOAD_WINDOW_S:
                g78 += games
            other_tour = tournament is None or m.tournament_id != tournament
            if age <= TENNIS_WEEK_S and other_tour:
                g7 += games
            if (tournament is not None and m.tournament_id == tournament
                    and age <= 3 * TENNIS_WEEK_S and _won(m, player_id)):
                rounds += 1
        ret = False
        for m in reversed(past):
            if kickoff_ts - m.ts > TENNIS_RET_DAYS * DAY_S:
                break
            if not m.abnormal:
                break  # a completed match since
            if not _won(m, player_id):
                ret = True
                break
        dom: float | None = None
        if last is not None:
            own = last.home_games if last.home_id == player_id else last.away_games
            tot = last.home_games + last.away_games
            dom = own / tot if tot else None
        return TennisPlayerFeatures(
            coverage=coverage,
            games78=g78 / 10.0,
            games7d_prev=g7 / 10.0,
            rounds_cur=rounds,
            layoff21=last is None or kickoff_ts - last.ts > TENNIS_LAYOFF_DAYS * DAY_S,
            ret14=ret,
            surface_switch=(last is not None and surface is not None
                            and last.surface is not None and last.surface != surface),
            dom_prev=dom,
            qual=qualifying,
        )


def _won(m: CalendarMatch, player_id: int) -> bool:
    return (m.winner == 1 and m.home_id == player_id) or (
        m.winner == 2 and m.away_id == player_id)


def _spans_winter(last_ts: int, kickoff_ts: int) -> bool:
    import datetime as _dt

    a = _dt.datetime.fromtimestamp(last_ts, _dt.UTC).date()
    b = _dt.datetime.fromtimestamp(kickoff_ts, _dt.UTC).date()
    month, day = WINTER_MONTH_DAY
    for year in range(a.year, b.year + 1):
        mark = _dt.date(year, month, day)
        if a <= mark <= b:
            return True
    return False


def iter_listed_events(conn: sqlite3.Connection, sport: str,
                       ids: Collection[int] | None = None) -> Iterator[dict[str, Any]]:
    """Every ``sofa_listed_event`` payload of a sport (read-only)."""
    cur = conn.execute(
        "SELECT event_id, event_json FROM sofa_listed_event WHERE sport = ?", (sport,))
    for eid, raw in cur:
        if ids is not None and eid not in ids:
            continue
        try:
            event = json.loads(raw)
        except (TypeError, ValueError):
            continue
        if isinstance(event, dict):
            yield event


def calendar_from_events(events: Iterable[Mapping[str, Any]], sport: str,
                         continental: Collection[int] = ()) -> Calendar:
    cal = Calendar(sport=sport, continental=frozenset(continental))
    for event in events:
        m = match_from_event(event, sport)
        if m is not None:
            cal.add(m)
    return cal
