#!/usr/bin/env python3
"""Can Superbet's tennis "after N games / after N points" markets be forecast
from the players' serve history? Read-only evidence on the cached history.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_tennis_game_order.py \\
        [--k-games 40] [--k-points 200] [--md-out f] [--json-out f]

Markets (Superbet names, market_coverage tn.game_order / tn.points_in_game):
  "1. set - bedzie prowadzic po 2 gemach"   draw (both hold) / A leads / B leads
  "1. set - dokladny wynik po 4 gemach"     2:2 (and the full 0:4..4:0 grid)
  "<player> 1. gem serwisowy - wynik po 2 / 3 punktach"   30:0, 15:15, 0:30 ...

Forecast, as of each match (only earlier matches read): a player's hold rate =
service games won / played over his earlier matches, shrunk to the pool with
--k-games pseudo-games; the receiver's break rate likewise; the hold of A
against B = logit(hold_A) + logit(1 - break_B) - logit(pool hold). The serve
point = service points won / served, shrunk with --k-points, adjusted by the
receiver's return-point rate the same way. Games in set 1's first four are
independent given those (first server unknown before the toss: the draw /
2:2 forecasts do not depend on it, a lead does - both orders averaged).

Outcomes from the point-by-point (bet.sofa.point_by_point, sofa_event_extra).
Reports per selection: n, mean forecast, realised, log-loss against the pool
forecast, and calibration by forecast bucket with the Wilson lower bound - the
number a curve would print. Superbet's prices are NOT here (recorded from
2026-10-14 by bet.sofa.unmapped_prices). Exit 0, 2 on a crash.
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import point_by_point as pbp  # noqa: E402
from bet.sofa.config import SofaConfig  # noqa: E402
from scripts.sofa.measure_shot_detail import wilson_lo  # noqa: E402

BUCKETS = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 1.01)
SERVE_KEYS = ("serviceGamesWon", "serviceGamesTotal", "servicePointsScored",
              "receiverPointsScored")


def logit(p: float) -> float:
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def expit(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def serve_numbers(stats: dict[str, Any]) -> tuple[list[int], list[int]] | None:
    """[sgw, sgt, spw, rpw] for home and away from /statistics ALL."""
    vals: dict[str, tuple[int, int]] = {}
    for per in stats.get("statistics") or []:
        if per.get("period") != "ALL":
            continue
        for g in per.get("groups") or []:
            for it in g.get("statisticsItems") or []:
                k = it.get("key")
                if k in SERVE_KEYS and k not in vals:
                    try:
                        vals[k] = (int(it["homeValue"]), int(it["awayValue"]))
                    except (KeyError, TypeError, ValueError):
                        return None
    if any(k not in vals for k in SERVE_KEYS):
        return None
    return ([vals[k][0] for k in SERVE_KEYS], [vals[k][1] for k in SERVE_KEYS])


Row = tuple[int, int, int, int, list[int], list[int]]


def load(db: sqlite3.Connection) -> tuple[list[Row], dict[int, Any]]:
    """Every tennis match with serve statistics, kickoff order:
    (ts, event, home id, away id, home numbers, away numbers); and the
    point-by-point payload of the events that have one."""
    meta = {int(e): (int(t), int(h), int(a)) for e, t, h, a in db.execute(
        "SELECT event_id, start_ts, json_extract(event_json, '$.homeTeam.id'), "
        "json_extract(event_json, '$.awayTeam.id') FROM sofa_listed_event "
        "WHERE sport = 'tennis' AND start_ts IS NOT NULL "
        "AND json_extract(event_json, '$.homeTeam.id') IS NOT NULL")}
    rows = []
    for eid, raw in db.execute(
        "SELECT sofascore_event_id, statistics_json FROM sofa_event_stats "
        "WHERE statistics_json LIKE '%serviceGamesWon%'"
    ):
        m = meta.get(int(eid))
        if m is None:
            continue
        nums = serve_numbers(json.loads(raw))
        if nums is None:
            continue
        rows.append((m[0], int(eid), m[1], m[2], nums[0], nums[1]))
    rows.sort()
    pbps = {int(e): json.loads(p) for e, p in db.execute(
        "SELECT sofascore_event_id, payload_json FROM sofa_event_extra "
        "WHERE kind = 'point_by_point' AND length(payload_json) > 2")}
    return rows, pbps


def point_state(points: tuple[tuple[str, str], ...], n: int, server: int) -> str | None:
    """'30:0'-style score from the SERVER's side after n points of a game;
    None when the game ended before (the winning point is not in the list:
    after len(points) points the score is the last entry)."""
    if len(points) < n:
        return None
    h, a = points[n - 1]
    return f"{h}:{a}" if server == 1 else f"{a}:{h}"


def binom_states(p: float, n: int) -> dict[str, float]:
    names = {0: "0", 1: "15", 2: "30", 3: "40"}
    out = {}
    for w in range(n + 1):
        out[f"{names[w]}:{names[n - w]}"] = (math.comb(n, w) * p ** w
                                            * (1 - p) ** (n - w))
    return out


def exact_after_4(ha: float, hb: float) -> dict[str, float]:
    """Set 1's score after 4 games: each player serves two of them."""
    out: dict[str, float] = defaultdict(float)
    for a_holds in range(3):
        pa = math.comb(2, a_holds) * ha ** a_holds * (1 - ha) ** (2 - a_holds)
        for b_holds in range(3):
            pb = math.comb(2, b_holds) * hb ** b_holds * (1 - hb) ** (2 - b_holds)
            a_games = a_holds + (2 - b_holds)
            out[f"{a_games}:{4 - a_games}"] += pa * pb
    return dict(out)


def measure(rows: list[Any], pbps: dict[int, Any], k_games: float,
            k_points: float) -> dict[str, list[tuple[float, float, int]]]:
    # running per-player sums: sgw, sgt, spw, sp(served), rgw(return games
    # won), rgt, rpw, rp(return points played)
    acc: dict[int, list[float]] = defaultdict(lambda: [0.0] * 8)
    pool = [0.0] * 8
    preds: dict[str, list[tuple[float, float, int]]] = defaultdict(list)
    for _ts, eid, home, away, hn, an in rows:
        if eid in pbps and pool[1] > 1000:
            games = pbp.games(pbps[eid])
            if games:
                ph = pool[0] / pool[1]
                pp = pool[2] / pool[3]

                def hold(s: list[float], r: list[float]) -> float:
                    h = (s[0] + k_games * ph) / (s[1] + k_games)
                    br = (r[4] + k_games * (1 - ph)) / (r[5] + k_games)
                    return expit(logit(h) + logit(1 - br) - logit(ph))

                def spt(s: list[float], r: list[float]) -> float:
                    w = (s[2] + k_points * pp) / (s[3] + k_points)
                    rw = (r[6] + k_points * (1 - pp)) / (r[7] + k_points)
                    return expit(logit(w) + logit(1 - rw) - logit(pp))

                a, b = acc[home], acc[away]
                ha, hb = hold(a, b), hold(b, a)
                set1 = pbp.in_set(games, 1)
                base_h = ph
                if len(set1) >= 2:
                    both = int(set1[0].held and set1[1].held)
                    preds["lead_after_2|draw"].append((ha * hb, base_h ** 2, both))
                    lead_home = int(set1[1].home_games == 2)
                    preds["lead_after_2|home"].append(
                        (ha * (1 - hb), base_h * (1 - base_h), lead_home))
                if len(set1) >= 4:
                    sc = pbp.score_after(set1, 4)
                    grid = exact_after_4(ha, hb)
                    base = exact_after_4(base_h, base_h)
                    key = f"{sc[0]}:{sc[1]}" if sc else None
                    preds["exact_after_4|2:2"].append(
                        (grid["2:2"], base["2:2"], int(key == "2:2")))
                pa, pb_ = spt(a, b), spt(b, a)
                for side, p_serve in ((1, pa), (2, pb_)):
                    first = next((g for g in set1 if g.server == side), None)
                    if first is None:
                        continue
                    for n in (2, 3):
                        state = point_state(first.points, n, side)
                        if state is None:
                            continue
                        model = binom_states(p_serve, n)
                        base = binom_states(pp, n)
                        for name, p in model.items():
                            preds[f"serve_after_{n}|{name}"].append(
                                (p, base[name], int(state == name)))
        # learn the match only after forecasting it
        for pid, mine, theirs in ((home, hn, an), (away, an, hn)):
            # own serve points won + lost to the returner; return games won
            # = the opponent's service games lost; return points played =
            # the opponent's serve points won + our return points won
            add = (mine[0], mine[1], mine[2], mine[2] + theirs[3],
                   theirs[1] - theirs[0], theirs[1], mine[3], theirs[2] + mine[3])
            acc[pid] = [x + y for x, y in zip(acc[pid], add, strict=True)]
        for mine, theirs in ((hn, an), (an, hn)):
            add_pool = (mine[0], mine[1], mine[2], mine[2] + theirs[3])
            pool[:4] = [x + y for x, y in zip(pool[:4], add_pool, strict=True)]
    return preds


def ll(p: float, y: int) -> float:
    p = min(max(p, 1e-6), 1 - 1e-6)
    return -math.log(p if y else 1 - p)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--k-games", type=float, default=40.0)
    ap.add_argument("--k-points", type=float, default=200.0)
    ap.add_argument("--md-out")
    ap.add_argument("--json-out")
    args = ap.parse_args()
    db = sqlite3.connect(f"file:{SofaConfig.from_env().db_path}?mode=ro", uri=True)
    rows, pbps = load(db)
    preds = measure(rows, pbps, args.k_games, args.k_points)
    lines = ["# Tennis game order / points in game - walk-forward", "",
             f"matches with serve statistics: {len(rows)}; with point-by-point: "
             f"{len(pbps)}", ""]
    js: dict[str, Any] = {}
    for key, rs in sorted(preds.items()):
        n = len(rs)
        if n < 300:
            continue
        hit = sum(y for *_, y in rs) / n
        d_ll = sum(ll(p, y) - ll(b, y) for p, b, y in rs) / n
        lines.append(f"## {key}: n {n}, realised {hit:.3f}, mean forecast "
                     f"{sum(p for p, *_ in rs) / n:.3f}, log-loss vs pool {d_ll:+.4f}")
        lines.append("| forecast | n | mean | realised | Wilson lo |")
        lines.append("|---|---|---|---|---|")
        cal = []
        for lo, hi in zip(BUCKETS, BUCKETS[1:], strict=False):
            b = [(p, y) for p, _, y in rs if lo <= p < hi]
            if len(b) < 30:
                continue
            h = sum(y for _, y in b)
            m = sum(p for p, _ in b) / len(b)
            cal.append({"lo": lo, "hi": hi, "n": len(b), "forecast": m,
                        "realised": h / len(b), "wilson_lo": wilson_lo(h, len(b))})
            lines.append(f"| {lo:.2f}-{hi:.2f} | {len(b)} | {m:.3f} | {h / len(b):.3f} "
                         f"| {wilson_lo(h, len(b)):.3f} |")
        lines.append("")
        js[key] = {"n": n, "realised": hit, "d_logloss_vs_pool": d_ll,
                   "calibration": cal}
    text = "\n".join(lines)
    print(text)
    if args.md_out:
        Path(args.md_out).write_text(text + "\n", encoding="utf-8")
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(js, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
