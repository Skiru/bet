"""SHEET's football schedule / fatigue term on the PURE rating goals centres
(epochs.SCHEDULE_TERM; path (ii) of the pre-registration
``docs/sofa/evidence/schedule_context_prereg_2026-11-09.md`` section 5, the
one group that passed its exam: ``football_result``,
``docs/sofa/evidence/kontekst_terminarza_2026-11-08/exam_result.json``).

The term: a side's rating goals centre ``FootballForecast.centre("goals_for",
side)`` times exp(t_side), with

    t_side = sum_c coef[own_c] * own.indicators()[c]
           + sum_c coef[opp_c] * opp.indicators()[c]

over ``schedule_features.FOOTBALL_COLUMNS`` (a coefficient absent from the
config = 0), and t = 0 for both sides when either side has no calendar
coverage (``FootballSideFeatures.coverage``) or the fixture is a national
team's (national-team matches were out of the fit and the exam). The
coefficients are the frozen, shrunk dev fit
(``kontekst_terminarza_2026-11-08/frozen/fr_frozen.json``), installed as they
are in ``config/sofa_schedule_terms.json`` - never refitted here.

Only the path (ii) rows read it (``epochs.SCHEDULE_TERM_MARKETS``: 1X2, DNB,
double chance, the score markets, the first goal and the simulator's keys
except its four 0.60-floor keys, which keep the uncorrected p until their
floor is re-measured - pre-registration D13). ``ScheduleTermForecast`` changes
``centre("goals_for", side)`` only: ``supremacy`` (the game-state / stretch
covariate), card points and every other metric read the wrapped forecast.

Features are read exactly as the measurement read them
(``data/refit_2026-11-08_schedule/football_features.py``): a
``schedule_features.Calendar`` of the listed football events (the union of
every listing) with the continental competitions of
``config/sofa_cup_strength.json``, then ``Calendar.football_side`` per side as
of the kick-off. For speed the calendar holds only the events starting in
[earliest kick-off - SQL_WINDOW_BEFORE_DAYS, latest kick-off +
SQL_WINDOW_AFTER_DAYS] plus every event of the fixtures' own (competition)
seasons (``layoff_kind`` "season_start" reads the side's whole past in that
season): with COVERAGE_DAYS = 120 < 150 every feature of a covered side is the
full calendar's (tests/sofa/test_schedule_term.py proves it), and a side with
no coverage takes t = 0 either way.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

from bet.sofa import epochs
from bet.sofa.config import config_path
from bet.sofa.cup_strength import load as load_cup_strength
from bet.sofa.football_rating import FootballForecast
from bet.sofa.schedule_features import (
    COVERAGE_DAYS,
    DAY_S,
    FOOTBALL_COLUMNS,
    Calendar,
    FootballSideFeatures,
    calendar_from_events,
    iter_listed_events,
    match_from_event,
)

CONFIG_FILE = "sofa_schedule_terms.json"
NOTE = "SCHEDULE_TERM"
SPORT = "football"
# The SQL pre-filter (speed only; features identical, see the module doc).
SQL_WINDOW_BEFORE_DAYS = 150
SQL_WINDOW_AFTER_DAYS = 10
# Chosen, not fitted (pre-registration section 4; schedule_features): the
# rest bucket edges, the 96 h continental window, 4 matches in 14 days, 30
# national matches a day = an international break, the 120-day coverage, the
# 7-day extra-time window, the 25 December winter mark, the shrinkage tau and
# the SQL window. Every row the term touches names them (CLAUDE.md: never
# strip UNFITTED_CONSTANTS).
UNFITTED_CONSTANTS: tuple[str, ...] = (
    "SCHEDULE_REST_EDGES", "SCHEDULE_CONTINENTAL_WINDOW_H",
    "SCHEDULE_DENSE14_MATCHES", "SCHEDULE_INTL_DAY_MATCHES",
    "SCHEDULE_COVERAGE_DAYS", "SCHEDULE_ET_PREV_DAYS",
    "SCHEDULE_WINTER_MARK", "SCHEDULE_SHRINK_TAU", "SCHEDULE_SQL_WINDOW_DAYS",
)

if SQL_WINDOW_BEFORE_DAYS <= COVERAGE_DAYS:  # pragma: no cover - a guard
    raise AssertionError("the SQL window must reach past the coverage window")

# Row statuses (`schedule_term.status`)
APPLIED = "APPLIED"  # both sides covered, club fixture: t as computed
NATIONAL = "NATIONAL"  # a national team's fixture: t = 0 (out of the fit)
NO_COVERAGE = "NO_COVERAGE"  # a side with no match in COVERAGE_DAYS: t = 0
NO_FEATURES = "NO_FEATURES"  # the fixture was not read (no side ids): t = 0
EXCLUDED_FLOOR = "EXCLUDED_FLOOR"  # a 0.60-floor key: p uncorrected (D13)


@dataclass(frozen=True)
class ScheduleTerms:
    """config/sofa_schedule_terms.json."""

    columns: tuple[str, ...]
    coef: Mapping[str, float]
    excluded_markets: frozenset[str]


def load(path: Path | None = None) -> ScheduleTerms:
    """The installed coefficients; a missing / malformed file raises."""
    p = path if path is not None else config_path(CONFIG_FILE)
    doc = json.loads(p.read_text(encoding="utf-8"))
    columns = tuple(str(c) for c in doc["columns"])
    if columns != FOOTBALL_COLUMNS:
        raise ValueError(f"{p}: columns {columns} are not "
                         f"schedule_features.FOOTBALL_COLUMNS")
    allowed = {f"{w}_{c}" for w in ("own", "opp") for c in columns}
    coef: dict[str, float] = {}
    for key, value in dict(doc["coef"]).items():
        if key not in allowed:
            raise ValueError(f"{p}: coefficient {key!r} is not own_/opp_ + a column")
        if (not isinstance(value, (int, float)) or isinstance(value, bool)
                or not math.isfinite(float(value))):
            raise ValueError(f"{p}: coefficient {key!r} is not a number")
        coef[key] = float(value)
    excluded = frozenset(str(m) for m in doc.get("excluded_markets") or ())
    return ScheduleTerms(columns=columns, coef=coef, excluded_markets=excluded)


def side_term(coefs: Mapping[str, float], own: FootballSideFeatures,
              opp: FootballSideFeatures) -> float:
    """t of the side ``own`` against ``opp``; 0 when either side has no
    coverage (the measurement's ``side_t``)."""
    if not (own.coverage and opp.coverage):
        return 0.0
    io, ip = own.indicators(), opp.indicators()
    return (sum(coefs.get(f"own_{c}", 0.0) * io[c] for c in FOOTBALL_COLUMNS)
            + sum(coefs.get(f"opp_{c}", 0.0) * ip[c] for c in FOOTBALL_COLUMNS))


def scale(value: float, t: float) -> float:
    """The term's arithmetic on one goals centre: value x exp(t) (t = 0: the
    value itself) - what ``ScheduleTermForecast.centre`` returns and what a
    replay of stored centres applies (``ReplayTerms.scaled``)."""
    return value if t == 0.0 else value * math.exp(t)


def features_dict(f: FootballSideFeatures | None) -> dict[str, Any] | None:
    """A side's features for the row: the dataclass fields and the design
    columns that are 1."""
    if f is None:
        return None
    out: dict[str, Any] = asdict(f)
    out["indicators"] = [c for c, v in f.indicators().items() if v]
    return out


@dataclass(frozen=True)
class FixtureKey:
    """What the features of one fixture are read from."""

    event_id: int
    kickoff_ts: int
    home_id: int
    away_id: int
    competition_id: int | None
    season_id: int | None
    national: bool | None = None  # Fixture.national_teams (None: unknown)


@dataclass(frozen=True)
class FixtureTerm:
    status: str
    t_home: float
    t_away: float
    home: FootballSideFeatures | None
    away: FootballSideFeatures | None

    @property
    def moves(self) -> bool:
        return self.t_home != 0.0 or self.t_away != 0.0

    def row_field(self, status: str | None = None) -> dict[str, Any]:
        return {"status": status or self.status,
                "t_home": round(self.t_home, 6), "t_away": round(self.t_away, 6),
                "home": features_dict(self.home), "away": features_dict(self.away)}


# A football fixture the day's read did not cover (no path (ii) rung): x1.
NO_TERM = FixtureTerm(NO_FEATURES, 0.0, 0.0, None, None)


def fixture_term(terms: ScheduleTerms, home: FootballSideFeatures | None,
                 away: FootballSideFeatures | None, national: bool) -> FixtureTerm:
    if national:
        return FixtureTerm(NATIONAL, 0.0, 0.0, home, away)
    if home is None or away is None:
        return FixtureTerm(NO_FEATURES, 0.0, 0.0, home, away)
    if not (home.coverage and away.coverage):
        return FixtureTerm(NO_COVERAGE, 0.0, 0.0, home, away)
    return FixtureTerm(APPLIED, side_term(terms.coef, home, away),
                       side_term(terms.coef, away, home), home, away)


def side_features(cal: Calendar, key: FixtureKey
                  ) -> tuple[FootballSideFeatures, FootballSideFeatures]:
    return (cal.football_side(key.home_id, key.kickoff_ts, key.competition_id,
                              key.season_id),
            cal.football_side(key.away_id, key.kickoff_ts, key.competition_id,
                              key.season_id))


def window_bounds(keys: Sequence[FixtureKey]) -> tuple[int, int]:
    lo = min(k.kickoff_ts for k in keys) - SQL_WINDOW_BEFORE_DAYS * DAY_S
    hi = max(k.kickoff_ts for k in keys) + SQL_WINDOW_AFTER_DAYS * DAY_S
    return lo, hi


def window_calendar(events: Iterable[Mapping[str, Any]], keys: Sequence[FixtureKey],
                    continental: Collection[int]) -> tuple[Calendar, set[int]]:
    """The calendar of the events in the window or of a fixture's season (the
    SQL's filter, applied again in Python so a test can feed any events), and
    the fixture ids a national-team payload names."""
    lo, hi = window_bounds(keys)
    seasons = {k.season_id for k in keys if k.season_id is not None}
    ids = {k.event_id for k in keys}
    cal = Calendar(sport=SPORT, continental=frozenset(continental))
    national: set[int] = set()
    for event in events:
        m = match_from_event(event, SPORT)
        if m is None:
            continue
        if m.event_id in ids and m.national:
            national.add(m.event_id)
        if lo <= m.ts <= hi or m.season_id in seasons:
            cal.add(m)
    return cal, national


def _query(keys: Sequence[FixtureKey]) -> tuple[str, list[Any]]:
    lo, hi = window_bounds(keys)
    seasons = sorted({k.season_id for k in keys if k.season_id is not None})
    ids = sorted({k.event_id for k in keys})
    marks = ",".join("?" * len(seasons))
    id_marks = ",".join("?" * len(ids))
    sql = ("SELECT event_json FROM sofa_listed_event WHERE sport = ? AND ("
           "start_ts IS NULL OR start_ts BETWEEN ? AND ?"
           f" OR event_id IN ({id_marks})")
    params: list[Any] = [SPORT, lo, hi, *ids]
    if seasons:
        sql += (" OR (json_valid(event_json) AND "
                f"json_extract(event_json, '$.season.id') IN ({marks}))")
        params.extend(seasons)
    return sql + ")", params


def listed_events(conn: sqlite3.Connection, keys: Sequence[FixtureKey]
                  ) -> Iterable[dict[str, Any]]:
    """The listed football payloads the window calendar needs (read-only)."""
    sql, params = _query(keys)
    for (raw,) in conn.execute(sql, params):
        try:
            event = json.loads(raw)
        except (TypeError, ValueError):
            continue
        if isinstance(event, dict):
            yield event


def fixture_terms(conn: sqlite3.Connection, keys: Sequence[FixtureKey],
                  terms: ScheduleTerms, continental: Collection[int]
                  ) -> dict[int, FixtureTerm]:
    """Each fixture's term as of its kick-off, from the listed events of the
    connection (one read-only query)."""
    if not keys:
        return {}
    cal, national = window_calendar(listed_events(conn, keys), keys, continental)
    out: dict[int, FixtureTerm] = {}
    for k in keys:
        home, away = side_features(cal, k)
        out[k.event_id] = fixture_term(
            terms, home, away, bool(k.national) or k.event_id in national)
    return out


def load_fixture_terms(db_path: str | Path, keys: Sequence[FixtureKey],
                       terms: ScheduleTerms, continental: Collection[int]
                       ) -> dict[int, FixtureTerm]:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        return fixture_terms(conn, keys, terms, continental)
    finally:
        conn.close()


@dataclass(frozen=True)
class ScheduleTermForecast(FootballForecast):
    """A FootballForecast whose ``centre("goals_for", side)`` carries the
    side's exp(t); every other call is the wrapped forecast's."""

    t_home: float = 0.0
    t_away: float = 0.0
    wrapped: FootballForecast | None = field(default=None, compare=False,
                                             repr=False)

    @classmethod
    def wrap(cls, base: FootballForecast, t_home: float,
             t_away: float) -> ScheduleTermForecast:
        own = {f.name: getattr(base, f.name) for f in fields(FootballForecast)}
        return cls(**own, t_home=t_home, t_away=t_away, wrapped=base)

    def _base(self) -> FootballForecast:
        assert self.wrapped is not None, "use ScheduleTermForecast.wrap"
        return self.wrapped

    def centre(self, market: str, side: str | None) -> tuple[float, str] | None:
        got = self._base().centre(market, side)
        if got is None or market != "goals_for" or side not in ("side_a", "side_b"):
            return got
        t = self.t_home if side == "side_a" else self.t_away
        if t == 0.0:
            return got
        return scale(got[0], t), f"{got[1]}; {NOTE} exp({t:+.4f})"

    def supremacy(self, side: str) -> float | None:
        return self._base().supremacy(side)

    def no_league_rate(self, market: str) -> bool:
        return self._base().no_league_rate(market)

    def fixture_link(self) -> str:
        return self._base().fixture_link()

    def link_status(self, market: str) -> str | None:
        return self._base().link_status(market)

    def venue_multiplier(self, market: str, side: str,
                         venues: Iterable[str | None]) -> float | None:
        return self._base().venue_multiplier(market, side, venues)


# The result rows' note "pure rating centres home X / away Y"
# (rating_market_gap._RE_PURE reads it). On a corrected row it keeps naming
# the UNCORRECTED rating - the number the gap flag was measured on - and the
# corrected centres the p was priced from follow it.
_PURE = re.compile(r"pure rating centres home ([\d.]+) / away ([\d.]+)")


def pure_note(note: str, base_home: float, base_away: float,
              term: FixtureTerm) -> str:
    def sub(m: re.Match[str]) -> str:
        return (f"pure rating centres home {base_home:.3f} / away "
                f"{base_away:.3f} (x {NOTE} exp(t) home {math.exp(term.t_home):.4f}"
                f" / away {math.exp(term.t_away):.4f} = home {m.group(1)} / away "
                f"{m.group(2)})")
    return _PURE.sub(sub, note)


def term_note(term: FixtureTerm) -> str:
    return (f"{NOTE}: goals centres x exp(t), t home {term.t_home:+.4f} / away "
            f"{term.t_away:+.4f} ({term.status}; frozen coefficients "
            "config/sofa_schedule_terms.json, epochs.SCHEDULE_TERM); "
            "p_central_no_schedule_term is the row without it")


def unfitted_note() -> str:
    return "UNFITTED_CONSTANTS: " + ", ".join(UNFITTED_CONSTANTS)


# --- whole-history replay (the curve fitters' --schedule-term) -----------------


@dataclass
class ReplayTerms:
    """The term of every replayed match from ONE calendar of every listed
    football event (``schedule_features.calendar_from_events``), read per
    match exactly as SHEET reads a fixture (``side_features`` +
    ``fixture_term`` - ``fixture_terms`` on a window of the same listings;
    with COVERAGE_DAYS < SQL_WINDOW_BEFORE_DAYS every covered side's features
    are the full calendar's, tests/sofa/test_schedule_term.py). National:
    the caller's flag or the event's own listing payload, as
    ``window_calendar`` reads it. ``statuses`` counts what was read."""

    calendar: Calendar
    terms: ScheduleTerms
    statuses: dict[str, int] = field(default_factory=dict)

    def term(self, event_id: int, kickoff_ts: int, home_id: int, away_id: int,
             competition_id: int | None, season_id: int | None = None,
             national: bool | None = None) -> FixtureTerm:
        listed = self.calendar.get(event_id)
        if season_id is None and listed is not None:
            season_id = listed.season_id
        key = FixtureKey(event_id=event_id, kickoff_ts=kickoff_ts,
                         home_id=home_id, away_id=away_id,
                         competition_id=competition_id, season_id=season_id,
                         national=national)
        home, away = side_features(self.calendar, key)
        got = fixture_term(self.terms, home, away, bool(national) or (
            listed is not None and listed.national))
        self.statuses[got.status] = self.statuses.get(got.status, 0) + 1
        return got

    def of_result(self, r: Any) -> FixtureTerm:
        """The term of a ``football_rating.FootballResult`` (or any object
        with its event_id / ts / competition_id / home_id / away_id and an
        optional season_id)."""
        return self.term(int(r.event_id), int(r.ts), int(r.home_id),
                         int(r.away_id), r.competition_id,
                         getattr(r, "season_id", None))

    def forecast(self, fc: FootballForecast, r: Any) -> FootballForecast:
        """``fc`` as SHEET's path (ii) rows read it: wrapped when the term
        moves, else ``fc`` itself."""
        got = self.of_result(r)
        if not got.moves:
            return fc
        return ScheduleTermForecast.wrap(fc, got.t_home, got.t_away)

    @staticmethod
    def scaled(home: float, away: float, term: FixtureTerm) -> tuple[float, float]:
        """Stored pure goals centres with the term (``scale``)."""
        return scale(home, term.t_home), scale(away, term.t_away)

    def stamp(self, db_path: str | Path, config: Path | None = None
              ) -> dict[str, Any]:
        """What a fitter records in its fitted_from under --schedule-term."""
        cfg = config if config is not None else config_path(CONFIG_FILE)
        return {"rule": epochs.SCHEDULE_TERM, "flag": "--schedule-term",
                "config": str(cfg),
                "config_sha256": hashlib.sha256(cfg.read_bytes()).hexdigest(),
                "calendar_db": str(db_path),
                "calendar_events": len(self.calendar),
                "statuses": dict(sorted(self.statuses.items())),
                "code": "bet.sofa.schedule_term.ReplayTerms (side_features + "
                        "fixture_term, SHEET's functions) on one calendar of "
                        "every listed football event",
                "unfitted_constants": list(UNFITTED_CONSTANTS)}


def full_calendar(conn: sqlite3.Connection, continental: Collection[int]
                  ) -> Calendar:
    """Every listed football event of the connection (read-only)."""
    return calendar_from_events(iter_listed_events(conn, SPORT), SPORT,
                                continental)


def load_replay_terms(db_path: str | Path, terms: ScheduleTerms | None = None,
                      continental: Collection[int] | None = None) -> ReplayTerms:
    """The replay's terms: the installed coefficients and SHEET's continental
    competitions (``cup_strength.load().competitions``) unless given."""
    if continental is None:
        continental = load_cup_strength().competitions
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        cal = full_calendar(conn, continental)
    finally:
        conn.close()
    return ReplayTerms(cal, terms if terms is not None else load())
