#!/usr/bin/env python3
"""Measure the rating's link rule: either side's league vs a shared league.

football_rating.RatingBook._linked linked a pair when both sides played
LINK_MIN_MATCHES in a competition that was the league of EITHER side, so a
promoted side was LINKED three games into its new league and read its old
league's ratios 1:1 (2026-10-07). epochs.link_shared_league asks for a league
both domains share. Two books are replayed side by side over the same
history, one per rule, and every match from --from to --cut is forecast one
step ahead by both before either learns it:

  * squared error of each side's count (goals_for, corners_for for football;
    the regulation score for hockey / basketball / volleyball's metric),
    on every rated match and on the matches the two rules link differently;
  * the difference new - old with a 95% bootstrap interval over matches
    (negative = the shared-league rule is better);
  * the link status counts under each rule on the changed matches.

`--settled-from/--settled-to` (measured sports) also scores the score model
on Superbet's settled lines (sport_confidence.settled_shadow_rows - the rows
the confidence curves are fitted on): Brier per rule, on the rows whose
probability moved.

An analysis tool: it writes nothing the pipeline reads.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_link_rule.py \\
        --sport football --from 2026-07-01 --cut 2026-10-07
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from bet.sofa import epochs, shadow
from bet.sofa import football_rating as fr
from bet.sofa import sport_confidence as scf
from bet.sofa.config import SofaConfig
from bet.sofa.score_model import _metrics, _rated_values, load_events

FOOTBALL_METRICS = ("goals_for", "corners_for")


def _ts(day: str) -> int:
    return int(datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=UTC).timestamp())


def _forecast(book: fr.RatingBook, r: fr.FootballResult, metric: str
              ) -> tuple[str, tuple[float, float] | None]:
    status, lf = book.link(r.home_id, r.away_id, metric)
    return status, book.expected(r.competition_id, r.home_id, r.away_id, metric,
                                 lf, cross=status != fr.LINKED)


def walk(history: Iterable[fr.FootballResult], metrics: Sequence[str],
         start: int, cut: int) -> dict[str, list[dict[str, Any]]]:
    """metric -> one record per rated match in [start, cut): both rules'
    squared errors, whether they linked it differently, their statuses."""
    old = fr.RatingBook(shared_league_link=False)
    new = fr.RatingBook(shared_league_link=True)
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in history:
        if r.ts >= cut:
            break
        if r.ts >= start:
            changed = (old.linked(r.home_id, r.away_id)
                       != new.linked(r.home_id, r.away_id))
            for m in metrics:
                if m not in r.values or any(
                    b.team_matches(t, m) < fr.MIN_TEAM_MATCHES
                    for b in (old, new) for t in (r.home_id, r.away_id)
                ):
                    continue
                so, eo = _forecast(old, r, m)
                sn, en = _forecast(new, r, m)
                if eo is None or en is None:
                    continue
                vh, va = r.values[m]
                out[m].append({
                    "match": r.event_id, "changed": changed,
                    "old": (eo[0] - vh) ** 2 + (eo[1] - va) ** 2,
                    "new": (en[0] - vh) ** 2 + (en[1] - va) ** 2,
                    "status_old": so, "status_new": sn})
        old.update(r)
        new.update(r)
    return out


def bootstrap_diff(rows: Sequence[dict[str, Any]], a: str, b: str,
                   n_boot: int = 2000, seed: int = 7) -> tuple[float, float, float]:
    """Mean of b - a per match and its 95% interval, resampling matches."""
    by_match: dict[Any, list[float]] = defaultdict(list)
    for row in rows:
        by_match[row["match"]].append(row[b] - row[a])
    keys = list(by_match)
    if not keys:
        return 0.0, 0.0, 0.0
    sums = [(sum(by_match[k]), len(by_match[k])) for k in keys]
    point = sum(s for s, _ in sums) / sum(n for _, n in sums)
    rng = random.Random(seed)
    boots = []
    for _ in range(n_boot):
        pick = [sums[rng.randrange(len(sums))] for _ in sums]
        boots.append(sum(s for s, _ in pick) / sum(n for _, n in pick))
    boots.sort()
    return point, boots[int(0.025 * n_boot)], boots[int(0.975 * n_boot) - 1]


def _mean(pop: Sequence[dict[str, Any]], key: str, per: int = 1) -> float | None:
    return round(sum(r[key] for r in pop) / len(pop) / per, 5) if pop else None


def summarise(records: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for m, rows in sorted(records.items()):
        changed = [r for r in rows if r["changed"]]
        cell: dict[str, Any] = {}
        for name, pop in (("all", rows), ("changed", changed)):
            n = len(pop)
            d, lo, hi = bootstrap_diff(pop, "old", "new")
            # per side: each record holds both sides' squared errors
            cell[name] = {
                "n": n, "matches": len({r["match"] for r in pop}),
                "mse_old": _mean(pop, "old", 2), "mse_new": _mean(pop, "new", 2),
                "diff_new_minus_old": [round(x / 2, 5) for x in (d, lo, hi)],
            }
        cell["changed"]["status"] = {
            "old": dict(Counter(r["status_old"] for r in changed)),
            "new": dict(Counter(r["status_new"] for r in changed))}
        out[m] = cell
    return out


def _sport_history(db_path: str, sport_key: str
                   ) -> tuple[Any, list[Any], dict[int, Any]]:
    sport = shadow.SPORTS[sport_key]  # type: ignore[index]
    events = load_events(db_path, sport)
    return sport, scf.parse_history(events, sport), events


def settled_brier(runs_dir: str, sport: Any, history: list[Any],
                  events: dict[int, Any], days: list[str], n_sims: int
                  ) -> dict[str, Any]:
    """Brier of the score model on Superbet's settled lines, per rule."""
    saved = epochs.LINK_SHARED_LEAGUE_FROM_UTC
    rows: dict[bool, list[dict[str, Any]]] = {}
    try:
        for rule, moment in ((False, None), (True, datetime(2000, 1, 1, tzinfo=UTC))):
            epochs.LINK_SHARED_LEAGUE_FROM_UTC = moment
            rows[rule] = scf.settled_shadow_rows(runs_dir, sport, days, events,
                                                 history, n_sims)
    finally:
        epochs.LINK_SHARED_LEAGUE_FROM_UTC = saved
    key = ("game", "market_id", "period", "subject", "line", "side")
    new_by = {tuple(r[k] for k in key): r for r in rows[True]}
    paired = []
    for r in rows[False]:
        n = new_by.get(tuple(r[k] for k in key))
        if n is None:
            continue
        paired.append({"match": r["game"], "changed": abs(n["p"] - r["p"]) > 1e-9,
                       "old": (r["p"] - r["y"]) ** 2, "new": (n["p"] - r["y"]) ** 2})
    out: dict[str, Any] = {"rows_old": len(rows[False]), "rows_new": len(rows[True])}
    moved = [p for p in paired if p["changed"]]
    for name, pop in (("all", paired), ("changed", moved)):
        d, lo, hi = bootstrap_diff(pop, "old", "new")
        out[name] = {"n": len(pop), "games": len({p["match"] for p in pop}),
                     "brier_old": _mean(pop, "old"), "brier_new": _mean(pop, "new"),
                     "diff_new_minus_old": [round(x, 5) for x in (d, lo, hi)]}
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--sport", required=True,
                    choices=("football", "hockey", "basketball", "volleyball"))
    ap.add_argument("--from", dest="start", required=True)
    ap.add_argument("--cut", required=True)
    ap.add_argument("--settled-from")
    ap.add_argument("--settled-to")
    ap.add_argument("--sims", type=int, default=2000)
    args = ap.parse_args()
    config = SofaConfig.from_env()
    start, cut = _ts(args.start), _ts(args.cut)
    result: dict[str, Any] = {"sport": args.sport, "window": [args.start, args.cut]}
    if args.sport == "football":
        history = fr.load_history(config.db_path, Path(config.db_path).parent / "cache")
        result["metrics"] = summarise(walk(history, FOOTBALL_METRICS, start, cut))
    else:
        sport, games, events = _sport_history(config.db_path, args.sport)
        ratings = [_rated_values(g.rating, sport) for g in games]
        result["metrics"] = summarise(walk(ratings, _metrics(sport)[:1], start, cut))
        if args.settled_from and args.settled_to:
            d0 = datetime.strptime(args.settled_from, "%Y-%m-%d")
            d1 = datetime.strptime(args.settled_to, "%Y-%m-%d")
            days = [(d0 + timedelta(days=i)).strftime("%Y-%m-%d")
                    for i in range((d1 - d0).days + 1)]
            result["settled_lines"] = settled_brier(
                config.runs_dir, sport, [g for g in games], events, days, args.sims)
    print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
