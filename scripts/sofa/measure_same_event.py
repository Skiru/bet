#!/usr/bin/env python3
"""Read-only: the printed coupons with one leg per event (audit 2026-11-07).

Before epochs.SAME_EVENT_DEDUP_FROM_UTC two market names of one outcome both
printed (bet.sofa.leg_identity) and the ledger counted the outcome twice.
For each day this prints the official figures of the printed singles
(13_results.json) beside the same singles with each (match, event) counted
once - the leg leg_identity.dedupe keeps (the higher price, then the lower
confidence), as if every printed single had been fresh at one print. A
view, never the ledger; the days are printed one by one, never pooled across
epoch groups (audit_ledger.EPOCH_GROUPS).

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_same_event.py \
        --from 2026-10-13 --to 2026-11-06
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import leg_identity as li  # noqa: E402
from bet.sofa.coupon_results import key_of  # noqa: E402
from bet.sofa.superbet_names import board_sides  # noqa: E402


def _units(status: str, odds: float) -> float:
    return odds - 1.0 if status == "won" else -1.0


def day_figures(run: Path) -> dict[str, Any] | None:
    coupon_path, results_path = run / "11_coupon.json", run / "13_results.json"
    if not coupon_path.exists() or not results_path.exists():
        return None
    coupon = json.loads(coupon_path.read_text(encoding="utf-8"))
    results = json.loads(results_path.read_text(encoding="utf-8")).get("legs") or {}
    singles = [s for s in coupon.get("singles") or [] if isinstance(s, dict)]
    # every printed single as if all were fresh at one print: the leg the
    # rule keeps of an event is its best-priced one
    once, removed = li.dedupe([], singles, board_sides(run))

    def tally(legs: list[dict[str, Any]]) -> dict[str, float]:
        out = {"positions": 0.0, "settled": 0.0, "won": 0.0, "units": 0.0}
        for leg in legs:
            out["positions"] += 1
            got = results.get(key_of(leg)) or {}
            status = str(got.get("status") or "")
            if status in ("won", "lost"):
                odds = float(got.get("odds") or li.price(leg) or 0.0)
                out["settled"] += 1
                out["won"] += status == "won"
                out["units"] += _units(status, odds)
        return out

    return {"date": run.name, "official": tally(singles), "one_per_event": tally(once),
            "removed": len(removed)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--from", dest="start", required=True)
    parser.add_argument("--to", dest="end", required=True)
    parser.add_argument("--runs-dir", default="runs/sofa")
    args = parser.parse_args()
    day = dt.date.fromisoformat(args.start)
    end = dt.date.fromisoformat(args.end)
    print("| day | positions | settled | won | units | one per event: positions "
          "| settled | won | units | second legs |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    while day <= end:
        got = day_figures(Path(args.runs_dir) / day.isoformat())
        if got is not None:
            o, e = got["official"], got["one_per_event"]
            print(f"| {got['date']} | {o['positions']:.0f} | {o['settled']:.0f} | "
                  f"{o['won']:.0f} | {o['units']:+.2f} | {e['positions']:.0f} | "
                  f"{e['settled']:.0f} | {e['won']:.0f} | {e['units']:+.2f} | "
                  f"{got['removed']} |")
        day += dt.timedelta(days=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
