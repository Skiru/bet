#!/usr/bin/env python3
"""Does a model far above its own sample's hit rate realise worse? Measured.

2026-10-04, SC Farense - Chaves goals_total UNDER 3.5: model 0.786, the
sample the row was priced from held the line 14 times in 20 (0.70), and the
verifier flagged the 8.6 pp gap in prose. Nothing in code compares the two
(the football rating and the league prior move the centre away from the raw
sample; DISAGREES_WITH_PRICE reads `sample_frequency`, which football rows
never carry). Before a gate is written, this asks whether the gap predicts
anything:

For every settled live row (sofa_settled_row, run_date in range, priced:
offered_odds and market_p set, no player market) the row's own sample is
rebuilt from that day's 03_samples.json exactly as CONFIDENCE reads it (a
``*_for`` row: its side; a total: side_a + side_b + h2h, one match once), the
hit rate h = (observations the row would have won) / n, and gap = p_central
- h. Rows are binned by gap; per bin: rows, matches, mean p_central, mean
market_p, realised hit rate, realised - market_p, ROI per bet at
offered_odds, a 95% interval from resampling whole matches and the two
event-id halves apart. ``--min-p`` keeps only rows a coupon could print.

Measurement only: the DB is opened read-only and nothing the pipeline reads
is written.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_own_sample_gap.py \\
        --from 2026-09-24 --to 2026-10-03 [--min-p 0.65] [--sport football]
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from collections.abc import Sequence
from datetime import date, timedelta
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np  # noqa: E402

from bet.sofa.config import SofaConfig  # noqa: E402
from bet.sofa.contracts import Fixture  # noqa: E402
from bet.sofa.players import is_player_metric  # noqa: E402
from scripts.sofa.run_sheet import determine_side  # noqa: E402

BINS: tuple[tuple[float, float], ...] = (
    (-1.0, -0.05),
    (-0.05, 0.0),
    (0.0, 0.05),
    (0.05, 0.10),
    (0.10, 0.15),
    (0.15, 1.0),
)


def wins(value: float, line: float, direction: str) -> bool:
    return value > line if direction == "OVER" else value < line


def own_sample(
    fixture_samples: dict[str, Any], fixture: Fixture | None, market: str, subject: str
) -> list[float]:
    """The values CONFIDENCE reads for the row (run_confidence.side_observations)."""
    mv = (fixture_samples.get("metrics") or {}).get(market)
    if not mv:
        return []
    if subject:
        side = determine_side(subject, fixture) if fixture else None
        obs = list(mv.get(side) or []) if side else []
    else:
        obs, seen = [], set()
        for key in ("side_a", "side_b", "h2h"):
            for o in mv.get(key) or []:
                if o["sofascore_event_id"] in seen:
                    continue
                seen.add(o["sofascore_event_id"])
                obs.append(o)
    return [float(o["value"]) for o in obs if o.get("value") is not None]


def gap_bin(gap: float) -> int:
    for i, (lo, hi) in enumerate(BINS):
        if lo <= gap < hi:
            return i
    return len(BINS) - 1


def cluster_interval(
    values: np.ndarray, groups: np.ndarray, rng: np.random.Generator, draws: int = 1000
) -> tuple[float, float]:
    uniq, inv = np.unique(groups, return_inverse=True)
    sums = np.bincount(inv, weights=values)
    counts = np.bincount(inv)
    out = np.empty(draws)
    for i in range(draws):
        pick = rng.integers(0, len(uniq), size=len(uniq))
        out[i] = sums[pick].sum() / counts[pick].sum()
    return float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5))


def collect(
    db: Path, runs_dir: Path, start: date, end: date, sport: str, min_p: float
) -> list[dict[str, Any]]:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    rows: list[dict[str, Any]] = []
    day = start
    while day <= end:
        d = day.isoformat()
        day += timedelta(days=1)
        run = runs_dir / d
        samples_path, fixtures_path = run / "03_samples.json", run / "02_fixtures.json"
        if not samples_path.exists() or not fixtures_path.exists():
            continue
        samples = {
            int(x["sofascore_event_id"]): x
            for x in json.loads(samples_path.read_text(encoding="utf-8"))
        }
        fixtures: dict[int, Fixture] = {}
        for raw in json.loads(fixtures_path.read_text(encoding="utf-8")):
            try:
                fx = Fixture.model_validate_json(json.dumps(raw))
            except ValueError:
                continue
            fixtures[fx.sofascore_event_id] = fx
        for (eid, market, subject, line, direction, p, mp, odds, outcome,
             sp) in con.execute(
            "SELECT sofascore_event_id, market, subject, line, direction, "
            "p_central, market_p, offered_odds, outcome, sport "
            "FROM sofa_settled_row WHERE run_date = ? AND offered_odds IS NOT NULL "
            "AND market_p IS NOT NULL AND outcome IN ('WIN', 'LOSS')",
            (d,),
        ):
            if sport != "all" and sp != sport:
                continue
            if p < min_p or is_player_metric(market):
                continue
            fs = samples.get(int(eid))
            if fs is None:
                continue
            values = own_sample(fs, fixtures.get(int(eid)), market, subject or "")
            if len(values) < 5:
                continue
            hit_rate = sum(wins(v, line, direction) for v in values) / len(values)
            rows.append({
                "date": d, "eid": int(eid), "market": market, "p": float(p),
                "direction": direction,
                "market_p": float(mp), "odds": float(odds),
                "won": outcome == "WIN", "own": hit_rate, "n": len(values),
                "gap": float(p) - hit_rate,
            })
    return rows


def report(rows: list[dict[str, Any]], label: str) -> list[str]:
    rng = np.random.default_rng(20261004)
    matches = len({r["eid"] for r in rows})
    out = [f"### {label}: {len(rows)} rows, {matches} matches", "",
           "| p - own hit rate | rows | matches | p | own | market_p | realised | "
           "realised - market [95%] | ROI [95%] | ROI even | ROI odd |",
           "|---|---|---|---|---|---|---|---|---|---|---|"]
    by: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by[gap_bin(r["gap"])].append(r)
    for i, (lo, hi) in enumerate(BINS):
        group = by.get(i) or []
        if not group:
            continue
        won = np.asarray([r["won"] for r in group], dtype=float)
        mp = np.asarray([r["market_p"] for r in group])
        roi = np.asarray([(r["odds"] - 1.0) if r["won"] else -1.0 for r in group])
        eids = np.asarray([r["eid"] for r in group])
        edge_lo, edge_hi = cluster_interval(won - mp, eids, rng)
        roi_lo, roi_hi = cluster_interval(roi, eids, rng)
        even, odd = eids % 2 == 0, eids % 2 == 1
        out.append(
            f"| [{lo:+.2f}, {hi:+.2f}) | {len(group)} | {len(set(eids.tolist()))} | "
            f"{np.mean([r['p'] for r in group]):.3f} | "
            f"{np.mean([r['own'] for r in group]):.3f} | {mp.mean():.3f} | "
            f"{won.mean():.3f} | {(won - mp).mean():+.3f} "
            f"[{edge_lo:+.3f}; {edge_hi:+.3f}] | {roi.mean():+.1%} "
            f"[{roi_lo:+.1%}; {roi_hi:+.1%}] | "
            f"{roi[even].mean() if even.any() else float('nan'):+.1%} | "
            f"{roi[odd].mean() if odd.any() else float('nan'):+.1%} |"
        )
    out.append("")
    return out


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--from", dest="start", required=True)
    ap.add_argument("--to", dest="end", required=True)
    ap.add_argument("--sport", default="football",
                    choices=("football", "tennis", "all"))
    ap.add_argument("--min-p", type=float, default=0.65)
    ap.add_argument("--db", type=Path, default=Path("data/sofa.db"))
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)
    if not args.db.exists():
        print(f"no DB at {args.db}", file=sys.stderr)
        return 2
    runs_dir = Path(SofaConfig.from_env().runs_dir)
    rows = collect(args.db, runs_dir, date.fromisoformat(args.start),
                   date.fromisoformat(args.end), args.sport, args.min_p)
    if not rows:
        print("no settled priced row with a sample in range", file=sys.stderr)
        return 1
    text = [f"# Model vs its own sample, {args.start}..{args.end}, "
            f"{args.sport}, p_central >= {args.min_p}", ""]
    text += report(rows, "all rows")
    for direction in ("OVER", "UNDER"):
        subset = [r for r in rows if r["direction"] == direction]
        if subset:
            text += report(subset, direction)
    body = "\n".join(text)
    print(body)
    if args.out:
        args.out.write_text(body + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
