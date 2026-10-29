#!/usr/bin/env python3
"""How much the football replay moves without results awarded at the table
(epochs.AWARDED_EXCLUDED, calibrate_from_cache --awarded-excluded).

The installed football curves were fitted on a replay that kept Sofascore's
`isAwarded` results (forfeits, walkovers: an unplayed 3-0 / 0-0 off the
listing). Before a refit is spent on it alone, its scale:

  * awarded football results in the parsed history (load_history);
  * the matches of --from .. --cut whose side has an awarded result among
    its previous SAMPLE_N results (a sample that changes) - all, and the
    share;
  * the rating's goals_for one step ahead with and without them: Poisson
    log-loss per side (RatingBook.expected through link(), as SHEET reads
    it) on the matches neither awarded, without minus with (negative =
    better), 95% interval from resampling matches; all and the matches with
    an awarded result in a side's last SAMPLE_N.

Read only: the history comes from football_rating.load_history on --db-path
(a COPY - the pickle is written next to it); writes only --json-out.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_awarded_scale.py \\
        --db-path data/refit_2026-10-30/sofa.db --json-out <f>
"""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict, deque
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from bet.sofa import football_rating as fr
from bet.sofa.cup_strength import load as load_cup

METRIC = "goals_for"
SAMPLE_N = 10


def _ts(day: str) -> int:
    return int(datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=UTC).timestamp())


def _nll(y: float, mu: float) -> float:
    mu = max(mu, 1e-9)
    return mu - y * math.log(mu) + math.lgamma(y + 1)


def _book() -> fr.RatingBook:
    cup = load_cup()
    book = fr.RatingBook(shared_league_link=True)
    book.cup_competitions = cup.competitions
    book.cup_eta = dict(cup.eta)
    return book


def _boot(v: list[float], n_boot: int = 2000, seed: int = 7) -> list[float] | None:
    if not v:
        return None
    a = np.array(v, dtype=float)
    rng = np.random.default_rng(seed)
    means = a[rng.integers(0, len(a), size=(n_boot, len(a)))].mean(axis=1)
    return [round(float(a.mean()), 6), round(float(np.quantile(means, 0.025)), 6),
            round(float(np.quantile(means, 0.975)), 6), len(a)]


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db-path", required=True)
    ap.add_argument("--from", dest="from_day", default="2025-10-01")
    ap.add_argument("--cut", default="2026-10-29")
    ap.add_argument("--json-out", required=True)
    args = ap.parse_args(argv)
    db = Path(args.db_path)
    history = [replace(r, values={METRIC: r.values[METRIC]})
               for r in fr.load_history(db, db.parent / "cache")
               if METRIC in r.values]
    start, cut = _ts(args.from_day), _ts(args.cut)
    recent: dict[int, deque[bool]] = defaultdict(lambda: deque(maxlen=SAMPLE_N))
    with_book, without_book = _book(), _book()
    touched: set[int] = set()
    scored = 0
    d_all: list[float] = []
    d_touched: list[float] = []
    for r in history:
        if r.ts >= cut:
            break
        if r.ts >= start and not r.awarded:
            scored += 1
            hit = any(recent[r.home_id]) or any(recent[r.away_id])
            if hit:
                touched.add(r.event_id)
            if not (r.women or r.home_reserve or r.away_reserve) and all(
                    b.team_matches(t, METRIC) >= fr.MIN_TEAM_MATCHES
                    for b in (with_book, without_book)
                    for t in (r.home_id, r.away_id)):
                vh, va = r.values[METRIC]
                nll: list[float] = []
                for b in (with_book, without_book):
                    status, lf = b.link(r.home_id, r.away_id, METRIC,
                                        r.competition_id)
                    exp = (None if status == fr.UNLINKED else b.expected(
                        r.competition_id, r.home_id, r.away_id, METRIC, lf,
                        cross=status != fr.LINKED))
                    if exp is None:
                        break
                    nll.append((_nll(vh, exp[0]) + _nll(va, exp[1])) / 2)
                if len(nll) == 2:
                    d_all.append(nll[1] - nll[0])
                    if hit:
                        d_touched.append(nll[1] - nll[0])
        for team in (r.home_id, r.away_id):
            recent[team].append(r.awarded)
        with_book.update(r)
        if not r.awarded:
            without_book.update(r)
    awarded = sum(1 for r in history if r.awarded)
    report: dict[str, Any] = {
        "db_path": str(db), "from": args.from_day, "cut": args.cut,
        "history_results": len(history), "awarded_results": awarded,
        "awarded_in_window": sum(1 for r in history
                                 if r.awarded and start <= r.ts < cut),
        "matches_scored": scored,
        "matches_with_awarded_in_last_10": len(touched),
        "share": round(len(touched) / scored, 5) if scored else None,
        "rating_goals_for_nll_without_minus_with": {
            "all": _boot(d_all), "touched": _boot(d_touched)},
    }
    Path(args.json_out).write_text(json.dumps(report, indent=1))
    print(json.dumps(report, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
