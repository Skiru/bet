#!/usr/bin/env python3
"""Does the model add anything to the price? The combination test.

Fits P(win) = sigmoid(a + b * logit(p_model) + c * logit(p_price)) on graded
lines (JSONL rows with p_model, p_price, y and a `game` cluster key, as
written by measure_score_model.py --rows-out), with a 95% interval for b
from a bootstrap over games. b near 0 means the model carries no information
beyond the price, however its Brier compares; b > 0 with its interval clear
of 0 means it does (Manner 2016's combination test, the question every sofa
sport has to answer before a model may move a coupon).

An analysis tool: it writes nothing the pipeline reads.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_model_information.py \\
        --rows runs/.../hockey.rows.jsonl [--family total]
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Any

BOOTSTRAP = 1000
EPS = 1e-4


def _logit(p: float) -> float:
    p = min(max(p, EPS), 1.0 - EPS)
    return math.log(p / (1.0 - p))


def fit(
    rows: Sequence[dict[str, Any]], ridge: float = 1e-3
) -> tuple[float, float, float]:
    """(a, b, c) by Newton's method on the log-likelihood, lightly ridged."""
    w = [0.0, 0.0, 1.0]  # start at "the price, as is"
    xs = [(1.0, _logit(r["p_model"]), _logit(r["p_price"])) for r in rows]
    ys = [float(r["y"]) for r in rows]
    for _ in range(50):
        g = [0.0, 0.0, 0.0]
        h = [[0.0] * 3 for _ in range(3)]
        for x, y in zip(xs, ys, strict=True):
            z = sum(wi * xi for wi, xi in zip(w, x, strict=True))
            p = 1.0 / (1.0 + math.exp(-max(min(z, 30.0), -30.0)))
            q = p * (1.0 - p)
            for i in range(3):
                g[i] += (p - y) * x[i]
                for j in range(3):
                    h[i][j] += q * x[i] * x[j]
        for i in range(3):
            g[i] += ridge * (w[i] - (1.0 if i == 2 else 0.0))
            h[i][i] += ridge
        step = _solve(h, g)
        w = [wi - si for wi, si in zip(w, step, strict=True)]
        if sum(abs(si) for si in step) < 1e-9:
            break
    return w[0], w[1], w[2]


def _solve(a: list[list[float]], b: list[float]) -> list[float]:
    m = [row[:] + [bv] for row, bv in zip(a, b, strict=True)]
    n = len(b)
    for c in range(n):
        piv = max(range(c, n), key=lambda r: abs(m[r][c]))
        m[c], m[piv] = m[piv], m[c]
        if abs(m[c][c]) < 1e-12:
            return [0.0] * n
        for r in range(n):
            if r != c:
                f = m[r][c] / m[c][c]
                m[r] = [m[r][k] - f * m[c][k] for k in range(n + 1)]
    return [m[i][n] / m[i][i] for i in range(n)]


def bootstrap_b(rows: Sequence[dict[str, Any]], seed: int = 7,
                n: int = BOOTSTRAP) -> tuple[float, float, float]:
    """b, and its 95% interval from resampling whole games."""
    by_game: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_game[str(r["game"])].append(r)
    games = list(by_game)
    rng = random.Random(seed)
    stats = []
    for _ in range(n):
        sample = [r for _ in games for r in by_game[games[rng.randrange(len(games))]]]
        stats.append(fit(sample)[1])
    stats.sort()
    return fit(rows)[1], stats[int(0.025 * n)], stats[int(0.975 * n)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--rows", required=True)
    ap.add_argument("--family", default=None)
    ap.add_argument("--bootstrap", type=int, default=BOOTSTRAP)
    args = ap.parse_args()
    text = Path(args.rows).read_text()
    rows = [json.loads(line) for line in text.splitlines() if line]
    if args.family:
        rows = [r for r in rows if r.get("family") == args.family]
    if len(rows) < 30:
        print(json.dumps({"rows": len(rows), "verdict": "too few"}))
        return 0
    a, b, c = fit(rows)
    b_hat, lo, hi = bootstrap_b(rows, n=args.bootstrap)
    verdict = ("model adds information" if lo > 0 else
               "model hurts" if hi < 0 else "no evidence the model adds anything")
    print(json.dumps({
        "rows": len(rows), "games": len({r["game"] for r in rows}),
        "family": args.family or "ALL", "a": round(a, 4), "b": round(b_hat, 4),
        "b_95": [round(lo, 4), round(hi, 4)], "c": round(c, 4), "verdict": verdict,
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
