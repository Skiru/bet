#!/usr/bin/env python3
"""Measure bet.sofa.score_model against Superbet's price on graded lines.

For each settled game of `--sport` on each `--date` (runs/sofa/shadow/<sport>/
<date>/settled.json), the model is rebuilt from history strictly before that
day, the game is simulated, and every graded non-player line gets the
model's probability beside Superbet's devigged `fair_p`. Reported per market
family: Brier of the price, of the model, and of blends, with a 95% interval
for (model - price) and (blend - price) from a bootstrap over GAMES - the
lines of one game are not independent, and a line count overstates the
evidence many times.

An analysis tool: it writes nothing the pipeline reads.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_score_model.py \\
        --sport hockey --date 2026-09-29
"""

from __future__ import annotations

import argparse
import json
import random
import sqlite3
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bet.sofa.config import SofaConfig
from bet.sofa.score_model import build_model, line_probability, load_history
from bet.sofa.shadow import MARKETS, SPORTS, ShadowLine

BLENDS = (0.25, 0.5)
BOOTSTRAP = 2000


def _event(con: sqlite3.Connection, eid: int) -> dict[str, Any] | None:
    for (events_json,) in con.execute(
        "SELECT events_json FROM sofa_entity_events WHERE kind = 'last' "
        "AND events_json LIKE ?", (f'%"id": {eid},%',)
    ):
        for event in json.loads(events_json).get("events", []):
            if event.get("id") == eid:
                return dict(event)
    return None


def _ci(
    diffs: dict[str, list[float]], rng: random.Random
) -> tuple[float, float, float]:
    games = list(diffs)
    if not games:
        return (0.0, 0.0, 0.0)
    total = sum(sum(v) for v in diffs.values())
    n = sum(len(v) for v in diffs.values())
    stats = []
    for _ in range(BOOTSTRAP):
        pick = [games[rng.randrange(len(games))] for _ in games]
        s = sum(sum(diffs[g]) for g in pick)
        c = sum(len(diffs[g]) for g in pick)
        stats.append(s / c if c else 0.0)
    stats.sort()
    return total / n, stats[int(0.025 * BOOTSTRAP)], stats[int(0.975 * BOOTSTRAP)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--sport", choices=sorted(SPORTS), required=True)
    ap.add_argument("--date", action="append", required=True)
    ap.add_argument("--runs-dir", default="runs/sofa")
    ap.add_argument("--json-out", default=None)
    ap.add_argument("--rows-out", default=None, help="every scored line, JSONL")
    args = ap.parse_args()
    sport = SPORTS[args.sport]
    config = SofaConfig.from_env()
    history = load_history(config.db_path, sport)
    con = sqlite3.connect(f"file:{config.db_path}?mode=ro", uri=True)
    con.execute("PRAGMA busy_timeout = 60000")
    rows: list[dict[str, Any]] = []
    skipped: dict[str, int] = defaultdict(int)
    for date in args.date:
        path = Path(args.runs_dir) / "shadow" / args.sport / date / "settled.json"
        doc = json.loads(path.read_text(encoding="utf-8"))
        cut = int(datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=UTC).timestamp())
        model = build_model(history, sport, cut)
        for sb_id, entry in doc["events"].items():
            if entry.get("state") != "SETTLED" or entry.get("orientation_unclear"):
                skipped["not_settled_or_unoriented"] += 1
                continue
            event = _event(con, int(entry["sofascore_event_id"]))
            if event is None:
                skipped["no_cached_event"] += 1
                continue
            unique = (event.get("tournament") or {}).get("uniqueTournament") or {}
            comp = int(unique.get("id", event["tournament"]["id"]))
            exp = model.expected(comp, event["homeTeam"]["id"], event["awayTeam"]["id"])
            if exp is None:
                skipped["unrated"] += 1
                continue
            mh, ma = exp
            mu1, mu2 = (mh, ma) if entry.get("home_is_team1") else (ma, mh)
            games = model.simulate(mu1, mu2, seed=int(entry["sofascore_event_id"]))
            for g in entry.get("graded", []):
                if g.get("outcome") not in ("WIN", "LOSS") or g.get("fair_p") is None:
                    continue
                if g["market_id"] not in MARKETS[sport.key]:
                    continue
                line = ShadowLine(sb_id, g["market_id"], g["family"], g["period"],
                                  g.get("subject") or "", g.get("line"), g["side"],
                                  g["odds"])
                p = line_probability(line, games, sport)
                if p is None:
                    skipped["no_model_p"] += 1
                    continue
                rows.append({"game": f"{date}:{sb_id}", "family": g["family"],
                             "side": g["side"], "line": g.get("line"),
                             "p_model": p, "p_price": g["fair_p"],
                             "y": 1.0 if g["outcome"] == "WIN" else 0.0})
    if args.rows_out:
        Path(args.rows_out).write_text(
            "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    rng = random.Random(7)
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        groups["ALL"].append(r)
        groups[r["family"]].append(r)
    report: dict[str, Any] = {"sport": args.sport, "dates": args.date,
                              "skipped": dict(skipped), "families": {}}
    print(f"{args.sport} {args.date} lines={len(rows)} "
          f"games={len({r['game'] for r in rows})} skipped={dict(skipped)}")
    print(f"{'family':22s} {'lines':>6s} {'games':>5s} {'price':>7s} {'model':>7s} "
          + " ".join(f"{'b' + str(w):>7s}" for w in BLENDS)
          + "   model-price [95%]      b0.25-price [95%]")
    for fam, rs in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        if len(rs) < 30 and fam != "ALL":
            continue
        n = len(rs)
        bp = sum((r["p_price"] - r["y"]) ** 2 for r in rs) / n
        bm = sum((r["p_model"] - r["y"]) ** 2 for r in rs) / n
        bb = [sum(((w * r["p_model"] + (1 - w) * r["p_price"]) - r["y"]) ** 2
                  for r in rs) / n for w in BLENDS]
        dm: dict[str, list[float]] = defaultdict(list)
        db: dict[str, list[float]] = defaultdict(list)
        for r in rs:
            base = (r["p_price"] - r["y"]) ** 2
            dm[r["game"]].append((r["p_model"] - r["y"]) ** 2 - base)
            blend = 0.25 * r["p_model"] + 0.75 * r["p_price"]
            db[r["game"]].append((blend - r["y"]) ** 2 - base)
        m_ci, b_ci = _ci(dm, rng), _ci(db, rng)
        n_games = len({r["game"] for r in rs})
        print(f"{fam:22s} {n:6d} {n_games:5d} {bp:7.4f} {bm:7.4f} "
              + " ".join(f"{b:7.4f}" for b in bb)
              + f"   {m_ci[0]:+.4f} [{m_ci[1]:+.4f},{m_ci[2]:+.4f}]"
              + f"  {b_ci[0]:+.4f} [{b_ci[1]:+.4f},{b_ci[2]:+.4f}]")
        report["families"][fam] = {"lines": n, "games": n_games, "brier_price": bp,
                                   "brier_model": bm, "brier_blends": dict(zip(
                                       map(str, BLENDS), bb, strict=True)),
                                   "model_minus_price": m_ci,
                                   "blend25_minus_price": b_ci}
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(report, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
