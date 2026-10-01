#!/usr/bin/env python3
"""Which devig describes the outcomes? Power vs proportional vs Shin.

Superbet's two-way pairs are devigged three ways and each side's probability
is scored (Brier) against how the line settled:

  * power        - p_i = q_i^k with sum 1 (engine.DEVIG_METHOD, sofa's);
  * proportional - p_i = q_i / sum q;
  * shin         - Shin (1993): the margin as insider trading, solved for z;

plus the "worst case" a cautious reader would use - the lowest of the three
for the side. Sources: the shadow sports' and CS2's graded lines (both sides
recorded) and football/tennis sheet rungs (OVER and UNDER rows of one rung)
joined to sofa_settled_row. Reported per sport and family with a bootstrap
interval over matches for (method - power). An analysis tool; it writes
nothing the pipeline reads.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_devig.py --from <d> --to <d>
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import os
import random
import sqlite3
import sys
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from bet.sofa.config import SofaConfig
from bet.sofa.engine import devig_many

METHODS = ("power", "proportional", "shin", "worst")


def shin(implied: list[float]) -> list[float] | None:
    """Shin's probabilities for a complete market (bisection on z)."""
    total = sum(implied)
    if total <= 1.0:
        return [q / total for q in implied]

    def probs(z: float) -> list[float]:
        return [(math.sqrt(z * z + 4 * (1 - z) * q * q / total) - z) / (2 * (1 - z))
                for q in implied]

    lo, hi = 0.0, 0.5
    for _ in range(80):
        z = (lo + hi) / 2
        if sum(probs(z)) > 1.0:
            lo = z
        else:
            hi = z
    p = probs((lo + hi) / 2)
    s = sum(p)
    return [x / s for x in p]


def all_methods(odds: list[float]) -> dict[str, list[float]] | None:
    if len(odds) < 2 or any(o <= 1.0 for o in odds):
        return None
    implied = [1.0 / o for o in odds]
    power = devig_many(implied, "power")
    prop = devig_many(implied, "proportional")
    sh = shin(implied)
    if power is None or prop is None or sh is None:
        return None
    worst = [min(a, b, c) for a, b, c in zip(power, prop, sh, strict=True)]
    return {"power": power, "proportional": prop, "shin": sh, "worst": worst}


def _days(a: str, b: str) -> list[str]:
    d0 = datetime.strptime(a, "%Y-%m-%d").replace(tzinfo=UTC)
    d1 = datetime.strptime(b, "%Y-%m-%d").replace(tzinfo=UTC)
    return [(d0 + timedelta(days=i)).strftime("%Y-%m-%d")
            for i in range((d1 - d0).days + 1)]


def graded_rows(runs: Path, days: list[str]) -> list[dict[str, Any]]:
    """(sport, family, game, odds side, odds other, y) from graded two-ways."""
    out: list[dict[str, Any]] = []
    for day in days:
        for path in glob.glob(str(runs / "shadow" / "*" / day / "settled.json")) + [
                str(runs / "cs2" / day / "settled.json")]:
            try:
                doc = json.loads(Path(path).read_text())
            except (OSError, ValueError):
                continue
            sport = doc.get("sport") or "cs2"
            events = doc.get("events", {})
            for eid, e in (events.items() if isinstance(events, dict) else []):
                if not isinstance(e, dict):
                    continue
                for g in e.get("graded", []):
                    if g.get("outcome") not in ("WIN", "LOSS"):
                        continue
                    if g.get("odds") is None or g.get("partner_odds") is None:
                        continue
                    group = g.get("group_odds")
                    if isinstance(group, dict) and len(group) > 2:
                        continue
                    out.append({"sport": sport, "family": g.get("family"),
                                "game": f"{day}:{eid}",
                                "odds": [g["odds"], g["partner_odds"]],
                                "y": 1.0 if g["outcome"] == "WIN" else 0.0})
    return out


def sheet_rows(runs: Path, days: list[str], db_path: str) -> list[dict[str, Any]]:
    """Football and tennis rungs priced both ways, joined to their settle."""
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.execute("PRAGMA busy_timeout = 60000")
    out: list[dict[str, Any]] = []
    for day in days:
        path = runs / day / "05_sheet.json"
        if not path.exists():
            continue
        settled = {(e, m, s, ln, d): o for e, m, s, ln, d, o in con.execute(
            "SELECT sofascore_event_id, market, subject, line, direction, outcome "
            "FROM sofa_settled_row WHERE run_date = ?", (day,))}
        rungs: dict[tuple[Any, ...], dict[str, Any]] = defaultdict(dict)
        for r in json.loads(path.read_text()):
            if r.get("offered_odds") is None:
                continue
            key = (r["sofascore_event_id"], r["market"], r.get("subject") or "",
                   r["line"])
            rungs[key][r["direction"]] = r
        for (eid, market, subject, line), sides in rungs.items():
            if set(sides) != {"OVER", "UNDER"}:
                continue
            o = settled.get((eid, market, subject, line, "OVER"))
            if o not in ("WIN", "LOSS"):
                continue
            out.append({"sport": sides["OVER"]["sport"], "family": market,
                        "game": f"{day}:{eid}",
                        "odds": [sides["OVER"]["offered_odds"],
                                 sides["UNDER"]["offered_odds"]],
                        "y": 1.0 if o == "WIN" else 0.0})
    con.close()
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--from", dest="date_from", required=True)
    ap.add_argument("--to", dest="date_to", required=True)
    ap.add_argument("--runs-dir", default=os.environ.get("SOFA_RUNS_DIR", "runs/sofa"))
    args = ap.parse_args()
    days = _days(args.date_from, args.date_to)
    runs = Path(args.runs_dir)
    db_path = SofaConfig.from_env().db_path
    rows = graded_rows(runs, days) + sheet_rows(runs, days, db_path)
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        ps = all_methods([float(x) for x in r["odds"]])
        if ps is None:
            continue
        r["p"] = {m: v[0] for m, v in ps.items()}
        groups[r["sport"]].append(r)
        groups["ALL"].append(r)
    rng = random.Random(7)
    print(f"# devig vs outcomes {args.date_from}..{args.date_to} "
          "(Brier, lower is better)")
    print("| sport | sides | matches | power | proportional | shin | worst | "
          "best | best-power [95% by match] |")
    print("|---|---|---|---|---|---|---|---|---|")
    for sport, rs in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        n = len(rs)
        br = {m: sum((r["p"][m] - r["y"]) ** 2 for r in rs) / n for m in METHODS}
        best = min(("power", "proportional", "shin"), key=lambda m: br[m])
        by_game: dict[str, list[float]] = defaultdict(list)
        for r in rs:
            by_game[r["game"]].append((r["p"][best] - r["y"]) ** 2
                                      - (r["p"]["power"] - r["y"]) ** 2)
        games = list(by_game)
        stats = []
        for _ in range(1000):
            pick = [games[rng.randrange(len(games))] for _ in games]
            stats.append(sum(sum(by_game[g]) for g in pick)
                         / sum(len(by_game[g]) for g in pick))
        stats.sort()
        diff = sum(sum(v) for v in by_game.values()) / n
        print(f"| {sport} | {n} | {len(games)} | " + " | ".join(
            f"{br[m]:.5f}" for m in METHODS)
            + f" | {best} | {diff:+.5f} [{stats[25]:+.5f}, {stats[975]:+.5f}] |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
