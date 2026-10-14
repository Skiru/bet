#!/usr/bin/env python3
"""Measure the measured sports' derived markets on the results history.

epochs.SPORT_DERIVED_MARKETS_FROM_UTC (shadow.DERIVED_MARKETS): hockey's and
basketball's double chance (game, period / half / quarter; regulation time)
and volleyball's "<team> wygra seta", "<team> wygra dokładnie N set(y)" and
"Dokładna liczba setów" - every one a function of a score the score model
already simulates. Before any of them is read live, this asks the question
out of sample: walk forward through the history (sport_confidence.
walk_forward_rows, the replay a sport curve is fitted on - a model built only
from games before each one, rebuilt every REBUILD_DAYS), score each game on
the derived markets' own lines (sport_confidence.synthetic_lines: the three
double-chance selections, YES / NO at N = 1 and 2 sets, SETS=3/4/5), and
report per key:

  * log-loss of the model's p against the BASE RATE of the same line (its
    realised rate over the history before the window - home = team1, as in
    the rows), the difference with a 95% interval from a bootstrap over
    GAMES (one game's lines are not independent);
  * calibration by sport_confidence.EDGES bucket: n, mean p, realised, the
    Wilson lower bound (what a curve would read);
  * how many forecasts are >= 0.70 (the coupon's floor) and what they
    realised (with the Wilson lower bound).

No price is read and nothing the pipeline reads is written. Read-only on the
database (load_events opens it mode=ro).

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_sport_derived.py \\
        --sport all --start 2025-10-14 --end 2026-10-14 \\
        --json-out f.json --md-out f.md
"""

from __future__ import annotations

import argparse
import json
import math
import pickle
import random
import sys
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _path in (str(_REPO_ROOT), str(_REPO_ROOT / "src")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from bet.sofa import sport_confidence as scf  # noqa: E402
from bet.sofa.config import SofaConfig  # noqa: E402
from bet.sofa.score_model import load_events  # noqa: E402
from bet.sofa.shadow import SPORTS, ShadowSport, actual_value, grade  # noqa: E402

BOOTSTRAP = 2000
FLOOR = scf.PRINTABLE_FROM
BASE_GAMES = 20000  # the newest games before the window the base rate reads
EPS = 1e-6


def _ts(day: str) -> int:
    return int(datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=UTC).timestamp())


def line_id(row: Mapping[str, Any]) -> tuple[str, int, str, Any, str]:
    """A base rate's cell: the family, period, subject, line and side."""
    return (str(row["family"]), int(row.get("period") or 0),
            str(row.get("subject") or ""), row.get("line"), str(row["side"]))


def base_rates(history: Sequence[scf.HistoryGame], sport: ShadowSport,
               before_ts: int) -> dict[tuple[str, int, str, Any, str], float]:
    """Each derived line's realised rate over the newest BASE_GAMES graded
    games before `before_ts` (home = team1, the rows' orientation)."""
    games = [g for g in history if g.rating.ts < before_ts and g.result is not None]
    won: dict[tuple[str, int, str, Any, str], list[int]] = defaultdict(lambda: [0, 0])
    for g in games[-BASE_GAMES:]:
        assert g.result is not None
        for mid in scf.DERIVED_HISTORY_MARKETS[sport.key]:
            for period in scf.market_periods(sport, mid):
                for ln in scf.synthetic_lines(sport, mid, [], period):
                    actual = actual_value(ln, g.result, sport)
                    if actual is None:
                        continue
                    out = grade(ln, actual)
                    if out == "VOID":
                        continue
                    cell = won[line_id(ln.as_dict())]
                    cell[0] += out == "WIN"
                    cell[1] += 1
    return {k: v[0] / v[1] for k, v in won.items() if v[1]}


def _ll(p: float, y: int) -> float:
    p = min(max(p, EPS), 1 - EPS)
    return -math.log(p if y else 1 - p)


def _boot(per_game: Mapping[str, list[float]], rng: random.Random
          ) -> tuple[float, float, float]:
    games = list(per_game)
    if not games:
        return 0.0, 0.0, 0.0
    total = sum(sum(v) for v in per_game.values())
    n = sum(len(v) for v in per_game.values())
    stats = []
    for _ in range(BOOTSTRAP):
        s = c = 0.0
        for _ in games:
            v = per_game[games[rng.randrange(len(games))]]
            s += sum(v)
            c += len(v)
        stats.append(s / c if c else 0.0)
    stats.sort()
    return total / n, stats[int(0.025 * BOOTSTRAP)], stats[int(0.975 * BOOTSTRAP) - 1]


def summarise(rows: Sequence[Mapping[str, Any]], base: Mapping[Any, float],
              seed: int = 7) -> dict[str, Any]:
    """Per curve key: n, games, log-loss model / base and their difference
    (game bootstrap), calibration by bucket, the share >= FLOOR."""
    rng = random.Random(seed)
    by_key: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for r in rows:
        if line_id(r) in base:
            by_key[str(r["key"])].append(r)
    out: dict[str, Any] = {}
    for key in sorted(by_key):
        rs = by_key[key]
        diff: dict[str, list[float]] = defaultdict(list)
        ll_m = ll_b = 0.0
        buckets: dict[int, list[int | float]] = defaultdict(lambda: [0, 0, 0.0])
        hi_n = hi_k = 0
        for r in rs:
            p, y = float(r["p"]), int(r["y"])
            pb = base[line_id(r)]
            m, b = _ll(p, y), _ll(pb, y)
            ll_m += m
            ll_b += b
            diff[str(r["game"])].append(m - b)
            cell = buckets[scf.bucket_of(p)]
            cell[0] += 1
            cell[1] += y
            cell[2] += p
            if p >= FLOOR:
                hi_n += 1
                hi_k += y
        mean, lo, hi = _boot(diff, rng)
        n = len(rs)
        out[key] = {
            "n": n, "games": len(diff),
            "logloss_model": round(ll_m / n, 5), "logloss_base": round(ll_b / n, 5),
            "diff": round(mean, 5), "diff_lo": round(lo, 5), "diff_hi": round(hi, 5),
            "realised": round(sum(int(r["y"]) for r in rs) / n, 4),
            "mean_p": round(sum(float(r["p"]) for r in rs) / n, 4),
            "printable_n": hi_n, "printable_share": round(hi_n / n, 4),
            "printable_realised": round(hi_k / hi_n, 4) if hi_n else None,
            "printable_wilson_lo": (round(scf.wilson_lo(hi_k, hi_n), 4)
                                    if hi_n else None),
            "buckets": {
                scf.bucket_label(b): {
                    "n": int(c[0]), "mean_p": round(float(c[2]) / c[0], 4),
                    "realised": round(int(c[1]) / c[0], 4),
                    "wilson_lo": round(scf.wilson_lo(int(c[1]), int(c[0])), 4)}
                for b, c in sorted(buckets.items())},
        }
    return out


def _events(db_path: str, sport: ShadowSport, cache_dir: str | None
            ) -> dict[int, Any]:
    if cache_dir:
        path = Path(cache_dir) / f"{sport.key}.pkl"
        if path.exists():
            data: dict[int, Any] = pickle.loads(path.read_bytes())
            return data
        events = load_events(db_path, sport)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(pickle.dumps(events))
        return events
    return load_events(db_path, sport)


def measure_sport(sport: ShadowSport, history: Sequence[scf.HistoryGame],
                  start: str, end: str, sims: int, max_games: int
                  ) -> dict[str, Any]:
    """The live estimator's switches as of the window's end (basketball
    freshness on, the league-rate rule on, no overtime / pace / set length -
    epochs as of 2026-10-14)."""
    start_ts, end_ts = _ts(start), _ts(end)
    rows = scf.walk_forward_rows(
        history, sport, start_ts, end_ts, sims, max_games, "derived_history",
        freshness=sport.key == "basketball", strict_league_rate=True,
        markets=scf.DERIVED_HISTORY_MARKETS[sport.key])
    base = base_rates(history, sport, start_ts)
    return {"window": [start, end], "rows": len(rows),
            "games": len({r["game"] for r in rows}), "keys": summarise(rows, base)}


def markdown(report: Mapping[str, Any]) -> str:
    lines = ["| sport | klucz | n | mecze | LL model | LL baza | różnica [95%] "
             "| p>=0,70: n (udział) | zrealizowane (Wilson) |",
             "|---|---|---|---|---|---|---|---|---|"]
    for sport, entry in report["sports"].items():
        for key, k in entry["keys"].items():
            hi = (f"{k['printable_realised']:.3f} ({k['printable_wilson_lo']:.3f})"
                  if k["printable_n"] else "-")
            lines.append(
                f"| {sport} | `{key}` | {k['n']} | {k['games']} | "
                f"{k['logloss_model']:.4f} | {k['logloss_base']:.4f} | "
                f"{k['diff']:+.4f} [{k['diff_lo']:+.4f}, {k['diff_hi']:+.4f}] | "
                f"{k['printable_n']} ({k['printable_share']:.1%}) | {hi} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sport", choices=[*SPORTS, "all"], default="all")
    ap.add_argument("--start", required=True, help="window start, YYYY-MM-DD")
    ap.add_argument("--end", required=True, help="window end (exclusive)")
    ap.add_argument("--sims", type=int, default=1000)
    ap.add_argument("--max-games", type=int, default=4000)
    ap.add_argument("--db-path", default=None)
    ap.add_argument("--events-cache", default=None,
                    help="a directory of <sport>.pkl event dumps (read / written)")
    ap.add_argument("--json-out", default=None)
    ap.add_argument("--md-out", default=None)
    args = ap.parse_args(argv)
    db_path = args.db_path or SofaConfig.from_env().db_path
    sports = list(SPORTS) if args.sport == "all" else [args.sport]
    report: dict[str, Any] = {"start": args.start, "end": args.end,
                              "sims": args.sims, "max_games": args.max_games,
                              "sports": {}}
    end_ts = _ts(args.end)
    for key in sports:
        sport = SPORTS[key]
        print(f"{key}: loading history", file=sys.stderr, flush=True)
        history = [g for g in scf.parse_history(
            _events(db_path, sport, args.events_cache), sport)
            if g.rating.ts < end_ts]
        print(f"{key}: {len(history)} games, replaying", file=sys.stderr, flush=True)
        report["sports"][key] = measure_sport(
            sport, history, args.start, args.end, args.sims, args.max_games)
        print(f"{key}: {report['sports'][key]['games']} games scored",
              file=sys.stderr, flush=True)
    text = json.dumps(report, indent=2, ensure_ascii=False)
    if args.json_out:
        Path(args.json_out).write_text(text + "\n", encoding="utf-8")
    if args.md_out:
        Path(args.md_out).write_text(markdown(report), encoding="utf-8")
    print(markdown(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
