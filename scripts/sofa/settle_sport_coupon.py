#!/usr/bin/env python3
"""Grade the experimental per-sport coupons against the measurement's settles.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/settle_sport_coupon.py \\
        --from 2026-09-30 --to 2026-09-30 [--sport hockey]

Reads each day's sport_coupon.json and the settled.json that CS2_SETTLE /
SHADOW_SETTLE wrote beside it (run those first - they need the bridge; this
does not), grades every printed leg at the PRINTED price, writes
sport_coupon_settled.json next to the coupon, and prints one table per sport.

Each sport is reported on its own and never pooled with another, nor with the
coupon's result (audit_settlement 7c). Offline. Exit 0 when every leg is
graded, 1 when a leg is pending or a file
was unreadable (named in the table, the rest still graded).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import sport_coupon as sc  # noqa: E402
from bet.sofa.config import SofaConfig  # noqa: E402
from bet.sofa.cs2 import write_atomic  # noqa: E402

SETTLED_OUT = "sport_coupon_settled.json"


def days(start: str, end: str) -> list[str]:
    a, b = date.fromisoformat(start), date.fromisoformat(end)
    return [(a + timedelta(days=i)).isoformat() for i in range((b - a).days + 1)]


def settle_day(
    runs_dir: str, sport: sc.SportKey, day: str
) -> list[dict[str, Any]] | None:
    directory = sc.day_dir(runs_dir, sport, day)
    path = directory / sc.COUPON_FILE
    if not path.exists():
        return None
    coupon = json.loads(path.read_text(encoding="utf-8"))
    # A leg settles in the file its event was snapshotted in: D's, or D+1's
    # for a game after midnight UTC.
    sources = {leg.get("source_date") or day for leg in coupon.get("legs", [])}
    settled = {d: sc.load_settled(runs_dir, sport, d) for d in sources | {day}}
    graded = sc.grade_coupon(coupon, settled)
    write_atomic(
        directory / SETTLED_OUT,
        json.dumps(
            {
                "sport": sport,
                "date": day,
                "not_the_coupon": True,
                "graded_at": "printed price",
                "legs": graded,
            },
            ensure_ascii=False,
            indent=2,
        ),
    )
    return graded


def is_pending(outcome: str) -> bool:
    return outcome == "PENDING" or outcome.startswith("PENDING:")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--from", dest="start", required=True)
    parser.add_argument("--to", dest="end", required=True)
    parser.add_argument("--sport", choices=[*sc.SPORT_KEYS, "all"], default="all")
    args = parser.parse_args()
    runs_dir = SofaConfig.from_env().runs_dir
    sports = sc.SPORT_KEYS if args.sport == "all" else (args.sport,)
    print(
        f"# Experimental sport coupons {args.start}..{args.end} "
        "(NOT the coupon; never pooled)\n"
    )
    bad = pending_total = 0
    for sport in sports:
        print(f"## {sport}\n")
        print(
            "| day | legs | WIN | LOSS | void | ungraded | pending | hit "
            "| mean fair p | ROI (printed) |"
        )
        print("|---|---|---|---|---|---|---|---|---|---|")
        pooled: list[dict[str, Any]] = []
        for day in days(args.start, args.end):
            try:
                graded = settle_day(runs_dir, sport, day)
            except (OSError, ValueError, KeyError) as exc:
                # One bad file is named and skipped; the other days and sports
                # are still graded.
                print(f"| {day} | bad file: {type(exc).__name__}: {exc} |")
                bad += 1
                continue
            if graded is None:
                continue
            pooled += graded
            s = sc.summarize(graded)
            outcomes = [str(g["outcome"]) for g in graded]
            void = outcomes.count("VOID")
            pending = sum(1 for o in outcomes if is_pending(o))
            ungraded = len(outcomes) - s.get("n", 0) - void - pending
            pending_total += pending
            print(
                f"| {day} | {len(graded)} | {s.get('wins', 0)} | "
                f"{s.get('n', 0) - s.get('wins', 0)} | {void} | {ungraded} | "
                f"{pending} | "
                + (
                    f"{s['hit']:.1%} | {s['mean_fair_p']:.1%} | {s['roi']:+.1%} |"
                    if s.get("n")
                    else "- | - | - |"
                )
            )
        s = sc.summarize(pooled)
        if s.get("n"):
            print(
                f"| **all** | {len(pooled)} | {s['wins']} | {s['n'] - s['wins']} "
                f"| | | | {s['hit']:.1%} | {s['mean_fair_p']:.1%} | "
                f"{s['roi']:+.1%} |"
            )
        print()
    # 0 all graded; 1 something still pending or a file was unreadable.
    return 1 if bad or pending_total else 0


if __name__ == "__main__":
    sys.exit(main())
