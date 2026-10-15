#!/usr/bin/env python3
"""Read-only measurement: best-of-five matches in the tennis games samples of
the cache replay (CLAUDE.md "Before the next refit": the best-of-five
games_total / games_won_for samples of the replay are not format-scoped).

Live SAMPLES keeps a past tennis match only when its format matches the
fixture's (`samples.py`: `infer_best_of(event) != fixture.default_period_count`
-> dropped), while the replay (`calibrate_from_cache`) takes a player's last
SAMPLE_N matches with games whatever their format. So a best-of-three
fixture of a player fresh from a Grand Slam is replayed with five-set game
counts in his sample - rows the football / tennis curves are fitted on.

For every best-of-three tennis match (from --from) where both players have
>= MIN_SAMPLE earlier matches with games, the two samples are built:

  R  replay: each player's last SAMPLE_N matches with games, any format
  S  scoped: the last SAMPLE_N best-of-three matches (what SAMPLES reads)

and scored where they differ ("affected"):

  games_total   pool of both players (each match once), mean as the centre
  games_won_for each player's own games

Scores: centre minus actual (bias) and squared error, and the log-loss of
P(OVER) at the line round(S mean)+0.5 from a normal with the sample's own
spread (a common yardstick, not SHEET's NB); R - S with a 95% match
bootstrap. Also the share of all best-of-three rows that are affected
(how much of the replay population this touches), overall and by
category (ATP / Challenger / ITF ...).

Nothing is written. ``REPLAYED_SPORTS`` is narrowed to tennis in-process so
the cache load holds no football.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_tennis_bo5_samples.py \\
        --db data/refit_2026-10-16/sofa_replay.db --from 2025-01-01 \\
        --json-out <f> --md-out <f>
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict, deque
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa.settle import surfaces_comparable  # noqa: E402
from scripts.sofa import calibrate_from_cache as cfc  # noqa: E402

SAMPLE_N = cfc.SAMPLE_N
MIN_SAMPLE = cfc.MIN_SAMPLE
REPS = 2000
SEED = 7


def ts_of(day: str) -> int:
    return int(datetime.fromisoformat(day).replace(tzinfo=UTC).timestamp())


POOL_N = 100   # how far back the surface-scoped sample may look


class Hist:
    """A player's earlier matches with games: (event, own, total, bo5), and
    the same with the surface for the surface-scoped arm."""

    def __init__(self) -> None:
        self.any: deque[tuple[int, float, float, bool]] = deque(maxlen=SAMPLE_N)
        self.bo3: deque[tuple[int, float, float, bool]] = deque(maxlen=SAMPLE_N)
        self.pool: deque[tuple[tuple[int, float, float, bool], str | None]] = deque(
            maxlen=POOL_N)

    def add(self, entry: tuple[int, float, float, bool],
            surface: str | None = None) -> None:
        self.any.append(entry)
        if not entry[3]:
            self.bo3.append(entry)
        self.pool.append((entry, surface))

    def scoped(self, surface: str | None) -> list[tuple[int, float, float, bool]]:
        """SAMPLES' rule: best of three AND a comparable surface (none when
        the fixture's surface is unknown), the newest SAMPLE_N, oldest first."""
        if surface is None:
            return []
        picked = [e for e, s in self.pool
                  if not e[3] and surfaces_comparable(s, surface)]
        return picked[-SAMPLE_N:]


def pooled_total(a: Sequence[tuple[int, float, float, bool]],
                 b: Sequence[tuple[int, float, float, bool]]) -> list[float]:
    """The total's pool: home side's matches, then the away side's not
    already in it (each match once), as the replay pools a total."""
    seen = {e[0] for e in a}
    return [e[2] for e in a] + [e[2] for e in b if e[0] not in seen]


def p_over(values: Sequence[float], line: float) -> float:
    m = sum(values) / len(values)
    sd = math.sqrt(max(np.var(values, ddof=1) if len(values) > 1 else 0.0, m, 1e-6))
    z = (line - m) / sd
    return min(max(0.5 * math.erfc(z / math.sqrt(2)), 1e-4), 1 - 1e-4)


def score(
    r_vals: Sequence[float], s_vals: Sequence[float], y: float,
) -> dict[str, float]:
    mr, ms = sum(r_vals) / len(r_vals), sum(s_vals) / len(s_vals)
    line = math.floor(ms) + 0.5
    o = 1.0 if y > line else 0.0
    pr, ps = p_over(r_vals, line), p_over(s_vals, line)

    def ll(p: float) -> float:
        return -(o * math.log(p) + (1 - o) * math.log(1 - p))
    return {"shift": mr - ms, "bias_r": mr - y, "bias_s": ms - y,
            "se_r": (mr - y) ** 2, "se_s": (ms - y) ** 2,
            "ll_r": ll(pr), "ll_s": ll(ps)}


def boot(values: np.ndarray, groups: np.ndarray, reps: int = REPS,
         seed: int = SEED) -> tuple[float, float, float]:
    if len(values) == 0:
        return (math.nan, math.nan, math.nan)
    uniq, inv = np.unique(groups, return_inverse=True)
    sums = np.bincount(inv, weights=values)
    counts = np.bincount(inv)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(uniq), (reps, len(uniq)))
    means = sums[idx].sum(axis=1) / counts[idx].sum(axis=1)
    return (float(values.mean()), float(np.percentile(means, 2.5)),
            float(np.percentile(means, 97.5)))


def replay(played: Sequence[Any], from_ts: int) -> dict[str, Any]:
    hist: dict[int, Hist] = defaultdict(Hist)
    rows: dict[str, list[dict[str, float]]] = {
        "games_total": [], "games_won_for": [],
        "games_total (format+surface)": [], "games_won_for (format+surface)": []}
    counts: Counter[str] = Counter()
    by_cat: Counter[tuple[str, str]] = Counter()
    i = 0
    n = len(played)
    while i < n:
        ts = played[i].timestamp
        j = i
        while j < n and played[j].timestamp == ts:
            j += 1
        group = played[i:j]
        for m in group:
            g = m.values.get("games")
            if g is None or m.tennis is None or ts < from_ts or m.tennis.best_of_five:
                continue
            ha, hb = hist[m.home_id], hist[m.away_id]
            if len(ha.any) < MIN_SAMPLE or len(hb.any) < MIN_SAMPLE:
                continue
            cat = m.tennis.category_name or "?"
            counts["bo3_fixtures"] += 1
            r_tot = pooled_total(list(ha.any), list(hb.any))
            s_tot = pooled_total(list(ha.bo3), list(hb.bo3))
            affected = len(s_tot) >= MIN_SAMPLE and r_tot != s_tot
            by_cat[(cat, "all")] += 1
            if r_tot != s_tot:
                counts["total_differs"] += 1
                by_cat[(cat, "differs")] += 1
            if affected:
                rows["games_total"].append(
                    {"ev": float(m.event_id), **score(r_tot, s_tot, g[0] + g[1])})
            surf = m.tennis.ground_type
            fs_tot = pooled_total(ha.scoped(surf), hb.scoped(surf))
            if len(fs_tot) >= MIN_SAMPLE and r_tot != fs_tot:
                counts["total_differs_fs"] += 1
                rows["games_total (format+surface)"].append(
                    {"ev": float(m.event_id), **score(r_tot, fs_tot, g[0] + g[1])})
            for h, y in ((ha, g[0]), (hb, g[1])):
                counts["bo3_sides"] += 1
                r_own = [e[1] for e in h.any]
                s_own = [e[1] for e in h.bo3]
                if r_own != s_own:
                    counts["side_differs"] += 1
                if len(s_own) >= MIN_SAMPLE and r_own != s_own:
                    rows["games_won_for"].append(
                        {"ev": float(m.event_id), **score(r_own, s_own, y)})
                fs_own = [e[1] for e in h.scoped(surf)]
                if len(fs_own) >= MIN_SAMPLE and r_own != fs_own:
                    rows["games_won_for (format+surface)"].append(
                        {"ev": float(m.event_id), **score(r_own, fs_own, y)})
        for m in group:
            g = m.values.get("games")
            if g is None or m.tennis is None:
                continue
            bo5 = bool(m.tennis.best_of_five)
            surf = m.tennis.ground_type
            hist[m.home_id].add((m.event_id, float(g[0]), float(g[0] + g[1]), bo5),
                                surf)
            hist[m.away_id].add((m.event_id, float(g[1]), float(g[0] + g[1]), bo5),
                                surf)
        i = j
    out: dict[str, Any] = {"counts": dict(counts), "markets": {}}
    for market, rs in rows.items():
        if not rs:
            out["markets"][market] = {"n": 0}
            continue
        ev = np.asarray([r["ev"] for r in rs])
        col = {k: np.asarray([r[k] for r in rs]) for k in rs[0] if k != "ev"}
        out["markets"][market] = {
            "n": len(rs), "matches": int(len(np.unique(ev))),
            "shift_R_minus_S": boot(col["shift"], ev),
            "bias_R": boot(col["bias_r"], ev), "bias_S": boot(col["bias_s"], ev),
            "se_R_minus_S": boot(col["se_r"] - col["se_s"], ev),
            "ll_R_minus_S": boot(col["ll_r"] - col["ll_s"], ev),
        }
    top = sorted({c for c, _ in by_cat}, key=lambda c: -by_cat[(c, "all")])[:12]
    out["by_category"] = {c: {"bo3_fixtures": by_cat[(c, "all")],
                              "total_sample_differs": by_cat[(c, "differs")]}
                          for c in top}
    return out


def markdown(res: dict[str, Any]) -> str:
    def ci(t: Sequence[float], f: str = "{:+.3f}") -> str:
        return f"{f.format(t[0])} [{f.format(t[1])}; {f.format(t[2])}]"
    c = res["counts"]
    lines = ["# best-of-five in the replay's tennis games samples", "",
             f"params: `{json.dumps(res['params'])}`", "",
             f"best-of-three fixtures with both samples: {c.get('bo3_fixtures', 0)}; "
             f"total sample differs (a bo5 match in it): {c.get('total_differs', 0)}; "
             f"sides {c.get('bo3_sides', 0)}, side sample differs "
             f"{c.get('side_differs', 0)}", "",
             "| market | rows | matches | centre shift R-S | bias R | bias S | "
             "SE R-S | log-loss R-S |", "|---|---|---|---|---|---|---|---|"]
    for m, v in res["markets"].items():
        if not v.get("n"):
            lines.append(f"| {m} | 0 | | | | | | |")
            continue
        lines.append(
            f"| {m} | {v['n']} | {v['matches']} | {ci(v['shift_R_minus_S'])} | "
            f"{ci(v['bias_R'])} | {ci(v['bias_S'])} | {ci(v['se_R_minus_S'])} | "
            f"{ci(v['ll_R_minus_S'], '{:+.4f}')} |")
    lines += ["", "| category | bo3 fixtures | total sample with a bo5 |",
              "|---|---|---|"]
    for cat, v in res["by_category"].items():
        lines.append(f"| {cat} | {v['bo3_fixtures']} | {v['total_sample_differs']} |")
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("--db", type=Path, required=True)
    ap.add_argument("--from", dest="from_day", default="2025-01-01")
    ap.add_argument("--history-from", default="2024-07-01",
                    help="matches before this are not loaded (samples need ~10)")
    ap.add_argument("--json-out", type=Path, default=None)
    ap.add_argument("--md-out", type=Path, default=None)
    args = ap.parse_args(argv)
    cfc.REPLAYED_SPORTS = ("tennis",)  # type: ignore[assignment]  # tennis only
    played = cfc.load_cache(args.db, since_ts=ts_of(args.history_from))
    res = replay(played, ts_of(args.from_day))
    res["params"] = {"db": str(args.db), "from": args.from_day,
                     "history_from": args.history_from, "sample_n": SAMPLE_N,
                     "min_sample": MIN_SAMPLE, "reps": REPS}
    md = markdown(res)
    if args.json_out:
        args.json_out.write_text(json.dumps(res, indent=1))
    if args.md_out:
        args.md_out.write_text(md)
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
