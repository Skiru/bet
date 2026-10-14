#!/usr/bin/env python3
"""Can a footballer's shot-detail counts (bet.sofa.shot_detail: outside the
box, header, left / right foot; all and on target) be forecast well enough
to carry a curve? Read-only evidence, walk-forward on the cached history.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_shot_detail.py \\
        [--min-prior 5] [--window 10] [--md-out f] [--json-out f]

Population: every STARTER (lineups `substitute` false) of every football
match with a cached shotmap (sofa_event_extra) and per-player lineups, in
kickoff order (sofa_listing_event.start_ts). A start is forecast only from
the same player's earlier starts (the last --window, at least --min-prior)
and a position pool built from earlier starts only - nothing after the
kickoff is read. Forecast: Poisson with the player's mean shrunk to his
position's running mean with K pseudo-starts, K in {0, 2, 5, 10}.

Reports per metric and line (0.5 / 1.5 / 2.5): n, log-loss of each K against
the position pool alone (the skill a player term adds), and the calibration
of the best K by forecast bucket - realised, its Wilson lower bound, and the
player-matches in it. Superbet's prices are NOT in this measurement: whether
a printed line beats its price is a separate question for the recorded
prices (bet.sofa.unmapped_prices) once they settle. Nothing is written but
--md-out / --json-out. Exit 0, 2 on a crash.
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import shot_detail as sd  # noqa: E402
from bet.sofa.config import SofaConfig  # noqa: E402

LINES = (0.5, 1.5, 2.5)
KS = (0, 2, 5, 10)
BUCKETS = (0.0, 0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.75, 0.8, 0.85, 0.9, 1.01)


def poisson_over(mean: float, line: float) -> float:
    k = int(line)
    return 1.0 - sum(math.exp(-mean) * mean ** j / math.factorial(j)
                     for j in range(k + 1))


def wilson_lo(hits: int, n: int, z: float = 1.96) -> float:
    if n == 0:
        return 0.0
    p = hits / n
    den = 1 + z * z / n
    centre = p + z * z / (2 * n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (centre - half) / den


def starts(db: sqlite3.Connection) -> list[tuple[int, int, int, str, dict[str, int]]]:
    """(start_ts, event, player, position, counts) per starter, kickoff order."""
    ts = {int(e): int(t) for e, t in db.execute(
        "SELECT event_id, MIN(start_ts) FROM sofa_listing_event "
        "WHERE start_ts IS NOT NULL GROUP BY event_id")}
    out = []
    rows = db.execute(
        "SELECT x.sofascore_event_id, x.payload_json, s.lineups_json "
        "FROM sofa_event_extra x JOIN sofa_event_stats s USING (sofascore_event_id) "
        "WHERE x.kind = 'shotmap' AND length(x.payload_json) > 2 "
        "AND s.lineups_json IS NOT NULL")
    for eid, shot_raw, lu_raw in rows:
        if int(eid) not in ts:
            continue
        shotmap = json.loads(shot_raw)
        lineups = json.loads(lu_raw)
        for side in ("home", "away"):
            for p in (lineups.get(side) or {}).get("players") or []:
                if p.get("substitute") or not p.get("statistics"):
                    continue
                pid = (p.get("player") or {}).get("id")
                if not isinstance(pid, int):
                    continue
                counts = sd.player_counts(shotmap, pid)
                if counts is None:
                    continue
                pos = str(p.get("position") or (p.get("player") or {}).get("position")
                          or "?")
                out.append((ts[int(eid)], int(eid), pid, pos, counts))
    out.sort()
    return out


def measure(rows: list[tuple[int, int, int, str, dict[str, int]]],
            min_prior: int, window: int) -> dict[str, Any]:
    hist: dict[int, deque[dict[str, int]]] = defaultdict(lambda: deque(maxlen=window))
    pool_sum: dict[tuple[str, str], float] = defaultdict(float)
    pool_n: dict[str, int] = defaultdict(int)
    # (metric, line) -> list of (p by K, p pool, y)
    preds: dict[tuple[str, float], list[tuple[dict[int, float], float, int]]] = (
        defaultdict(list))
    day_rows: list[tuple[int, int, str, dict[str, int]]] = []
    current_day = None
    for start_ts, _eid, pid, pos, counts in rows:
        day = start_ts // 86400
        if day != current_day:
            # the pool learns a day only after the day is over
            for _, _p, ps, c in day_rows:
                pool_n[ps] += 1
                for m in sd.METRICS:
                    pool_sum[(ps, m)] += c[m]
            day_rows, current_day = [], day
        prior = hist[pid]
        if len(prior) >= min_prior and pool_n[pos] >= 200:
            for m in sd.METRICS:
                pm = pool_sum[(pos, m)] / pool_n[pos]
                total = sum(c[m] for c in prior)
                for line in LINES:
                    by_k = {k: poisson_over((total + k * pm) / (len(prior) + k), line)
                            for k in KS}
                    preds[(m, line)].append(
                        (by_k, poisson_over(pm, line), 1 if counts[m] > line else 0))
        day_rows.append((start_ts, pid, pos, counts))
        hist[pid].append(counts)
    return {"preds": preds}


def ll(p: float, y: int) -> float:
    p = min(max(p, 1e-6), 1 - 1e-6)
    return -math.log(p if y else 1 - p)


def report(
    preds: dict[tuple[str, float], list[Any]],
) -> tuple[list[str], dict[str, Any]]:
    lines = ["# Shot detail - walk-forward", ""]
    js: dict[str, Any] = {}
    for (m, line), rs in sorted(preds.items()):
        n = len(rs)
        if n < 500:
            continue
        base = sum(ll(pp, y) for _, pp, y in rs) / n
        by_k = {k: sum(ll(p[k], y) for p, _, y in rs) / n for k in KS}
        best = min(by_k, key=lambda k: by_k[k])
        hit = sum(y for *_, y in rs) / n
        lines.append(f"## {m} > {line}  (n {n}, base rate {hit:.3f})")
        lines.append("log-loss: pool " + f"{base:.4f}; " + ", ".join(
            f"K={k} {v:.4f}" for k, v in by_k.items()) + f"; best K={best}")
        lines.append("| forecast | n | mean forecast | realised | Wilson lo |")
        lines.append("|---|---|---|---|---|")
        cal = []
        for lo, hi in zip(BUCKETS, BUCKETS[1:], strict=False):
            b = [(p[best], y) for p, _, y in rs if lo <= p[best] < hi]
            if not b:
                continue
            h = sum(y for _, y in b)
            mean_f = sum(p for p, _ in b) / len(b)
            cal.append({"lo": lo, "hi": hi, "n": len(b), "forecast": mean_f,
                        "realised": h / len(b), "wilson_lo": wilson_lo(h, len(b))})
            lines.append(f"| {lo:.2f}-{hi:.2f} | {len(b)} | {mean_f:.3f} | "
                         f"{h / len(b):.3f} | {wilson_lo(h, len(b)):.3f} |")
        lines.append("")
        js[f"{m}|{line}"] = {"n": n, "base_rate": hit, "logloss_pool": base,
                             "logloss_by_k": by_k, "best_k": best, "calibration": cal}
    return lines, js


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--min-prior", type=int, default=5)
    ap.add_argument("--window", type=int, default=10)
    ap.add_argument("--md-out")
    ap.add_argument("--json-out")
    args = ap.parse_args()
    db = sqlite3.connect(f"file:{SofaConfig.from_env().db_path}?mode=ro", uri=True)
    rows = starts(db)
    out = measure(rows, args.min_prior, args.window)
    lines, js = report(out["preds"])
    head = [f"starters: {len(rows)}, matches: {len({r[1] for r in rows})}", ""]
    text = "\n".join(lines[:2] + head + lines[2:])
    print(text)
    if args.md_out:
        Path(args.md_out).write_text(text + "\n", encoding="utf-8")
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(js, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
