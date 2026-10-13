#!/usr/bin/env python3
"""The registered A7 comparison (docs/sofa/evidence/
market_positioned_lines_2026-10-13.md, section 1): two fitted sport curves
read on the same settled Superbet lines. Read-only evidence, never a gate.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_market_positioned_lines.py \\
        --base data/refit_2026-10-13/bb_base/cal.json \\
        --variant data/refit_2026-10-13/a7/cal.json \\
        --rows data/refit_2026-10-13/bb_base/rows/basketball_superbet_settled.jsonl \\
        --from 2026-09-29 --to 2026-10-12 [--json-out f]

Confidence = the curve bucket's realised_lo95 (no admission, no line
evidence). Primary: mean log-loss of the confidence, paired on the lines
both curves read, variant - base, 95% interval from a bootstrap over games.
Second: realised - confidence on the lines a curve reads at >= 0.70 (each
curve its own set), 95% interval by game. Threshold: Δ log-loss < 0 with the
upper bound < 0 AND |printable gap| of the variant < the base's.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa.sport_confidence import PRINTABLE_FROM, _find  # noqa: E402

KEYS = ("total|OVER", "total|UNDER", "handicap|TEAM", "team_total|OVER",
        "team_total|UNDER")
BOOT = 2000
SEED = 13


def _ll(p: float, y: int) -> float:
    q = min(max(p, 1e-6), 1 - 1e-6)
    return -math.log(q if y else 1 - q)


def read_curves(path: str, sport: str) -> dict[str, Any]:
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    return dict(doc["sports"][sport]["curves"])


def confidence(curves: Mapping[str, Any], key: str, p: float) -> float | None:
    entry = _find(curves.get(key) or {}, p)
    return None if entry is None else float(entry["realised_lo95"])


def _boot(per_game: Mapping[str, tuple[float, int]], rng: random.Random
          ) -> list[float]:
    """Mean over lines (sum / count per game), resampled by game."""
    games = list(per_game.values())
    point = sum(s for s, _ in games) / max(1, sum(n for _, n in games))
    stats: list[float] = []
    for _ in range(BOOT):
        s = n = 0.0
        for _ in range(len(games)):
            gs, gn = games[rng.randrange(len(games))]
            s += gs
            n += gn
        stats.append(s / n if n else 0.0)
    stats.sort()
    return [round(point, 5), round(stats[int(0.025 * BOOT)], 5),
            round(stats[int(0.975 * BOOT) - 1], 5)]


def compare(rows: Sequence[Mapping[str, Any]], base: Mapping[str, Any],
            variant: Mapping[str, Any], keys: Sequence[str]) -> dict[str, Any]:
    rng = random.Random(SEED)
    paired: dict[str, tuple[float, int]] = defaultdict(lambda: (0.0, 0))
    ll_b: dict[str, tuple[float, int]] = defaultdict(lambda: (0.0, 0))
    ll_v: dict[str, tuple[float, int]] = defaultdict(lambda: (0.0, 0))
    pr: dict[str, dict[str, tuple[float, int]]] = {
        "base": defaultdict(lambda: (0.0, 0)),
        "variant": defaultdict(lambda: (0.0, 0))}
    pr_conf: dict[str, list[float]] = {"base": [], "variant": []}
    pr_y: dict[str, list[int]] = {"base": [], "variant": []}
    cover = {"lines": 0, "base": 0, "variant": 0, "both": 0}
    for r in rows:
        if r["key"] not in keys:
            continue
        p, y, g = float(r["p"]), int(r["y"]), str(r["game"])
        cb = confidence(base, r["key"], p)
        cv = confidence(variant, r["key"], p)
        cover["lines"] += 1
        cover["base"] += cb is not None
        cover["variant"] += cv is not None
        for name, c in (("base", cb), ("variant", cv)):
            if c is not None and c >= PRINTABLE_FROM:
                s, n = pr[name][g]
                pr[name][g] = (s + (y - c), n + 1)
                pr_conf[name].append(c)
                pr_y[name].append(y)
        if cb is None or cv is None:
            continue
        cover["both"] += 1
        lb, lv = _ll(cb, y), _ll(cv, y)
        s, n = paired[g]
        paired[g] = (s + lv - lb, n + 1)
        s, n = ll_b[g]
        ll_b[g] = (s + lb, n + 1)
        s, n = ll_v[g]
        ll_v[g] = (s + lv, n + 1)
    out: dict[str, Any] = {"coverage": cover,
                           "paired_games": len(paired)}
    if paired:
        out["logloss_base"] = _boot(ll_b, rng)[0]
        out["logloss_variant"] = _boot(ll_v, rng)[0]
        out["delta_logloss"] = _boot(paired, rng)
    for name in ("base", "variant"):
        n = len(pr_y[name])
        if n:
            out[f"printable_{name}"] = {
                "n": n, "games": len(pr[name]),
                "confidence": round(sum(pr_conf[name]) / n, 4),
                "realised": round(sum(pr_y[name]) / n, 4),
                "gap": _boot(pr[name], rng)}
    d = out.get("delta_logloss")
    gb = (out.get("printable_base") or {}).get("gap")
    gv = (out.get("printable_variant") or {}).get("gap")
    out["threshold"] = {
        "logloss_better": bool(d and d[0] < 0 and d[2] < 0),
        "printable_gap_closer": bool(gb and gv and abs(gv[0]) < abs(gb[0])),
    }
    out["threshold"]["met"] = all(out["threshold"].values())
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--base", required=True)
    ap.add_argument("--variant", required=True)
    ap.add_argument("--rows", required=True,
                    help="superbet_settled rows (fit_sport_confidence --rows-out)")
    ap.add_argument("--sport", default="basketball")
    ap.add_argument("--from", dest="date_from", required=True)
    ap.add_argument("--to", dest="date_to", required=True)
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args()
    base = read_curves(args.base, args.sport)
    variant = read_curves(args.variant, args.sport)
    with open(args.rows, encoding="utf-8") as f:
        rows = [r for r in map(json.loads, f)
                if args.date_from <= str(r.get("date")) <= args.date_to]
    result: dict[str, Any] = {
        "rows_file": args.rows, "window": [args.date_from, args.date_to],
        "keys": list(KEYS), "registered": compare(rows, base, variant, KEYS),
        "per_key": {k: compare(rows, base, variant, (k,)) for k in KEYS},
        "all_keys": compare(rows, base, variant,
                            sorted({str(r["key"]) for r in rows})),
    }
    text = json.dumps(result, indent=1)
    if args.json_out:
        Path(args.json_out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
