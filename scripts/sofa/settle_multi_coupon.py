#!/usr/bin/env python3
"""Grade WARIANT WSZYSTKIE at its printed prices, section by section.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/settle_multi_coupon.py \\
        --from 2026-09-30 --to 2026-09-30

- official section: its singles and builders are graded exactly as
  audit_settlement 7c grades the PDF - the same 07_settled.json rows, the
  same key, the same slip rule (one lost leg loses the slip), the builder's
  screen price where 09_screen_prices.json has it, else the haircut estimate;
- each sport section: sport_coupon.grade_coupon on the stored results.

Writes runs/sofa/multi/<d>/multi_coupon_settled.json and prints one table.
The variant's total is its own; it is never added to the coupon (7c), to
WARIANT (7d), or to a sport coupon's result reported elsewhere. Offline.
Exit 0 all graded, 1 something pending or unreadable.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import multi_coupon as mc  # noqa: E402
from bet.sofa.confidence import builder_odds  # noqa: E402
from bet.sofa.config import SofaConfig  # noqa: E402
from bet.sofa.cs2 import write_atomic  # noqa: E402
from scripts.sofa.audit_settlement import _key, slip_status  # noqa: E402
from scripts.sofa.settle_sport_coupon import days, is_pending  # noqa: E402


def grade_confidence_positions(
    singles: list[dict[str, Any]],
    builders: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    screen: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Printed confidence singles and builders graded as audit_settlement 7c /
    7d grade them: the same key, PUSH not counted, one lost leg loses a slip,
    a builder at its screen price when recorded, else the haircut estimate.

    Each position is a dict with the artifact row under `source`.
    """
    by_key = {_key(r): r for r in rows}
    graded_singles = []
    for p in singles:
        g = by_key.get(_key(p["source"]))
        if g is None:
            outcome = "PENDING"
        elif g["outcome"] == "PUSH":
            outcome = "VOID"
        else:
            outcome = str(g["outcome"])
        graded_singles.append(
            {**p, "odds": p["source"]["offered_odds"], "outcome": outcome}
        )
    graded_builders = []
    for b in builders:
        src = b["source"]
        outs = []
        for leg in src.get("legs") or []:
            g = by_key.get(
                _key({**leg, "sofascore_event_id": src["sofascore_event_id"]})
            )
            outs.append(None if g is None else g["outcome"])
        status = slip_status(outs)
        outcome = {"NIE WESZŁO": "LOSS", "WESZŁO": "WIN"}.get(status, "PENDING")
        real = screen.get(str(src["sofascore_event_id"]))
        odds = float(real) if real is not None else builder_odds(src["odds_if_product"])
        graded_builders.append(
            {**b, "outcome": outcome, "odds": odds, "odds_measured": real is not None}
        )
    return graded_singles, graded_builders


def official_rows(
    runs_dir: str, date: str
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """The day's 07_settled.json rows and 09_screen_prices.json (both may be
    absent: nothing settled yet, no screen price recorded)."""
    run = mc.official_dir(runs_dir, date)
    path = run / "07_settled.json"
    rows = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    screen_path = run / "09_screen_prices.json"
    screen = (
        json.loads(screen_path.read_text(encoding="utf-8"))
        if screen_path.exists()
        else {}
    )
    return rows, screen


def grade_official(
    runs_dir: str, date: str, section: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows, screen = official_rows(runs_dir, date)
    return grade_confidence_positions(
        section.get("singles", []), section.get("builders", []), rows, screen
    )


def settle_day(runs_dir: str, date: str) -> dict[str, Any] | None:
    out = mc.multi_dir(runs_dir, date)
    path = out / mc.MULTI_FILE
    if not path.exists():
        return None
    doc = json.loads(path.read_text(encoding="utf-8"))
    result: dict[str, Any] = {"date": date, "not_the_coupon": True, "sections": {}}
    everything: list[dict[str, Any]] = []
    for key, sec in doc["sections"].items():
        if sec["status"] != "OK":
            result["sections"][key] = {
                "status": sec["status"],
                "reason": sec.get("reason"),
            }
            continue
        if key == "official":
            singles, builders = grade_official(runs_dir, date, sec)
            graded = singles + builders
            result["sections"][key] = {
                "singles": mc.summarize_units(singles),
                "builders": mc.summarize_units(builders),
                "rows": graded,
            }
        else:
            legs = mc.grade_sport_section(runs_dir, key, date, sec)
            graded = [{"section": key, **leg} for leg in legs]
            result["sections"][key] = {
                "singles": mc.summarize_units(graded),
                "rows": graded,
            }
        everything += graded
    result["variant_total"] = mc.summarize_units(everything)
    write_atomic(
        out / mc.MULTI_SETTLED, json.dumps(result, ensure_ascii=False, indent=2)
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--from", dest="start", required=True)
    parser.add_argument("--to", dest="end", required=True)
    args = parser.parse_args()
    runs_dir = SofaConfig.from_env().runs_dir
    print(
        f"# WARIANT WSZYSTKIE {args.start}..{args.end} (NOT the coupon; never pooled)\n"
    )
    print(
        "| day | section | positions | settled | won | lost | not counted "
        "| units | ROI |"
    )
    print("|---|---|---|---|---|---|---|---|---|")
    open_rows = 0
    for day in days(args.start, args.end):
        try:
            res = settle_day(runs_dir, day)
        except (OSError, ValueError, KeyError) as exc:
            print(f"| {day} | bad file: {type(exc).__name__}: {exc} |")
            open_rows += 1
            continue
        if res is None:
            continue
        for key, sec in res["sections"].items():
            if "rows" not in sec:
                print(f"| {day} | {key} | excluded: {sec.get('reason')} |")
                continue
            for part in ("singles", "builders"):
                s = sec.get(part)
                if s is None or (part == "builders" and not s["positions"]):
                    continue
                roi = "-" if s["roi"] is None else f"{s['roi']:+.1%}"
                print(
                    f"| {day} | {key} {part} | {s['positions']} | {s['settled']} | "
                    f"{s['won']} | {s['lost']} | {s['not_counted']} | "
                    f"{s['units']:+.2f} | {roi} |"
                )
            open_rows += sum(1 for r in sec["rows"] if is_pending(str(r["outcome"])))
        t = res["variant_total"]
        roi = "-" if t["roi"] is None else f"{t['roi']:+.1%}"
        print(
            f"| {day} | **variant total** | {t['positions']} | {t['settled']} | "
            f"{t['won']} | {t['lost']} | {t['not_counted']} | "
            f"{t['units']:+.2f} | {roi} |"
        )
    return 1 if open_rows else 0


if __name__ == "__main__":
    sys.exit(main())
