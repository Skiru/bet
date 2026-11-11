#!/usr/bin/env python3
"""Read-only: do lesser-loss legs (bet.sofa.lesser_loss) lose less?

Joins every printed single of 11_coupon.json to its grade in 13_results.json
(WIN / LOSS only; refund / void / unknown out) and reports, before the 12%
tax, the realised hit, mean 1/odds and ROI with a match-bootstrap 95%
interval for: every leg, the marked legs (lesser_loss.annotate, recomputed
from the leg's own fields - the same rule whether the day carried the mark
or not), the "pewna" tier, and the marked legs by confidence band. The
window is split at --split (dev before, hold-out from it). Days are pooled
across ledger epoch groups - a view of the printed legs, never the ledger.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_lesser_loss.py \
        --from 2026-10-30 --to 2026-11-10 --split 2026-11-05

Forward judgement of T-LESSER-LOSS-flag: --from 2026-11-12 with no --split.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import lesser_loss as ll  # noqa: E402
from bet.sofa.coupon_results import key_of  # noqa: E402

Row = dict[str, Any]


def load_rows(runs: Path, start: str, end: str) -> list[Row]:
    rows: list[Row] = []
    for day_dir in sorted(p for p in runs.iterdir() if p.is_dir()):
        day = day_dir.name
        if not (start <= day <= end):
            continue
        res_path, cpn_path = day_dir / "13_results.json", day_dir / "11_coupon.json"
        if not (res_path.exists() and cpn_path.exists()):
            continue
        graded = json.loads(res_path.read_text(encoding="utf-8")).get("legs") or {}
        singles = json.loads(cpn_path.read_text(encoding="utf-8")).get("singles") or []
        for leg in singles:
            try:
                g = graded.get(key_of(leg))
            except (KeyError, TypeError, ValueError):
                continue
            if not g or g.get("status") not in ("won", "lost"):
                continue
            mark = ll.annotate({**leg, "confidence": g["confidence"],
                                "offered_odds": g["odds"]})
            rows.append({
                "day": day, "event": (day, leg.get("sofascore_event_id")),
                "sport": g.get("sport"), "won": g["status"] == "won",
                "odds": float(g["odds"]), "confidence": float(g["confidence"]),
                "tier": None if mark is None else mark["tier"],
            })
    return rows


def _roi(rows: list[Row]) -> float:
    return sum((r["odds"] - 1.0) if r["won"] else -1.0 for r in rows) / len(rows)


def summary(rows: list[Row], boots: int = 1000, seed: int = 11) -> str:
    if not rows:
        return "n=0"
    by_event: dict[Any, list[Row]] = defaultdict(list)
    for r in rows:
        by_event[r["event"]].append(r)
    events = list(by_event.values())
    rng = random.Random(seed)
    draws = sorted(_roi([r for e in rng.choices(events, k=len(events)) for r in e])
                   for _ in range(boots))
    lo, hi = draws[int(0.025 * boots)], draws[int(0.975 * boots) - 1]
    n = len(rows)
    hit = sum(r["won"] for r in rows) / n
    price = sum(1.0 / r["odds"] for r in rows) / n
    conf = sum(r["confidence"] for r in rows) / n
    return (f"n={n} meczów={len(events)} weszło={hit:.3f} pewność={conf:.3f} "
            f"1/kurs={price:.3f} ROI={100 * _roi(rows):+.1f}% "
            f"[{100 * lo:+.1f}; {100 * hi:+.1f}]")


GROUPS: list[tuple[str, Callable[[Row], bool]]] = [
    ("wszystkie nogi", lambda r: True),
    ("mniej złe (oba stopnie)", lambda r: r["tier"] is not None),
    ("mniej złe, pewność < 0,85", lambda r: r["tier"] == "mniej_zla"),
    ("PEWNE mniej złe (pewność >= 0,85)", lambda r: r["tier"] == "pewna"),
    ("mniej złe, pewność 0,80-0,85",
     lambda r: r["tier"] is not None and 0.80 <= r["confidence"] < 0.85),
    ("nieoznaczone", lambda r: r["tier"] is None),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--from", dest="start", required=True)
    ap.add_argument("--to", dest="end", required=True)
    ap.add_argument("--split", default=None,
                    help="first hold-out day; dev is every day before it")
    ap.add_argument("--runs-dir", default=str(_REPO / "runs" / "sofa"))
    args = ap.parse_args()
    rows = load_rows(Path(args.runs_dir), args.start, args.end)
    if not rows:
        print("no graded printed singles in the window", file=sys.stderr)
        return 1
    parts: list[tuple[str, list[Row]]] = [(f"{args.start}..{args.end}", rows)]
    if args.split:
        parts = [(f"dev {args.start}..<{args.split}",
                  [r for r in rows if r["day"] < args.split]),
                 (f"hold-out {args.split}..{args.end}",
                  [r for r in rows if r["day"] >= args.split])]
    for title, part in parts:
        print(f"\n## {title} (przed podatkiem 12%)")
        for name, keep in GROUPS:
            print(f"- {name}: {summary([r for r in part if keep(r)])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
