#!/usr/bin/env python3
"""Score bet.sofa.score_model on the cached results history - no prices.

Walk forward through the history: the model is built from everything before
`--start`, then each game from `--start` to `--end` is forecast from the
ratings as they stood before it (the book is updated after each game, as the
pipeline would have seen it) and simulated. Proper scores, against the real
game graded by the same shadow.build_result SETTLE uses:

  * winner     - Brier of P(team1 wins the game, overtime included);
  * total      - Brier of P(regulation total > t) at the TUNE window's
                 quartiles (+0.5), averaged over the thresholds;
  * margin     - the same for the regulation margin (home minus away);
  * team_total - the same for each side's own regulation score;
  * volleyball: sets total, set margin and points total in place of the
                three above.

The thresholds come from the history before --start, never from a price, so
the score measures the distribution itself. An analysis tool: it writes
nothing the pipeline reads.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_score_history.py \\
        --sport basketball --start 2026-07-15 --end 2026-09-29 \\
        --params '{"bb_game_sd": 2.0}'
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import pickle
import sqlite3
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bet.sofa.config import SofaConfig
from bet.sofa.football_rating import FootballResult
from bet.sofa.score_model import (
    SimParams,
    _rated_values,
    build_model,
    parse_event,
)
from bet.sofa.shadow import SPORTS, GameResult, ShadowSport, build_result


def _ts(day: str) -> int:
    return int(datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=UTC).timestamp())


def load(db_path: str, sport: ShadowSport, cache: str | None
         ) -> list[tuple[FootballResult, GameResult | None]]:
    """(rating input, the graded game) per finished game, in time order."""
    if cache and Path(cache).exists():
        data: list[tuple[FootballResult, GameResult | None]] = pickle.loads(
            Path(cache).read_bytes())
        return data
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.execute("PRAGMA busy_timeout = 60000")
    events: dict[int, dict[str, Any]] = {}
    try:
        for (events_json,) in con.execute(
            "SELECT events_json FROM sofa_entity_events WHERE kind = 'last' "
            "AND events_json LIKE ?", (f'%"slug": "{sport.sofascore_slug}"%',)
        ):
            for event in json.loads(events_json).get("events", []):
                if isinstance(event.get("id"), int):
                    events[event["id"]] = event
    finally:
        con.close()
    out: list[tuple[FootballResult, GameResult | None]] = []
    for e in events.values():
        r = parse_event(e, sport)
        if r is not None:
            out.append((r, build_result(e, sport, True)))
    out.sort(key=lambda x: (x[0].ts, x[0].event_id))
    if cache:
        Path(cache).write_bytes(pickle.dumps(out))
    return out


def _quartile_lines(values: list[float]) -> list[float]:
    vs = sorted(values)
    if not vs:
        return []
    return sorted({float(int(vs[int(q * (len(vs) - 1))])) + 0.5
                   for q in (0.25, 0.5, 0.75)})


def quantities(g: GameResult, sport: ShadowSport) -> dict[str, list[float]]:
    """family -> the game's values the thresholds are applied to."""
    if sport.regulation_periods is None:
        s1 = sum(1 for a, b in zip(g.t1_periods, g.t2_periods, strict=True) if a > b)
        s2 = len(g.t1_periods) - s1
        return {"sets_total": [s1 + s2], "set_margin": [s1 - s2],
                "points_total": [sum(g.t1_periods) + sum(g.t2_periods)]}
    r1, r2 = sum(g.t1_periods), sum(g.t2_periods)
    return {"total": [r1 + r2], "margin": [r1 - r2], "team_total": [r1, r2]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--sport", choices=sorted(SPORTS), required=True)
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--params", default="{}", help="SimParams overrides, JSON")
    ap.add_argument("--max-games", type=int, default=2500)
    ap.add_argument("--sims", type=int, default=600)
    ap.add_argument("--cache", default=None, help="pickle of the parsed history")
    args = ap.parse_args()
    sport = SPORTS[args.sport]
    params = dataclasses.replace(SimParams(), **json.loads(args.params))
    data = load(SofaConfig.from_env().db_path, sport, args.cache)
    start, end = _ts(args.start), _ts(args.end)
    history = [r for r, _ in data]
    model = build_model(history, sport, start, params)
    before = [gb for r, gb in data if r.ts < start and gb is not None]
    lines: dict[str, list[float]] = defaultdict(list)
    for gb in before[-20000:]:
        for fam, vals in quantities(gb, sport).items():
            lines[fam].extend(vals)
    thresholds = {fam: _quartile_lines(v) for fam, v in lines.items()}
    window = [(r, g) for r, g in data if start <= r.ts < end]
    step = max(1, len(window) // args.max_games)
    score: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
    last = model.last_played if model.last_played is not None else {}
    for i, (r, g) in enumerate(window):
        if i % step == 0 and g is not None:
            exp = model.expected(r.competition_id, r.home_id, r.away_id, r.ts)
            if exp is not None:
                sims = model.simulate(exp[0], exp[1], seed=r.event_id, n=args.sims)
                if g.winner is not None:
                    p = sum(1 for s in sims if s.winner == "T1") / len(sims)
                    y = 1.0 if g.winner == "T1" else 0.0
                    score["winner"][0] += (p - y) ** 2
                    score["winner"][1] += 1
                sim_q = [quantities(s, sport) for s in sims]
                for fam, actual in quantities(g, sport).items():
                    for k, a in enumerate(actual):
                        for t in thresholds.get(fam, []):
                            p = sum(1 for q in sim_q if q[fam][k] > t) / len(sims)
                            y = 1.0 if a > t else 0.0
                            score[fam][0] += (p - y) ** 2
                            score[fam][1] += 1
        model.book.update(_rated_values(r, sport))
        last[r.home_id] = r.ts
        last[r.away_id] = r.ts
    out = {f: round(v[0] / v[1], 5) for f, v in sorted(score.items()) if v[1]}
    games = int(score["winner"][1])
    print(json.dumps({"sport": args.sport, "params": json.loads(args.params),
                      "window": [args.start, args.end], "games": games,
                      "thresholds": thresholds, "brier": out,
                      "mean": round(sum(out.values()) / len(out), 5) if out else None}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
