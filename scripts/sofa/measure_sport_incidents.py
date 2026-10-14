#!/usr/bin/env python3
"""Order markets of the measured sports from Sofascore incidents - read-only
evidence, never a gate.

Superbet prices "1. gol" (hockey: which team scores first, or no goal;
`market_coverage` hk.goal_order) and "Wyścig do X punktów" (basketball: which
team reaches X points first; bb.score_order). Neither is graded by the period
scores SHADOW_SETTLE keeps; both are by the incidents
(`backfill_event_extra.py --kind incidents`, sofa_event_extra).

Walk forward over the sport's history (score_model.load_events ->
sport_confidence.parse_history), as `walk_forward_rows` does: the model is
built from the games strictly before the first scored game, rebuilt every
REBUILD_DAYS, and the rating book is updated after each start time; games
sharing a start are forecast before any is learnt. The day's rules:
strict league rate (epochs.LEAGUE_RATE_RULE) and basketball's freshness noise.

  * hockey "1. gol" - regulation only (an assumption about Superbet's
    settlement, not read in its terms): the per-period goal expectations as
    independent Poisson processes - P(no goal) = exp(-sum), P(home first) =
    sum_k P(none before k) (1 - exp(-tot_k)) eh_k / tot_k. Also "1. tercja -
    1. gol" (period 1 alone).
  * basketball race to X - the score model's simulated games give each draw a
    home share q of regulation points; a draw's race is a sequence of scoring
    plays, home with probability q, each worth 1 / 2 / 3 points by the running
    share of the plays of the games scored before it. P = the share of draws
    whose home side reaches X first.

The base rate is the running class share of the games scored before each one
(Laplace prior). Log-loss model minus base with a game bootstrap interval;
calibration of the per-side rows (the two-sided rung the pipeline would read)
by sport_confidence's buckets with the Wilson lower bound; the share of side
rows >= 0.70.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_sport_incidents.py \\
        --sport hockey [--json-out f] [--md-out f]
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sqlite3
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from bet.sofa.config import SofaConfig
from bet.sofa.football_rating import FootballResult
from bet.sofa.score_model import ScoreModel, _rated_values, build_model, load_events
from bet.sofa.shadow import SPORTS, ShadowSport
from bet.sofa.sport_confidence import (
    EDGES,
    REBUILD_DAYS,
    HistoryGame,
    bucket_of,
    parse_history,
    wilson_lo,
)

RACE_XS = (10, 15, 20, 25, 30)
N_SIMS = 200
BOOTSTRAP = 1000
PRINTABLE = 0.70
# 1 / 2 / 3-point shares of a basketball scoring play until the replay has
# learnt MIN_LEARNT_PLAYS of its own (the 9 games fetched 2026-10-14: 0.34 /
# 0.50 / 0.17; the distribution count only - never a scored game's p)
DEFAULT_PLAY_SIZES = (0.34, 0.50, 0.16)
MIN_LEARNT_PLAYS = 500
EPS = 1e-6


# --- the outcomes, from one game's incidents ---------------------------------

def _incidents(payload: Any) -> list[dict[str, Any]]:
    inc = payload.get("incidents") if isinstance(payload, dict) else None
    return [i for i in inc or [] if isinstance(i, dict)]


def hockey_goals(payload: Any) -> list[str] | None:
    """"H" / "A" of every goal (overtime included) in the order of the running
    score, or None when a goal has no side / score, the running total does
    not step by one, or a goal's side is not the side whose score moved.

    The order is the running score's, never the clock's: on 2026-10-14 a
    hockey feed (16836848) listed its first-period goals at 4', 11', 19' with
    the scores 3-0, 2-0, 1-0 - the incident ids follow the score, so the
    clock was the reversed one. Shoot-out attempts are not `goal` incidents
    with a running score past the game's, so they never enter."""
    out: list[tuple[int, int, int, str]] = []
    for i in _incidents(payload):
        if i.get("incidentType") != "goal":
            continue
        side = i.get("isHome")
        hs, as_ = i.get("homeScore"), i.get("awayScore")
        if not isinstance(side, bool) or not isinstance(hs, int) \
                or not isinstance(as_, int):
            return None
        out.append((hs + as_, hs, as_, "H" if side else "A"))
    out.sort()
    prev_h = prev_a = 0
    for k, (tot, hs, as_, side) in enumerate(out, 1):
        if tot != k:
            return None
        moved = "H" if (hs - prev_h, as_ - prev_a) == (1, 0) else (
            "A" if (hs - prev_h, as_ - prev_a) == (0, 1) else None)
        if moved != side:
            return None
        prev_h, prev_a = hs, as_
    return [g[3] for g in out]


def first_goal(goals: Sequence[str], goals_in_scope: int) -> str:
    """"H" / "A" / "N": the first goal's side when the scope (regulation, or
    period 1, by the period scores) holds any goal; "N" otherwise."""
    return goals[0] if goals_in_scope >= 1 and goals else "N"


def scoring_plays(payload: Any) -> list[tuple[int, int]] | None:
    """The running (home, away) score after each scoring play, in order, or
    None when it does not climb by 1..3 points a play from 0-0."""
    pts: set[tuple[int, int]] = set()
    for i in _incidents(payload):
        if i.get("incidentType") != "goal":
            continue
        hs, as_ = i.get("homeScore"), i.get("awayScore")
        if not isinstance(hs, int) or not isinstance(as_, int):
            return None
        pts.add((hs, as_))
    seq = sorted(pts, key=lambda p: (p[0] + p[1], p[0]))
    prev = (0, 0)
    for h, a in seq:
        dh, da = h - prev[0], a - prev[1]
        if not ((dh == 0 and 1 <= da <= 3) or (da == 0 and 1 <= dh <= 3)):
            return None
        prev = (h, a)
    return seq


def race_winner(plays: Sequence[tuple[int, int]], x: int) -> str | None:
    """"H" / "A": the side whose running score reaches `x` first; None when
    neither does."""
    for h, a in plays:
        if h >= x:
            return "H"
        if a >= x:
            return "A"
    return None


def play_sizes(plays: Sequence[tuple[int, int]]) -> list[int]:
    out: list[int] = []
    prev = (0, 0)
    for h, a in plays:
        out.append((h - prev[0]) + (a - prev[1]))
        prev = (h, a)
    return out


# --- the model's probabilities ---------------------------------------------

def hockey_first_goal_probs(eh: Sequence[float], ea: Sequence[float],
                            periods: int) -> dict[str, float]:
    """P(home first), P(away first), P(no goal) over the first `periods`
    regulation periods, the sides' goals independent Poisson processes."""
    p_h = p_a = 0.0
    alive = 1.0
    for k in range(periods):
        h, a = max(eh[k], 0.0), max(ea[k], 0.0)
        tot = h + a
        if tot <= 0:
            continue
        hit = alive * (1.0 - math.exp(-tot))
        p_h += hit * h / tot
        p_a += hit * a / tot
        alive *= math.exp(-tot)
    return {"H": p_h, "A": p_a, "N": alive}


def race_probs(shares: Sequence[float], sizes: Sequence[float],
               xs: Sequence[int], rng: random.Random) -> dict[int, float]:
    """P(home reaches x first) for each x: per draw a home share q, scoring
    plays home with probability q, worth 1 / 2 / 3 with weights `sizes`."""
    top = max(xs)
    wins = dict.fromkeys(xs, 0)
    cum = [sizes[0], sizes[0] + sizes[1], sum(sizes)]
    for q in shares:
        h = a = 0
        pending = sorted(xs)
        while pending and max(h, a) < top + 1:
            u = rng.random() * cum[2]
            pts = 1 if u < cum[0] else (2 if u < cum[1] else 3)
            if rng.random() < q:
                h += pts
            else:
                a += pts
            while pending and (h >= pending[0] or a >= pending[0]):
                if h >= pending[0]:
                    wins[pending[0]] += 1
                pending.pop(0)
    n = max(len(shares), 1)
    return {x: wins[x] / n for x in xs}


# --- scoring ----------------------------------------------------------------

@dataclass
class Market:
    """One market's walk-forward record: per game the model's and the base's
    class probabilities and the outcome."""
    classes: tuple[str, ...]
    rows: list[tuple[dict[str, float], dict[str, float], str]] = field(
        default_factory=list)
    counts: dict[str, float] = field(default_factory=dict)

    def base(self) -> dict[str, float]:
        tot = sum(self.counts.get(c, 0.0) + 1.0 for c in self.classes)
        return {c: (self.counts.get(c, 0.0) + 1.0) / tot for c in self.classes}

    def add(self, model_p: Mapping[str, float], outcome: str) -> None:
        self.rows.append((dict(model_p), self.base(), outcome))
        self.counts[outcome] = self.counts.get(outcome, 0.0) + 1.0


def _ll(p: float) -> float:
    return -math.log(min(max(p, EPS), 1.0 - EPS))


def summarise(m: Market, seed: int = 7) -> dict[str, Any]:
    """Log-loss model - base (game bootstrap), the side rows' calibration."""
    if not m.rows:
        return {"games": 0}
    diffs = [_ll(mp[y]) - _ll(bp[y]) for mp, bp, y in m.rows]
    model_ll = sum(_ll(mp[y]) for mp, _, y in m.rows) / len(m.rows)
    base_ll = sum(_ll(bp[y]) for _, bp, y in m.rows) / len(m.rows)
    rng = random.Random(seed)
    boots = []
    n = len(diffs)
    for _ in range(BOOTSTRAP):
        boots.append(sum(diffs[rng.randrange(n)] for _ in range(n)) / n)
    boots.sort()
    side_rows = [(mp[c], int(y == c)) for mp, _, y in m.rows
                 for c in m.classes if c != "N"]
    buckets: dict[int, list[int]] = {}
    psum: dict[int, float] = {}
    for p, y in side_rows:
        b = bucket_of(p)
        buckets.setdefault(b, []).append(y)
        psum[b] = psum.get(b, 0.0) + p
    cal = []
    for b in sorted(buckets):
        ys = buckets[b]
        cal.append({"bucket": f"{EDGES[b]:.3f}-{EDGES[b + 1]:.3f}", "n": len(ys),
                    "mean_p": round(psum[b] / len(ys), 4),
                    "realised": round(sum(ys) / len(ys), 4),
                    "wilson_lo": round(wilson_lo(sum(ys), len(ys)), 4)})
    hi = [(p, y) for p, y in side_rows if p >= PRINTABLE]
    k_hi = sum(y for _, y in hi)
    return {
        "games": n,
        "outcome_share": {c: round(sum(1 for *_, y in m.rows if y == c) / n, 4)
                          for c in m.classes},
        "logloss_model": round(model_ll, 5), "logloss_base": round(base_ll, 5),
        "diff": round(sum(diffs) / n, 5),
        "diff_ci95": [round(boots[int(0.025 * BOOTSTRAP)], 5),
                      round(boots[int(0.975 * BOOTSTRAP) - 1], 5)],
        "side_rows": len(side_rows),
        "share_ge_070": round(len(hi) / len(side_rows), 4) if side_rows else 0.0,
        "ge_070": {"n": len(hi),
                   "mean_p": round(sum(p for p, _ in hi) / len(hi), 4) if hi else None,
                   "realised": round(k_hi / len(hi), 4) if hi else None,
                   "wilson_lo": round(wilson_lo(k_hi, len(hi)), 4) if hi else None},
        "calibration": cal,
    }


# --- the replay ---------------------------------------------------------------

def model_probs(sport: ShadowSport, model: ScoreModel, r: FootballResult,
                n_sims: int, sizes: Sequence[float]) -> dict[str, dict[str, float]]:
    """market -> class probabilities of one game as of the model, or {} when
    the model has no expectation (thin side, no league rate, UNLINKED)."""
    exp = model.expected(r.competition_id, r.home_id, r.away_id, r.ts)
    if exp is None or model.no_league_rate(r.competition_id):
        return {}
    eh, ea = exp
    if sport.key == "hockey":
        return {"first_goal": hockey_first_goal_probs(eh, ea, 3),
                "first_goal_p1": hockey_first_goal_probs(eh, ea, 1)}
    sims = model.simulate(eh, ea, seed=r.event_id, n=n_sims,
                          noise_mult=model.noise_mult(r.home_id, r.away_id, r.ts))
    shares = [sum(s.t1_periods) / max(sum(s.t1_periods) + sum(s.t2_periods), 1)
              for s in sims]
    probs = race_probs(shares, sizes, RACE_XS, random.Random(r.event_id))
    return {f"race_{x}": {"H": probs[x], "A": 1.0 - probs[x]} for x in RACE_XS}


def load_incidents(db_path: str, ids: Iterable[int]) -> dict[int, Any]:
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.execute("PRAGMA busy_timeout = 60000")
    try:
        con.execute("CREATE TEMP TABLE want (id INTEGER PRIMARY KEY)")
        con.executemany("INSERT INTO want VALUES (?)", [(i,) for i in ids])
        return {int(eid): json.loads(payload) for eid, payload in con.execute(
            "SELECT x.sofascore_event_id, x.payload_json FROM sofa_event_extra x "
            "JOIN want w ON w.id = x.sofascore_event_id WHERE x.kind = 'incidents'")}
    finally:
        con.close()


def replay(history: Sequence[HistoryGame], sport: ShadowSport,
           incidents: Mapping[int, Any], n_sims: int = N_SIMS,
           dist_start_ts: int | None = None,
           ) -> tuple[dict[str, Market], dict[str, Any]]:
    """The walk-forward records of the games with incidents, and in `stats`
    `dist`: per market, how many side rows of EVERY rated game from
    `dist_start_ts` (incidents or not - the model needs none) reach 0.70."""
    markets: dict[str, Market] = {}
    if sport.key == "hockey":
        markets["first_goal"] = Market(("H", "A", "N"))
        markets["first_goal_p1"] = Market(("H", "A", "N"))
    else:
        for x in RACE_XS:
            markets[f"race_{x}"] = Market(("H", "A"))
    stats: dict[str, Any] = {"with_incidents": 0, "unparsed": 0,
                             "no_score_detail": 0, "inconsistent": 0,
                             "no_model": 0, "scored": 0}
    dist: dict[str, list[int]] = {k: [0, 0] for k in markets}
    targets = [g for g in history if incidents.get(g.rating.event_id)]
    if not targets:
        return markets, stats
    start = targets[0].rating.ts
    if dist_start_ts is not None:
        start = min(start, dist_start_ts)
    window = [g for g in history if g.rating.ts >= start]
    ratings = [g.rating for g in history]
    size_counts = [1.0, 1.0, 1.0]
    model: ScoreModel | None = None
    next_rebuild = start
    i = 0
    while i < len(window):
        ts = window[i].rating.ts
        j = i
        while j < len(window) and window[j].rating.ts == ts:
            j += 1
        batch = window[i:j]
        if model is None or ts >= next_rebuild:
            model = build_model(ratings, sport, ts, strict_league_rate=True)
            next_rebuild = ts + REBUILD_DAYS * 86400
            if sport.key == "basketball" and model.recent is None:
                model.recent = {}
        learnt_sizes: list[int] = []
        for g in batch:
            payload = incidents.get(g.rating.event_id)
            if dist_start_ts is not None and g.rating.ts >= dist_start_ts:
                sizes = (size_counts if sum(size_counts) > MIN_LEARNT_PLAYS
                         else list(DEFAULT_PLAY_SIZES))
                for name, probs in model_probs(sport, model, g.rating, n_sims,
                                               sizes).items():
                    sides = [v for c, v in probs.items() if c != "N"]
                    dist[name][0] += len(sides)
                    dist[name][1] += sum(1 for v in sides if v >= PRINTABLE)
            if not payload:
                continue
            stats["with_incidents"] += 1
            r = g.rating
            if sport.key == "hockey":
                goals = hockey_goals(payload)
                if goals is None:
                    stats["unparsed"] += 1
                    continue
                res = g.result
                if res is not None and not goals and res.t1_full + res.t2_full:
                    stats["no_score_detail"] += 1  # periods only, no goals
                    continue
                if res is None or len(goals) != res.t1_full + res.t2_full \
                        and len(goals) != sum(res.t1_periods) + sum(res.t2_periods):
                    stats["inconsistent"] += 1
                    continue
                reg_goals = sum(res.t1_periods) + sum(res.t2_periods)
                p1_goals = res.t1_periods[0] + res.t2_periods[0]
                got = model_probs(sport, model, r, n_sims, size_counts)
                if not got:
                    stats["no_model"] += 1
                    continue
                markets["first_goal"].add(got["first_goal"],
                                          first_goal(goals, reg_goals))
                markets["first_goal_p1"].add(got["first_goal_p1"],
                                             first_goal(goals, p1_goals))
                stats["scored"] += 1
                continue
            plays = scoring_plays(payload)
            res = g.result
            if plays is None:
                stats["unparsed"] += 1
                continue
            if not plays:
                stats["no_score_detail"] += 1  # periods only, no scoring plays
                continue
            if res is None or plays[-1] != (res.t1_full, res.t2_full):
                stats["inconsistent"] += 1
                continue
            learnt_sizes += play_sizes(plays)
            got = model_probs(sport, model, r, n_sims, size_counts)
            if not got:
                stats["no_model"] += 1
                continue
            for x in RACE_XS:
                won = race_winner(plays, x)
                if won is not None:
                    markets[f"race_{x}"].add(got[f"race_{x}"], won)
            stats["scored"] += 1
        for s in learnt_sizes:
            if 1 <= s <= 3:
                size_counts[s - 1] += 1.0
        for g in batch:
            model.book.update(_rated_values(g.rating, sport))
            model.note_game(g.rating)
            if model.last_played is not None:
                model.last_played[g.rating.home_id] = g.rating.ts
                model.last_played[g.rating.away_id] = g.rating.ts
            if model.recent is not None:
                model.recent.setdefault(g.rating.home_id, []).append(g.rating.ts)
                model.recent.setdefault(g.rating.away_id, []).append(g.rating.ts)
        i = j
    stats["dist"] = {k: {"side_rows": v[0], "ge_070": v[1],
                         "share": round(v[1] / v[0], 4) if v[0] else None}
                     for k, v in dist.items()}
    total = sum(size_counts)
    stats["play_size_share"] = [round(c / total, 4) for c in size_counts]
    return markets, stats


def to_markdown(sport: str, out: Mapping[str, Any]) -> str:
    lines = [f"## {sport}", "", f"- dane: {json.dumps(out['stats'])}", ""]
    for name, s in out["markets"].items():
        if not s.get("games"):
            lines.append(f"- {name}: brak gier")
            continue
        lines += [
            f"### {name}", "",
            f"- gry {s['games']}, wyniki {s['outcome_share']}",
            f"- log-loss model {s['logloss_model']} / baza {s['logloss_base']}, "
            f"różnica {s['diff']} [{s['diff_ci95'][0]}, {s['diff_ci95'][1]}]",
            f"- wiersze stron {s['side_rows']}, >= 0.70: {s['share_ge_070']} "
            f"({s['ge_070']})", "",
            "| koszyk | n | śr. p | zrealizowane | Wilson dolna |",
            "|---|---|---|---|---|"]
        lines += [f"| {c['bucket']} | {c['n']} | {c['mean_p']} | {c['realised']} | "
                  f"{c['wilson_lo']} |" for c in s["calibration"]]
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--sport", choices=("hockey", "basketball"), required=True)
    ap.add_argument("--sims", type=int, default=N_SIMS)
    ap.add_argument("--dist-days", type=int, default=120,
                    help="the >= 0.70 share over every rated game of these days")
    ap.add_argument("--json-out", default=None)
    ap.add_argument("--md-out", default=None)
    args = ap.parse_args()
    sport = SPORTS[args.sport]
    db = SofaConfig.from_env().db_path
    history = parse_history(load_events(db, sport), sport)
    incidents = load_incidents(db, [g.rating.event_id for g in history])
    last_ts = history[-1].rating.ts if history else 0
    markets, stats = replay(history, sport, incidents, args.sims,
                            last_ts - args.dist_days * 86400)
    out = {"sport": args.sport, "history_games": len(history),
           "incident_rows": len(incidents), "stats": stats,
           "markets": {k: summarise(m) for k, m in markets.items()}}
    print(json.dumps(out, indent=1))
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(out, indent=1), encoding="utf-8")
    if args.md_out:
        Path(args.md_out).write_text(to_markdown(args.sport, out), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
