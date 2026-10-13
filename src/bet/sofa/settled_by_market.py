"""Settled lines by market family and direction (read-only evidence).

Pure statistics for `scripts/sofa/measure_settled_by_market.py`: a line is
(game, p, odds, y); a cell groups lines by a label; the ROI interval is a
bootstrap over games (a game's lines are not independent). Raw model p, no
coupon gates - a table of what the model and the price did, never a gate.
"""

from __future__ import annotations

import random
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

SEED = 20261013
REPS = 800


@dataclass(frozen=True)
class Line:
    game: str
    p: float
    odds: float
    y: int


def roi_of(lines: Sequence[Line]) -> float:
    return sum((x.odds - 1.0) if x.y else -1.0 for x in lines) / len(lines)


def select(lines: Iterable[Line], p_min: float) -> list[Line]:
    return [x for x in lines if x.p >= p_min and x.odds > 1.0]


def bootstrap_roi(lines: Sequence[Line], seed: int = SEED,
                  reps: int = REPS) -> tuple[float, float]:
    """95% interval of the ROI per unit, resampling games."""
    by_game: dict[str, list[Line]] = defaultdict(list)
    for x in lines:
        by_game[x.game].append(x)
    games = list(by_game)
    rng = random.Random(seed)
    draws: list[float] = []
    for _ in range(reps):
        sample = [x for g in rng.choices(games, k=len(games)) for x in by_game[g]]
        draws.append(roi_of(sample))
    draws.sort()
    return draws[int(0.025 * reps)], draws[int(0.975 * reps) - 1]


def cell_stats(lines: Sequence[Line], p_min: float, seed: int = SEED,
               reps: int = REPS) -> dict[str, Any] | None:
    chosen = select(lines, p_min)
    if not chosen:
        return None
    n = len(chosen)
    lo, hi = bootstrap_roi(chosen, seed, reps)
    return {"n": n, "games": len({x.game for x in chosen}),
            "hit": sum(x.y for x in chosen) / n,
            "model": sum(x.p for x in chosen) / n,
            "implied": sum(1.0 / x.odds for x in chosen) / n,
            "roi": roi_of(chosen), "roi_lo": lo, "roi_hi": hi}


def table(cells: dict[tuple[str, ...], list[Line]], p_min: float,
          min_n: int = 1) -> list[dict[str, Any]]:
    """One record per cell with at least `min_n` lines at p >= p_min, best ROI
    first; a cell's seed is fixed so a rerun reproduces the table."""
    out: list[dict[str, Any]] = []
    for label, lines in cells.items():
        s = cell_stats(lines, p_min)
        if s is not None and s["n"] >= min_n:
            out.append({"label": list(label), **s})
    out.sort(key=lambda r: (-r["roi"], r["label"]))
    return out


def render_markdown(title: str, rows: Sequence[dict[str, Any]],
                    label_cols: Sequence[str]) -> str:
    head = "| " + " | ".join(label_cols) + \
        " | n | games | hit | model p | 1/odds | ROI | 95% ROI (games) |"
    lines = [f"### {title}", "", head,
             "|" + "---|" * (len(label_cols) + 7)]
    for r in rows:
        lines.append(
            "| " + " | ".join(str(c) for c in r["label"]) +
            f" | {r['n']} | {r['games']} | {r['hit']:.3f} | {r['model']:.3f} | "
            f"{r['implied']:.3f} | {100 * r['roi']:+.1f}% | "
            f"[{100 * r['roi_lo']:+.1f}, {100 * r['roi_hi']:+.1f}] |")
    if not rows:
        lines.append("| (no lines) |" + " |" * (len(label_cols) + 6))
    return "\n".join(lines) + "\n"
