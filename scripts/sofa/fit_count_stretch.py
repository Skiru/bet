"""Fit the count-stretch coefficients (epochs.FOOTBALL_COUNT_STRETCH) into
config/sofa_count_stretch.json.

The 2026-10-17 measurement's fit, reproduced: for every market of
count_stretch.COUNT_STRETCH_MARKETS (or --markets) the coefficients of
exp(beta x s [+ beta2 x s^2]) (a side) or exp(g1 |s| + g2 s^2) (a total, g2
written 0 where the market was measured to need |s| alone) - as many terms
as count_stretch.COUNT_STRETCH_TERMS says - by Poisson pseudo-likelihood,
log link, offset log centre (supremacy_stretch.fit_terms), on every row of
the replayed history from --train-from (default 2026-01-01: the mature
rating book the measurement recommends) to the day before --before.

The centre is SHEET's count centre one step ahead (the measurement's
b_walk): a side's last SAMPLE_N values of the metric (any competition),
rescaled by the B15 opponent correction (SampleCorrector on the book as of
the match) where the metric is corrected, shrunk with the market's K toward
the competition's per-side rate (the book's for a rated metric, a running
league mean - else the gender's - for the counts the book does not rate),
blended with the rating where the market is rated (the centre rules of
measure_game_state: --live-rules / --rated-scope / --rating-weight); a total
pools both sides' last match totals toward the sum of the rates. s is the
side's expected goal difference from the rating's goals book
(FootballForecast.supremacy; a total the home side's). The book learns the
league strength in international club cups by default, as live SHEET's
(epochs.FOOTBALL_CUP_STRENGTH, on since 2026-10-16;
config/sofa_cup_strength.json of the config dir, --cup-strength FILE another,
--no-cup-strength the plain book the 2026-10-17 measurement read). None of the 16
markets carries GAME_STATE, so its term is not in the offset. The venue
prior (a sample-only corners half centre) is not replayed: the half
corners are rated (RATED_SCOPE_MARKETS) under the live rules.

The counts the cached football history does not carry (second-half shots
and shots on target, saves, throw-ins, goal kicks) are read from
sofa_event_stats with metrics.extract_metric, as SAMPLES and SETTLE read
them (``extend_history``, the measurement's a_extend). Dry run by default:
prints the table; --write writes the file atomically. The file is read only
while epochs.FOOTBALL_COUNT_STRETCH_FROM_UTC is set (inert otherwise). Run
it on a COPY of the DB (CLAUDE.md, Changing the pipeline 4): the parsed
history pickle is kept in a cache/ directory next to --db-path.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/fit_count_stretch.py \\
        --before 2026-10-17 --db-path data/refit_<d>/sofa_replay.db \\
        --live-rules [--no-cup-strength] [--train-from 2026-01-01] \\
        [--markets saves_for ...] \\
        [--write [--out <file>]]
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import defaultdict, deque
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO / "src"), str(_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import count_stretch as cst  # noqa: E402
from bet.sofa import football_rating as fr  # noqa: E402
from bet.sofa import rating_weight as rw  # noqa: E402
from bet.sofa import supremacy_stretch as ss  # noqa: E402
from bet.sofa.atomic import write_bytes_atomic  # noqa: E402
from bet.sofa.config import SofaConfig, config_path  # noqa: E402
from bet.sofa.contracts import GapReason  # noqa: E402
from bet.sofa.cup_strength import CupStrength  # noqa: E402
from bet.sofa.cup_strength import apply as apply_cup_strength  # noqa: E402
from bet.sofa.cup_strength import load as load_cup_strength  # noqa: E402
from bet.sofa.metrics import extract_flat_statistics, extract_metric  # noqa: E402
from bet.sofa.opponent_correction import (  # noqa: E402
    SampleCorrector,
    corrected_metric,
)
from scripts.sofa.measure_game_state import (  # noqa: E402
    CentreRules,
    _ts,
    add_rule_args,
    k_table,
    rules_from_args,
)

SAMPLE_N = 10
MIN_VALUES = 5
SPORT_K = 15.0
DEFAULT_TRAIN_FROM = "2026-01-01"


def metric_of(market: str) -> str:
    """The per-side metric a market is counted on (a total: its `_for`)."""
    return market[: -len("_total")] + "_for" if market.endswith("_total") else market


def extra_metrics(markets: Iterable[str]) -> tuple[str, ...]:
    """The markets' metrics the cached history does not carry (no rated base
    metric): read from sofa_event_stats by ``extend_history``."""
    return tuple(sorted({metric_of(m) for m in markets}
                        - set(fr.BASE_METRICS)))


def extend_history(
    history: Sequence[fr.FootballResult], db_path: Path, metrics: Sequence[str],
) -> tuple[list[fr.FootballResult], dict[str, int]]:
    """The history with `metrics` added (home, away) from sofa_event_stats
    wherever extract_metric reads both sides as a count >= 0 - only for the
    matches that already carry statistics (a value beyond the listing's
    goals). Read-only on the DB."""
    out = list(history)
    added = dict.fromkeys(metrics, 0)
    if not metrics:
        return out, added
    need = {r.event_id: i for i, r in enumerate(out)
            if any(m not in fr._LISTING_METRICS for m in r.values)}
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        for eid, s_json, i_json in conn.execute(
                "SELECT sofascore_event_id, statistics_json, incidents_json "
                "FROM sofa_event_stats"):
            i = need.get(eid)
            if i is None or not s_json:
                continue
            flat = extract_flat_statistics(json.loads(s_json))
            incidents = json.loads(i_json) if i_json else None
            values = dict(out[i].values)
            for m in metrics:
                home = extract_metric(m, "football", flat, incidents, {}, True)
                away = extract_metric(m, "football", flat, incidents, {}, False)
                if (not isinstance(home, GapReason)
                        and not isinstance(away, GapReason)
                        and home >= 0 and away >= 0):
                    values[m] = (float(home), float(away))
                    added[m] += 1
            out[i] = replace(out[i], values=values)
    finally:
        conn.close()
    return out, added


class _RunningRates:
    """Per-(competition, metric) and per-(metric, gender) running per-side
    means of the counts the book does not rate - the book's own _League
    update rule (step max(ALPHA_LEAGUE, 1 / (n + 1)))."""

    def __init__(self) -> None:
        self.league: dict[tuple[int, str], list[float]] = {}
        self.gender: dict[tuple[str, bool], list[float]] = {}

    @staticmethod
    def _update(table: dict[Any, list[float]], key: Any,
                home: float, away: float) -> None:
        st = table.get(key)
        if st is None:
            st = table[key] = [0.0, 0.0, 0.0]
        step = max(fr.ALPHA_LEAGUE, 1.0 / (st[2] + 1))
        st[0] += step * (home - st[0])
        st[1] += step * (away - st[1])
        st[2] += 1

    def update(self, competition_id: int, metric: str, women: bool,
               home: float, away: float) -> None:
        self._update(self.league, (competition_id, metric), home, away)
        self._update(self.gender, (metric, women), home, away)

    def rates(self, competition_id: int, metric: str,
              women: bool) -> tuple[float, float] | None:
        for st in (self.league.get((competition_id, metric)),
                   self.gender.get((metric, women))):
            if st is not None and st[2] >= fr.MIN_LEAGUE_MATCHES:
                return st[0], st[1]
        return None


@dataclass(frozen=True)
class StretchRow:
    market: str
    event_id: int
    ts: int
    side: str  # "side_a" / "side_b" / "" (a total)
    y: float
    centre: float
    supremacy: float  # the side's (a total: the home side's)


def _rated(market: str, rules: CentreRules) -> bool:
    return fr.base_metric(market) is not None and (
        market not in fr.UNRATED_MARKETS or market in rules.rated_scope)


Sample = deque[tuple[int, float, float, int]]


class _Factors:
    """SampleCorrector.factors on the book as of one match, memoised."""

    def __init__(self, book: fr.RatingBook) -> None:
        self.corrector = SampleCorrector(book)
        self.cache: dict[tuple[int, int, str], tuple[float, float] | None] = {}

    def __call__(self, team: int, opp: int, today: int,
                 metric: str | None) -> tuple[float, float] | None:
        if metric is None:
            return None
        key = (team, opp, metric)
        if key not in self.cache:
            self.cache[key] = self.corrector.factors(team, opp, today, metric)
        return self.cache[key]


def _centre(fc: fr.FootballForecast, market: str, side: str | None,
            sample: float, rules: CentreRules) -> float:
    """The shrunk sample blended with the rating where the market is rated."""
    rated = fc.centre(market, side) if _rated(market, rules) else None
    if rated is None:
        return sample
    return rw.blend(rated[0], sample, market, rules.rating_weights)


def _match_rows(
    r: fr.FootballResult, fc: fr.FootballForecast, s_home: float,
    metric: str, markets: Sequence[str], rates: tuple[float, float],
    lh: Sample, la: Sample, factor: _Factors,
    k_by_market: Mapping[str, float], rules: CentreRules,
) -> Iterator[StretchRow]:
    vh, va = r.values[metric]
    cm = corrected_metric(metric)
    for market in markets:
        k = float(k_by_market.get(market, SPORT_K))
        if market.endswith("_total"):
            pool: dict[int, float] = {}
            for team, opp_today, own in ((r.home_id, r.away_id, lh),
                                         (r.away_id, r.home_id, la)):
                for o in own:
                    f = factor(team, o[3], opp_today, cm)
                    pool[o[0]] = o[1] * f[0] + o[2] * f[1] if f else o[1] + o[2]
            vals = list(pool.values())
            w = len(vals) / (len(vals) + k)
            sample = w * sum(vals) / len(vals) + (1 - w) * (rates[0] + rates[1])
            yield StretchRow(market, r.event_id, r.ts, "", vh + va,
                             _centre(fc, market, None, sample, rules), s_home)
            continue
        for side, team, opp_today, own, y in (
                ("side_a", r.home_id, r.away_id, lh, vh),
                ("side_b", r.away_id, r.home_id, la, va)):
            side_vals = []
            for o in own:
                f = factor(team, o[3], opp_today, cm)
                side_vals.append(o[1] * f[0] if f else o[1])
            w = len(side_vals) / (len(side_vals) + k)
            sample = (w * sum(side_vals) / len(side_vals)
                      + (1 - w) * (rates[0] + rates[1]) / 2)
            yield StretchRow(market, r.event_id, r.ts, side, y,
                             _centre(fc, market, side, sample, rules),
                             s_home if side == "side_a" else -s_home)


def walk(
    history: Iterable[fr.FootballResult], start_ts: int, end_ts: int,
    markets: Sequence[str], k_by_market: Mapping[str, float],
    rules: CentreRules, sample_n: int = SAMPLE_N, min_values: int = MIN_VALUES,
    cup_strength: CupStrength | None = None,
) -> Iterator[StretchRow]:
    """One row per (match, market, side) in [start_ts, end_ts) with a
    supremacy and both sides' samples of at least ``min_values`` values;
    ``cup_strength``: the book learns the cup league strength (None: the
    plain book)."""
    by_metric: dict[str, list[str]] = defaultdict(list)
    for m in markets:
        by_metric[metric_of(m)].append(m)
    extra = set(extra_metrics(markets))
    book = apply_cup_strength(fr.RatingBook(shared_league_link=True),
                              cup_strength)
    scope = frozenset(fr.UNRATED_MARKETS)
    running = _RunningRates()
    # (team, metric) -> (event id, own, opponent's, opponent id)
    last: dict[tuple[int, str], Sample] = defaultdict(
        lambda: deque(maxlen=sample_n))
    for r in history:
        if r.ts >= end_ts:
            break
        have = [m for m in by_metric if m in r.values]
        if r.ts >= start_ts and have:
            fc = fr.FootballForecast(book, r.competition_id, r.home_id,
                                     r.away_id, rated_scope=scope)
            s_home = fc.supremacy("side_a")
            factor = _Factors(book)
            for metric in have if s_home is not None else ():
                rates = (running.rates(r.competition_id, metric, r.women)
                         if metric in extra
                         else book.league_rates(r.competition_id, metric))
                lh, la = last[(r.home_id, metric)], last[(r.away_id, metric)]
                if (rates is None or s_home is None or len(lh) < min_values
                        or len(la) < min_values):
                    continue
                yield from _match_rows(r, fc, s_home, metric, by_metric[metric],
                                       rates, lh, la, factor, k_by_market, rules)
        for metric in have:
            vh, va = r.values[metric]
            last[(r.home_id, metric)].append((r.event_id, vh, va, r.away_id))
            last[(r.away_id, metric)].append((r.event_id, va, vh, r.home_id))
            if metric in extra:
                running.update(r.competition_id, metric, r.women, vh, va)
        if extra and any(m in extra for m in r.values):
            r = replace(r, values={m: v for m, v in r.values.items()
                                   if m not in extra})
        book.update(r)


def fit_rows(rows: Iterable[StretchRow], markets: Sequence[str],
             ) -> dict[str, dict[str, object]]:
    """market -> its file cell (coefficients, n_rows, n_matches)."""
    cols: dict[str, tuple[list[float], list[float], list[float], set[int]]] = {
        m: ([], [], [], set()) for m in markets}
    for row in rows:
        cell = cols.get(row.market)
        if cell is None:
            continue
        cell[0].append(row.centre)
        cell[1].append(row.supremacy)
        cell[2].append(row.y)
        cell[3].add(row.event_id)
    out: dict[str, dict[str, object]] = {}
    for m in markets:
        centres, sup, y, events = cols[m]
        total = cst.is_total(m)
        coefs = ss.fit_terms(total, centres, sup, y, cst.COUNT_STRETCH_TERMS[m])
        cell_out: dict[str, object] = dict(ss.cell_json(total, coefs))
        cell_out.update({"n_rows": len(y), "n_matches": len(events)})
        out[m] = cell_out
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--before", required=True)
    ap.add_argument("--train-from", default=DEFAULT_TRAIN_FROM)
    ap.add_argument("--markets", nargs="+",
                    default=list(cst.COUNT_STRETCH_MARKETS))
    ap.add_argument("--db-path", help="the DB (a copy) whose cached football "
                    "history and sofa_event_stats are read; default "
                    "SOFA_DB_PATH / data/sofa.db")
    ap.add_argument("--cup-strength", default=None, metavar="FILE",
                    help="the cup list the rating book learns from (default "
                    "the installed config/sofa_cup_strength.json)")
    ap.add_argument("--no-cup-strength", action="store_true",
                    help="the plain rating book (as the measurement)")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--out", help="default config/sofa_count_stretch.json")
    add_rule_args(ap)
    ap.add_argument("--awarded-excluded", action="store_true",
                    help="football results awarded at the table (isAwarded) out of the "
                    "history, as SHEET from epochs.AWARDED_EXCLUDED_FROM_UTC")
    args = ap.parse_args()
    bad = [m for m in args.markets if m not in cst.COUNT_STRETCH_MARKETS]
    if bad:
        print(f"not count-stretch markets: {bad}", file=sys.stderr)
        return 2
    if args.no_cup_strength and args.cup_strength:
        print("--cup-strength and --no-cup-strength", file=sys.stderr)
        return 2
    cup = (None if args.no_cup_strength else load_cup_strength(
        Path(args.cup_strength) if args.cup_strength else None))
    markets = tuple(args.markets)
    last_day = (date.fromisoformat(args.before) - timedelta(days=1)).isoformat()
    rules = rules_from_args(args, last_day)
    db = Path(args.db_path) if args.db_path else Path(SofaConfig.from_env().db_path)
    history = fr.load_history(db, db.parent / "cache")
    if args.awarded_excluded:
        history = fr.without_awarded(history)
    history, added = extend_history(history, db, extra_metrics(markets))
    print(f"history {len(history)}, read from sofa_event_stats: {added}",
          file=sys.stderr, flush=True)
    table = fit_rows(walk(history, _ts(args.train_from), _ts(last_day) + 86400,
                          markets, k_table(markets), rules,
                          cup_strength=cup), markets)
    del history
    doc = {
        "_doc": ("Count stretch (epochs.FOOTBALL_COUNT_STRETCH): a football "
                 "count centre outside GAME_STATE x exp(beta x s [+ beta2 x "
                 "s^2]) (a side, s its expected goal difference) or exp(g1 "
                 "|s| + g2 s^2) (a total, s the home side's). INERT while "
                 "epochs.FOOTBALL_COUNT_STRETCH_FROM_UTC is None. Written by "
                 "scripts/sofa/fit_count_stretch.py."),
        "fitted_from": {
            "awarded_excluded": bool(args.awarded_excluded),
            "fitted_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
            "train_from": args.train_from, "before": args.before,
            "db_path": str(db),
            "method": "Poisson pseudo-likelihood, log link, offset log centre",
            "centre": ("one-step-ahead count centre: last 10 values, B15 "
                       "opponent correction, market K shrink to the league "
                       "rate, rating blend where rated"),
            "centre_rules": rules.describe(),
            "cup_strength": (None if cup is None else
                             args.cup_strength or "config/sofa_cup_strength.json"),
            "terms": {m: cst.COUNT_STRETCH_TERMS[m] for m in markets},
            "evidence": cst.EVIDENCE,
        },
        "unfitted_constants": list(cst.COUNT_STRETCH_UNFITTED),
        "markets": table,
    }
    cst.parse_table(doc)  # what is written must be readable
    text = json.dumps(doc, indent=2) + "\n"
    print(text)
    if args.write:
        target = Path(args.out) if args.out else config_path(cst.CONFIG_FILE)
        write_bytes_atomic(target, text.encode("utf-8"))
        print(f"wrote {target}")
    else:
        print("dry run: nothing written (--write to write)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
