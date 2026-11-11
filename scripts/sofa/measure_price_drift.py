#!/usr/bin/env python3
"""Read-only: does Superbet's own price drift predict the outcome?

For every SHADOW line (hockey / basketball / volleyball) graded WIN / LOSS in
runs/sofa/shadow/<sport>/<day>/settled.json, the first pre-start quote of the
same line in that day's snapshots.jsonl is joined to the graded quote (the
last snapshot, with its devigged fair_p). drift = ln(first odds / graded odds)
(> 0: the price shortened). Reported per drift bin: realised hit minus mean
fair_p at the graded quote (match-bootstrap 95%), and ROI at the graded
price, split at --split (dev up to it, hold-out after). Before the tax.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_price_drift.py \
        --split 2026-10-25 [--min-fair 0.70]

Measured 2026-11-11: docs/sofa/evidence/ruch_kursu_superbet_2026-11-11.md.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
SPORTS = ("hockey", "basketball", "volleyball")
BINS: tuple[tuple[float, float, str], ...] = (
    (-9.0, -0.10, "wydłużył > 10%"), (-0.10, -0.03, "wydłużył 3-10%"),
    (-0.03, -0.005, "wydłużył < 3%"), (-0.005, 0.005, "bez ruchu"),
    (0.005, 0.03, "skrócił < 3%"), (0.03, 0.10, "skrócił 3-10%"),
    (0.10, 9.0, "skrócił > 10%"))
Row = dict[str, Any]
Key = tuple[Any, ...]


def _key(r: dict[str, Any]) -> Key:
    return (str(r.get("superbet_event_id")), r.get("market_id"), r.get("family"),
            r.get("period"), r.get("subject"), r.get("line"), r.get("side"))


def first_quotes(path: Path) -> dict[Key, float]:
    first: dict[Key, float] = {}
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            try:
                snap = json.loads(line)
            except ValueError:
                continue
            ko, at = snap.get("kickoff_utc"), snap.get("fetched_at_utc")
            if not ko or not at or at >= ko:
                continue
            for r in snap.get("lines") or []:
                odds = r.get("odds")
                if odds:
                    first.setdefault(_key(r), float(odds))
    return first


def load(root: Path) -> list[Row]:
    rows: list[Row] = []
    for sport in SPORTS:
        base = root / "shadow" / sport
        if not base.is_dir():
            continue
        for day_dir in sorted(p for p in base.iterdir() if p.is_dir()):
            settled, snaps = day_dir / "settled.json", day_dir / "snapshots.jsonl"
            if not (settled.exists() and snaps.exists()):
                continue
            first = first_quotes(snaps)
            events = json.loads(settled.read_text(encoding="utf-8")).get("events") or {}
            for e in events.values():
                for g in e.get("graded") or []:
                    if g.get("outcome") not in ("WIN", "LOSS"):
                        continue
                    if not g.get("fair_p") or not g.get("odds"):
                        continue
                    o0 = first.get(_key(g))
                    if not o0:
                        continue
                    rows.append({
                        "sport": sport, "day": day_dir.name,
                        "event": (day_dir.name, str(g.get("superbet_event_id"))),
                        "won": g["outcome"] == "WIN", "odds": float(g["odds"]),
                        "fair": float(g["fair_p"]),
                        "drift": math.log(o0 / float(g["odds"])),
                    })
    return rows


def summary(rows: list[Row], boots: int = 300, seed: int = 5) -> str:
    if len(rows) < 200:
        return f"n={len(rows)} (za mało)"
    by_event: dict[Any, list[Row]] = defaultdict(list)
    for r in rows:
        by_event[r["event"]].append(r)
    events = list(by_event.values())

    def gap(s: list[Row]) -> float:
        return float(sum(r["won"] - r["fair"] for r in s)) / len(s)

    rng = random.Random(seed)
    draws = sorted(gap([r for e in rng.choices(events, k=len(events)) for r in e])
                   for _ in range(boots))
    roi = sum((r["odds"] - 1.0) if r["won"] else -1.0 for r in rows) / len(rows)
    return (f"n={len(rows)} meczów={len(events)} trafienia−fair="
            f"{100 * gap(rows):+.2f} pp [{100 * draws[int(.025 * boots)]:+.2f}; "
            f"{100 * draws[int(.975 * boots) - 1]:+.2f}] ROI={100 * roi:+.1f}%")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--split", required=True, help="last dev day")
    ap.add_argument("--min-fair", type=float, default=0.0)
    ap.add_argument("--runs-dir", default=str(_REPO / "runs" / "sofa"))
    args = ap.parse_args()
    rows = [r for r in load(Path(args.runs_dir)) if r["fair"] >= args.min_fair]
    if not rows:
        print("no graded lines", file=sys.stderr)
        return 1
    for sport in (*SPORTS, "wszystkie"):
        for title, dev in (("dev", True), ("hold-out", False)):
            part = [r for r in rows
                    if (sport == "wszystkie" or r["sport"] == sport)
                    and (r["day"] <= args.split) == dev]
            print(f"\n## {sport} {title}")
            for lo, hi, name in BINS:
                cell = [r for r in part if lo <= r["drift"] < hi]
                print(f"- {name}: {summary(cell)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
