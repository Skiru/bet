"""Football referees: who refereed which match, and the as-of referee feature.

Why (2026-10-21, docs/sofa/evidence/referee_effect_2026-10-21.md): cards and
fouls are priced without the referee. On 2026-10-08 the referee was known for
0.19% of the matches with statistics (sofa_event_detail only), and only as a
career card that is not as of the match. This module keeps the referee of
every match we can label and builds the referee's record from OUR OWN
settled history, strictly before the match.

Storage (created here, idempotent, beside bet.sofa.db's tables):

  * ``sofa_event_referee`` - one row per event: the referee's id and name
    (both NULL when /event was asked and named no referee), start, unique
    tournament, the sport slug, and the source that labelled it: ``event``
    (an /event/{id} payload fetched by backfill_referees.py), ``referee_page``
    (one of the 30 events of /referee/{id}/events/last/{p}) or ``detail``
    (the sofa_event_detail RESOLVE / FIXTURE_CHECK already cached). A label
    with a referee is never overwritten by an empty one.
  * ``sofa_referee_page`` - the pages of a referee's history already read
    (backfill progress: resumable, a page is never asked twice in one pass).
  * ``sofa_referee`` - the referee's name, country and the career card the
    payload carried when last seen (display only; never a feature: it is not
    as of the match).

The as-of feature (``RefereeBook``): for a match at time t, the referee's
previous labelled matches in the history (start < t, with the metric) give
r_i = y_i / L_i, the match's count over its competition's as-of mean; the
feature is the shrunk ratio (sum r_i + K) / (n + K) - with one competition
it is the briefed (sum_ref + K x L) / (n + K) / L, and a referee who moves
between a league and a cup is read at each match's own level. No referee
or no record: 1.0.
"""

from __future__ import annotations

import json
import math
import sqlite3
from collections import defaultdict
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bet.sofa.db import get_connection
from bet.sofa.timeutil import now

SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS sofa_event_referee (
        event_id             INTEGER PRIMARY KEY,
        referee_id           INTEGER,
        referee_name         TEXT,
        start_ts             INTEGER,
        unique_tournament_id INTEGER,
        sport                TEXT,
        source               TEXT    NOT NULL,
        fetched_at           TEXT    NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS sofa_event_referee_ref "
    "ON sofa_event_referee (referee_id, start_ts)",
    """
    CREATE TABLE IF NOT EXISTS sofa_referee_page (
        referee_id  INTEGER NOT NULL,
        page        INTEGER NOT NULL,
        fetched_at  TEXT    NOT NULL,
        n_events    INTEGER NOT NULL,
        oldest_ts   INTEGER,
        has_next    INTEGER NOT NULL,
        PRIMARY KEY (referee_id, page)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sofa_referee (
        referee_id   INTEGER PRIMARY KEY,
        name         TEXT,
        country      TEXT,
        games        INTEGER,
        yellow_cards INTEGER,
        red_cards    INTEGER,
        yellow_red_cards INTEGER,
        fetched_at   TEXT    NOT NULL
    )
    """,
)

SOURCES = frozenset({"event", "referee_page", "detail"})


def ensure_schema(db_path: str | Path) -> None:
    """Create the referee tables if missing. Idempotent."""
    with get_connection(str(db_path)) as conn:
        for q in SCHEMA:
            conn.execute(q)
        conn.commit()


@dataclass(frozen=True)
class EventReferee:
    event_id: int
    referee_id: int | None
    referee_name: str | None
    start_ts: int | None
    unique_tournament_id: int | None
    sport: str | None
    source: str


@dataclass(frozen=True)
class Referee:
    referee_id: int
    name: str | None
    country: str | None
    games: int | None
    yellow_cards: int | None
    red_cards: int | None
    yellow_red_cards: int | None


def _int(raw: object) -> int | None:
    return raw if isinstance(raw, int) and not isinstance(raw, bool) else None


def _event_meta(event: Mapping[str, Any]) -> tuple[int | None, int | None, str | None]:
    """(start_ts, unique tournament id, sport slug) of one event dict."""
    tour = event.get("tournament") or {}
    unique = tour.get("uniqueTournament") or {}
    sport = ((tour.get("category") or {}).get("sport") or {}).get("slug")
    return (_int(event.get("startTimestamp")), _int(unique.get("id")),
            sport if isinstance(sport, str) else None)


def referee_of(raw: object) -> Referee | None:
    """A payload's ``referee`` object, or None when it names nobody."""
    if not isinstance(raw, Mapping):
        return None
    rid = _int(raw.get("id"))
    if rid is None:
        return None
    country = raw.get("country")
    if isinstance(country, Mapping):
        country = country.get("name") or country.get("alpha2")
    name = raw.get("name")
    return Referee(rid, name if isinstance(name, str) else None,
                   country if isinstance(country, str) else None,
                   _int(raw.get("games")), _int(raw.get("yellowCards")),
                   _int(raw.get("redCards")), _int(raw.get("yellowRedCards")))


def from_event_detail(
    event_id: int, detail: Mapping[str, Any] | None, source: str = "event",
) -> tuple[EventReferee, Referee | None]:
    """The label one /event/{id} payload gives (referee None: asked, nobody)."""
    event = (detail or {}).get("event") or {}
    ref = referee_of(event.get("referee"))
    ts, unique, sport = _event_meta(event)
    return (EventReferee(event_id, ref.referee_id if ref else None,
                         ref.name if ref else None, ts, unique, sport, source),
            ref)


def from_referee_page(
    referee_id: int, payload: Mapping[str, Any] | None,
    name: str | None = None,
) -> tuple[list[EventReferee], int | None, bool]:
    """(labels, oldest start on the page, hasNextPage) of one
    /referee/{id}/events/last/{p} answer. Every listed event is this
    referee's; a 404 (None) is an empty last page."""
    if not payload:
        return [], None, False
    out: list[EventReferee] = []
    oldest: int | None = None
    for ev in payload.get("events") or []:
        eid = _int(ev.get("id")) if isinstance(ev, Mapping) else None
        if eid is None:
            continue
        ts, unique, sport = _event_meta(ev)
        if ts is not None:
            oldest = ts if oldest is None else min(oldest, ts)
        out.append(EventReferee(eid, referee_id, name, ts, unique, sport,
                                "referee_page"))
    return out, oldest, bool(payload.get("hasNextPage"))


class RefereeStore:
    """Writes and reads of the referee tables; one short transaction each."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        ensure_schema(self.db_path)

    def save_labels(self, labels: Iterable[EventReferee]) -> int:
        """Upsert labels; a known referee is never replaced by an empty
        answer, and an ``event`` label keeps its source when a referee page
        or the detail seed names it again (the backfill's per-competition
        count reads it).
        Returns the rows written."""
        rows = [(lb.event_id, lb.referee_id, lb.referee_name, lb.start_ts,
                 lb.unique_tournament_id, lb.sport, lb.source, now().isoformat())
                for lb in labels]
        if not rows:
            return 0
        with get_connection(self.db_path) as conn:
            conn.executemany(
                """
                INSERT INTO sofa_event_referee
                (event_id, referee_id, referee_name, start_ts,
                 unique_tournament_id, sport, source, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(event_id) DO UPDATE SET
                    referee_id = COALESCE(excluded.referee_id, referee_id),
                    referee_name = COALESCE(excluded.referee_name, referee_name),
                    start_ts = COALESCE(excluded.start_ts, start_ts),
                    unique_tournament_id = COALESCE(
                        excluded.unique_tournament_id, unique_tournament_id),
                    sport = COALESCE(excluded.sport, sport),
                    source = CASE WHEN excluded.referee_id IS NULL
                                  AND referee_id IS NOT NULL THEN source
                                  WHEN source = 'event'
                                  AND excluded.source <> 'event'
                                  THEN source ELSE excluded.source END,
                    fetched_at = excluded.fetched_at
                """,
                rows,
            )
            conn.commit()
        return len(rows)

    def save_referee(self, ref: Referee) -> None:
        with get_connection(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO sofa_referee
                (referee_id, name, country, games, yellow_cards, red_cards,
                 yellow_red_cards, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (ref.referee_id, ref.name, ref.country, ref.games,
                 ref.yellow_cards, ref.red_cards, ref.yellow_red_cards,
                 now().isoformat()),
            )
            conn.commit()

    def save_page(self, referee_id: int, page: int, n_events: int,
                  oldest_ts: int | None, has_next: bool) -> None:
        with get_connection(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO sofa_referee_page
                (referee_id, page, fetched_at, n_events, oldest_ts, has_next)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (referee_id, page, now().isoformat(), n_events, oldest_ts,
                 int(has_next)),
            )
            conn.commit()


def _ro(db_path: str | Path) -> sqlite3.Connection:
    uri = Path(db_path).resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=30.0)
    conn.row_factory = sqlite3.Row
    return conn


def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                        "AND name=?", (name,)).fetchone() is not None


def next_page(pages: Iterable[tuple[int, int | None, bool]],
              cutoff_ts: int) -> int | None:
    """The next page of a referee to ask, from the (page, oldest_ts,
    has_next) already read: None when done - the last page read had no next
    page, or reached back past ``cutoff_ts``, or was empty."""
    read = sorted(pages)
    if not read:
        return 0
    page, oldest, has_next = read[-1]
    if not has_next or oldest is None or oldest < cutoff_ts:
        return None
    return page + 1


def referee_for_event(db_path: str | Path, event_id: int) -> EventReferee | None:
    """The referee of one fixture at prediction time: the stored label, else
    the cached /event payload RESOLVE / FIXTURE_CHECK wrote. None: nobody
    named yet (Sofascore announces referees late)."""
    conn = _ro(db_path)
    try:
        if _has_table(conn, "sofa_event_referee"):
            row = conn.execute(
                "SELECT referee_id, referee_name, start_ts, unique_tournament_id, "
                "sport, source FROM sofa_event_referee WHERE event_id = ? "
                "AND referee_id IS NOT NULL", (event_id,)).fetchone()
            if row is not None:
                return EventReferee(event_id, row["referee_id"],
                                    row["referee_name"], row["start_ts"],
                                    row["unique_tournament_id"], row["sport"],
                                    row["source"])
        if _has_table(conn, "sofa_event_detail"):
            row = conn.execute(
                "SELECT detail_json FROM sofa_event_detail "
                "WHERE sofascore_event_id = ?", (event_id,)).fetchone()
            if row is not None:
                label, _ = from_event_detail(event_id, json.loads(row[0]), "detail")
                if label.referee_id is not None:
                    return label
    finally:
        conn.close()
    return None


def load_labels(db_path: str | Path, sport: str | None = "football",
                ) -> dict[int, int]:
    """event id -> referee id of every labelled event (of ``sport``; None
    keeps every sport), plus the referees sofa_event_detail names for events
    not labelled otherwise. Read-only."""
    out: dict[int, int] = {}
    conn = _ro(db_path)
    try:
        if _has_table(conn, "sofa_event_detail"):
            for eid, raw in conn.execute(
                    "SELECT sofascore_event_id, "
                    "json_extract(detail_json, '$.event.referee.id') "
                    "FROM sofa_event_detail WHERE json_extract(detail_json, "
                    "'$.event.referee.id') IS NOT NULL"):
                if isinstance(raw, int):
                    out[int(eid)] = raw
        if _has_table(conn, "sofa_event_referee"):
            q = ("SELECT event_id, referee_id FROM sofa_event_referee "
                 "WHERE referee_id IS NOT NULL")
            args: tuple[Any, ...] = ()
            if sport is not None:
                q += " AND (sport = ? OR sport IS NULL)"
                args = (sport,)
            for eid, rid in conn.execute(q, args):
                out[int(eid)] = int(rid)
    finally:
        conn.close()
    return out


# --- the as-of feature ------------------------------------------------------

# A competition's as-of mean needs this many previous matches with the metric;
# below it the metric's pooled mean of every competition is read.
MIN_LEAGUE_MATCHES = 30
# Default prior weight of the shrunk ratio, in matches (fitted per metric by
# scripts/sofa/measure_referee_effect.py; the config carries the fitted K).
DEFAULT_K = 10.0


@dataclass(frozen=True)
class RefereeRead:
    """The referee's as-of record for one metric at one match."""

    referee_id: int | None
    n: int          # previous labelled matches with the metric
    ratio_sum: float  # sum of y_i / L_i over them
    league_mean: float | None  # the match competition's as-of mean (L)

    def ratio(self, k: float) -> float:
        """(sum r_i + K) / (n + K); 1.0 without a record."""
        if self.n <= 0 or k + self.n <= 0:
            return 1.0
        return (self.ratio_sum + k) / (self.n + k)


class RefereeBook:
    """Walk-forward referee and competition records, per metric (a match
    total). ``read`` before ``update`` for a match: the record holds only
    matches already added, so a caller that adds in time order and reads a
    match before adding it never sees the match or anything after it."""

    def __init__(self, metrics: Iterable[str]) -> None:
        self.metrics = tuple(metrics)
        self.league: dict[tuple[int, str], list[float]] = defaultdict(
            lambda: [0.0, 0.0])
        self.pooled: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
        self.ref: dict[tuple[int, str], list[float]] = defaultdict(
            lambda: [0.0, 0.0])

    def league_mean(self, competition_id: int, metric: str) -> float | None:
        st = self.league.get((competition_id, metric))
        if st is not None and st[1] >= MIN_LEAGUE_MATCHES and st[0] > 0:
            return st[0] / st[1]
        p = self.pooled.get(metric)
        if p is not None and p[1] >= MIN_LEAGUE_MATCHES and p[0] > 0:
            return p[0] / p[1]
        return None

    def read(self, referee_id: int | None, competition_id: int,
             metric: str) -> RefereeRead:
        lm = self.league_mean(competition_id, metric)
        if referee_id is None:
            return RefereeRead(None, 0, 0.0, lm)
        st = self.ref.get((referee_id, metric))
        if st is None:
            return RefereeRead(referee_id, 0, 0.0, lm)
        return RefereeRead(referee_id, int(st[1]), st[0], lm)

    def update(self, referee_id: int | None, competition_id: int,
               values: Mapping[str, float]) -> None:
        """Add one finished match's totals (metric -> count). The referee's
        ratio is taken against the competition's mean BEFORE this match."""
        for metric, y in values.items():
            if metric not in self.metrics:
                continue
            if referee_id is not None:
                lm = self.league_mean(competition_id, metric)
                if lm is not None:
                    st = self.ref[(referee_id, metric)]
                    st[0] += y / lm
                    st[1] += 1
            lg = self.league[(competition_id, metric)]
            lg[0] += y
            lg[1] += 1
            pl = self.pooled[metric]
            pl[0] += y
            pl[1] += 1


@dataclass(frozen=True)
class MatchTotals:
    event_id: int
    ts: int
    competition_id: int
    referee_id: int | None
    values: Mapping[str, float]  # metric -> the match total


def walk_reads(
    matches: Iterable[MatchTotals], metrics: Iterable[str],
) -> Iterator[tuple[MatchTotals, dict[str, RefereeRead]]]:
    """(match, metric -> its as-of read) for every match, in the given (time)
    order. Matches that start at the same second are all read before any of
    them is added: nothing of a kick-off time is known at that kick-off."""
    book = RefereeBook(metrics)
    pending: list[MatchTotals] = []
    ts_now: int | None = None
    for m in matches:
        if ts_now is not None and m.ts != ts_now:
            for p in pending:
                book.update(p.referee_id, p.competition_id, p.values)
            pending = []
        if ts_now is not None and m.ts < ts_now:
            raise ValueError("matches out of time order")
        ts_now = m.ts
        yield m, {metric: book.read(m.referee_id, m.competition_id, metric)
                  for metric in book.metrics}
        pending.append(m)


# --- the live term (epochs.FOOTBALL_REFEREE, off while None) ---------------

CONFIG_FILE = "sofa_referee_effect.json"
# Family -> the history metric whose match total is the referee's record.
FAMILY_METRIC: Mapping[str, str] = {"cards_points": "cards_points_for",
                                    "fouls": "fouls_for"}
# Chosen, not fitted: the as-of competition mean needs MIN_LEAGUE_MATCHES.
REFEREE_UNFITTED: tuple[str, ...] = ("MIN_LEAGUE_MATCHES",)
NO_REFEREE = "NO_REFEREE"
NO_RECORD = "NO_REFEREE_RECORD"
APPLIED = "APPLIED"


def family_of(market: str) -> str | None:
    """The referee family a market reads (None: the term does not apply)."""
    if market.startswith("cards_points_"):
        return "cards_points"
    if market.startswith("fouls_") and not market.startswith("fouls_drawn"):
        return "fouls"
    return None


@dataclass(frozen=True)
class EffectCell:
    family: str
    beta: float
    k: float


@dataclass(frozen=True)
class RefereeEffectTable:
    markets: Mapping[str, EffectCell]
    path: str | None = None

    def apply(self, market: str, read: RefereeRead | None,
              ) -> tuple[float, dict[str, Any]] | None:
        """(multiplier, the row's referee_read) for a market of the table,
        None for any other. No referee named: 1.0, NO_REFEREE; a referee
        without a record in our history: 1.0, NO_REFEREE_RECORD; else
        ratio_K ** beta."""
        cell = self.markets.get(market)
        if cell is None:
            return None
        if read is None or read.referee_id is None:
            return 1.0, {"status": NO_REFEREE}
        if read.n <= 0:
            return 1.0, {"status": NO_RECORD, "referee_id": read.referee_id}
        ratio = read.ratio(cell.k)
        mult = ratio ** cell.beta
        return mult, {"status": APPLIED, "referee_id": read.referee_id,
                      "n": read.n, "ratio": round(ratio, 4),
                      "multiplier": round(mult, 4)}


def parse_effect_table(data: Mapping[str, Any],
                       path: str | None = None) -> RefereeEffectTable:
    cells: dict[str, EffectCell] = {}
    for market, raw in (data.get("markets") or {}).items():
        fam = str(raw["family"])
        if fam not in FAMILY_METRIC or family_of(str(market)) != fam:
            raise ValueError(f"{path}: {market} family {fam!r}")
        k, beta = float(raw["K"]), float(raw["beta"])
        if not (k > 0 and math.isfinite(beta)):
            raise ValueError(f"{path}: {market} K {k} beta {beta}")
        cells[str(market)] = EffectCell(fam, beta, k)
    if not cells:
        raise ValueError(f"{path}: no markets")
    return RefereeEffectTable(cells, path)


def load_effect_table(path: Path | None = None) -> RefereeEffectTable:
    """config/sofa_referee_effect.json; raises when missing or malformed (a
    switched-on rule never silently prices without it)."""
    from bet.sofa.config import config_path
    p = path if path is not None else config_path(CONFIG_FILE)
    return parse_effect_table(json.loads(p.read_text(encoding="utf-8")), str(p))


def fixture_reads(
    history: Iterable[Any], labels: Mapping[int, int], cut_ts: int,
    fixture_referees: Mapping[int, int | None],
) -> dict[int, dict[str, RefereeRead]]:
    """event id -> family -> the fixture referee's read, from the history's
    matches that started strictly before ``cut_ts`` (football_rating.
    FootballResult: event_id, ts, competition_id, values) - no match of the
    day or after it. The term reads only the referee's record (n, ratio
    sum); the read's league_mean is the pooled one and is not used."""
    book = RefereeBook(FAMILY_METRIC)
    for r in history:
        if r.ts >= cut_ts:
            break
        vals = {fam: float(sum(r.values[m])) for fam, m in FAMILY_METRIC.items()
                if m in r.values}
        book.update(labels.get(r.event_id), r.competition_id, vals)
    out: dict[int, dict[str, RefereeRead]] = {}
    for eid, rid in fixture_referees.items():
        out[eid] = {fam: book.read(rid, -1, fam) for fam in FAMILY_METRIC}
    return out
