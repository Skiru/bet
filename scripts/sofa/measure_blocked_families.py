#!/usr/bin/env python3
# ruff: noqa: E501  - report lines are tables; the family lists read as one block.
"""Claimed vs realised on settled rows of the families CONFIDENCE refuses (plan F1.3).

`TENNIS_SET_MARKET_NOT_ADMITTED`, `DERIVED_NOT_CALIBRATABLE` and
`NOT_CALIBRATED` keep whole market families off the coupon. Before anyone
argues for admitting one, this asks the one question the settled rows can
answer: on live rows (``sofa_settled_row``, run_date a real date - cache
replay rows are left out) whose claimed probability was at least ``--min-p``,
how often did the row win, against what it claimed and against the devigged
price (``market_p``)?

Per family: rows, matches, mean ``p_central``, realised hit rate, their gap
with a 95% interval from resampling whole matches, mean ``market_p`` and the
hit rate on the priced subset, and the ROI per bet at ``offered_odds``.

Read it for what it is. ``p_central`` on these rows is the estimator of the
day they were settled (before 2026-10-05 07:15Z it blended in the price on
tennis), not the stats-only curve a coupon would print through; and every
row with p >= the floor is counted, not only what a coupon would have
taken. A family that over-claims here would over-claim on a coupon; one
that does not is not thereby admitted (that is a fit, out of sample by
date, and the operator's decision).

Measurement only: the DB is opened read-only.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_blocked_families.py \\
        [--min-p 0.70] [--from 2026-09-18] [--to 2026-10-04] [--json out.json]
"""

from __future__ import annotations

import argparse
import json
import random
import sqlite3
import sys
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa.config import SofaConfig  # noqa: E402

# The families refused on 2026-10-05 (09:50Z replay of CONFIDENCE), by code.
BLOCKED: dict[str, tuple[str, ...]] = {
    "TENNIS_SET_MARKET_NOT_ADMITTED": (
        "games_set1_total", "games_set2_total", "games_won_set1_for", "games_won_set2_for",
    ),
    "DERIVED_NOT_CALIBRATABLE": (
        "both_over_goals", "both_over_corners", "both_over_cards_points",
        "both_over_shots_on_target", "both_over_shots", "both_over_fouls", "both_over_offsides",
        "most_corners", "most_cards_points", "most_shots_on_target", "most_shots",
        "most_corners_1h", "most_corners_2h", "most_shots_1h", "most_shots_2h",
        "handicap_corners", "handicap_cards_points", "handicap_shots_on_target",
        "handicap_games", "most_games", "most_aces", "most_aces_set1", "most_aces_set2",
        "most_double_faults_set1", "most_double_faults_set2", "most_serve_points",
        "most_serve_points_set1", "most_serve_points_set2",
    ),
    "NOT_CALIBRATED": (
        "corners_1h_for", "corners_1h_total", "corners_2h_for", "corners_2h_total",
        "goals_1h_for", "goals_2h_for", "goals_2h_total", "shots_on_target_1h_total",
        "fouls_2h_for", "fouls_2h_total", "shots_2h_for", "shots_2h_total",
        "shots_on_target_2h_for", "shots_on_target_2h_total", "offsides_1h_for",
        "offsides_1h_total", "offsides_2h_for", "offsides_2h_total", "saves_1h_for",
        "saves_1h_total", "throw_ins_1h_for", "throw_ins_1h_total", "throw_ins_2h_for",
        "throw_ins_2h_total", "sets_total", "tiebreaks_total", "serve_points_for",
        "serve_points_total", "aces_set1_for", "aces_set2_for", "aces_set1_total",
        "aces_set2_total", "double_faults_set1_for", "double_faults_set2_for",
        "double_faults_set1_total", "double_faults_set2_total", "serve_points_set1_for",
        "serve_points_set2_for", "serve_points_set1_total", "serve_points_set2_total",
        "player_shots_on_target_for", "player_offsides_for",
    ),
}


@dataclass(frozen=True)
class Row:
    event: int
    p: float
    won: bool
    market_p: float | None
    odds: float | None


@dataclass(frozen=True)
class FamilyResult:
    market: str
    rows: int
    matches: int
    claimed: float
    realised: float
    gap: float
    gap_lo: float | None
    gap_hi: float | None
    priced_rows: int
    market_p: float | None
    priced_realised: float | None
    roi_rows: int
    roi: float | None


def _mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs)


def gap_interval(
    rows: Sequence[Row], *, n_boot: int = 1000, seed: int = 20261005
) -> tuple[float, float] | None:
    """95% interval of realised - claimed, resampling whole matches."""
    by_event: dict[int, list[Row]] = defaultdict(list)
    for r in rows:
        by_event[r.event].append(r)
    events = list(by_event)
    if len(events) < 2:
        return None
    rng = random.Random(seed)
    gaps: list[float] = []
    for _ in range(n_boot):
        won = claimed = n = 0.0
        for e in rng.choices(events, k=len(events)):
            for r in by_event[e]:
                won += r.won
                claimed += r.p
                n += 1
        gaps.append((won - claimed) / n)
    gaps.sort()
    return gaps[int(0.025 * n_boot)], gaps[int(0.975 * n_boot) - 1]


def summarise(market: str, rows: Sequence[Row], *, n_boot: int = 1000) -> FamilyResult:
    claimed = _mean([r.p for r in rows])
    realised = _mean([float(r.won) for r in rows])
    ci = gap_interval(rows, n_boot=n_boot)
    priced = [r for r in rows if r.market_p is not None]
    with_odds = [r for r in rows if r.odds is not None]
    return FamilyResult(
        market=market,
        rows=len(rows),
        matches=len({r.event for r in rows}),
        claimed=claimed,
        realised=realised,
        gap=realised - claimed,
        gap_lo=ci[0] if ci else None,
        gap_hi=ci[1] if ci else None,
        priced_rows=len(priced),
        market_p=_mean([float(r.market_p) for r in priced if r.market_p is not None]) if priced else None,
        priced_realised=_mean([float(r.won) for r in priced]) if priced else None,
        roi_rows=len(with_odds),
        roi=_mean([(float(r.odds) - 1.0) if r.won else -1.0 for r in with_odds if r.odds is not None])
        if with_odds else None,
    )


def load_rows(
    conn: sqlite3.Connection, markets: Iterable[str], *, min_p: float, date_from: str, date_to: str
) -> dict[str, list[Row]]:
    wanted = list(markets)
    marks = ",".join("?" for _ in wanted)
    sql = (
        "SELECT market, sofascore_event_id, p_central, outcome, market_p, offered_odds "
        "FROM sofa_settled_row "
        f"WHERE market IN ({marks}) AND p_central >= ? "
        "AND run_date >= ? AND run_date <= ? AND run_date NOT LIKE 'cache%'"
    )
    out: dict[str, list[Row]] = defaultdict(list)
    for market, event, p, outcome, mp, odds in conn.execute(sql, (*wanted, min_p, date_from, date_to)):
        out[str(market)].append(Row(int(event), float(p), outcome == "WIN",
                                    None if mp is None else float(mp),
                                    None if odds is None else float(odds)))
    return out


def _fmt(x: float | None, nd: int = 3) -> str:
    return "-" if x is None else f"{x:.{nd}f}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--min-p", type=float, default=0.70)
    ap.add_argument("--from", dest="date_from", default="2026-09-18")
    ap.add_argument("--to", dest="date_to", default="2026-10-04")
    ap.add_argument("--db", default=None)
    ap.add_argument("--json", default=None)
    ap.add_argument("--n-boot", type=int, default=1000)
    args = ap.parse_args(argv)

    db = args.db or SofaConfig.from_env().db_path
    if not Path(db).exists():
        print(f"no database at {db}", file=sys.stderr)
        return 2
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    all_markets = [m for ms in BLOCKED.values() for m in ms]
    rows = load_rows(conn, all_markets, min_p=args.min_p, date_from=args.date_from, date_to=args.date_to)

    out: dict[str, Any] = {"min_p": args.min_p, "from": args.date_from, "to": args.date_to, "codes": {}}
    for code, markets in BLOCKED.items():
        print(f"\n## {code} (p_central >= {args.min_p}, live rows {args.date_from}..{args.date_to})\n")
        print("| rynek | wiersze | mecze | pewność | realizacja | różnica [95% po meczach] | "
              "cena (market_p) | realizacja wycenionych | ROI przy kursie (n) |")
        print("|---|---|---|---|---|---|---|---|---|")
        res = []
        for m in markets:
            if not rows.get(m):
                print(f"| {m} | 0 | 0 | - | - | - | - | - | - |")
                continue
            r = summarise(m, rows[m], n_boot=args.n_boot)
            res.append(r.__dict__)
            ci = f"[{_fmt(r.gap_lo)}; {_fmt(r.gap_hi)}]" if r.gap_lo is not None else ""
            roi = f"{r.roi * 100:+.1f}% ({r.roi_rows})" if r.roi is not None else "-"
            print(f"| {m} | {r.rows} | {r.matches} | {_fmt(r.claimed)} | {_fmt(r.realised)} | "
                  f"{r.gap:+.3f} {ci} | {_fmt(r.market_p)} | {_fmt(r.priced_realised)} | {roi} |")
        out["codes"][code] = res
    if args.json:
        Path(args.json).write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
