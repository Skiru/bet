#!/usr/bin/env python3
"""Grade WARIANT WSZYSTKIE at its printed prices, section by section.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/settle_multi_coupon.py \\
        --from 2026-09-30 --to 2026-09-30

- official section: its singles and builders are graded exactly as
  audit_settlement 7c grades the PDF - the same settled rows, read from the
  database (sofa_settled_row, which regrade_settled.py corrects;
  07_settled.json is not corrected and is not read), the same key, the same
  slip rule (one lost leg loses the slip), the builder's screen price where
  09_screen_prices.json has it, else the haircut estimate;
- each sport section: sport_coupon.grade_coupon on the stored results.

Writes runs/sofa/multi/<d>/multi_coupon_settled.json and prints one table.
The variant's total is its own; it is never added to the coupon (7c), to
WARIANT (7d), or to a sport coupon's result reported elsewhere. Offline.
Exit 0 = graded as far as the settles allow (pending legs are shown), 1 = a
MISMATCH or an unreadable file, 2 = a crash.
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
from scripts.sofa.audit_settlement import (  # noqa: E402
    _key,
    settled_by_key,
    slip_status,
)
from scripts.sofa.settle_sport_coupon import days  # noqa: E402


def grade_confidence_positions(
    singles: list[dict[str, Any]],
    builders: list[dict[str, Any]],
    rows: list[dict[str, Any]] | dict[Any, dict[str, Any]],
    screen: dict[str, Any],
    settle_ran: bool | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Printed confidence singles and builders graded as audit_settlement 7c /
    7d grade them: the same key, PUSH not counted, one lost leg loses a slip,
    a builder at its screen price when recorded, else the haircut estimate.

    Each position is a dict with the artifact row under `source`.
    """
    by_key = rows if isinstance(rows, dict) else {_key(r): r for r in rows}
    # SETTLE ran for the day when it wrote any row: a position still absent
    # then will never be graded (7c's "nierozliczonych"), which is not the
    # same as waiting for SETTLE.
    if settle_ran is None:
        settle_ran = bool(rows)
    missing = "UNSETTLED" if settle_ran else "PENDING"
    graded_singles = []
    for p in singles:
        g = by_key.get(_key(p["source"]))
        if g is None:
            outcome = missing
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
        outcome = {"NIE WESZŁO": "LOSS", "WESZŁO": "WIN"}.get(status, missing)
        real = screen.get(str(src["sofascore_event_id"]))
        odds = float(real) if real is not None else builder_odds(src["odds_if_product"])
        graded_builders.append(
            {**b, "outcome": outcome, "odds": odds, "odds_measured": real is not None}
        )
    return graded_singles, graded_builders


SCREEN_FILE = {
    "standard": "09_screen_prices.json",
    "wariant": "09_screen_prices_wariant.json",
}


def official_rows(
    runs_dir: str,
    date: str,
    db_path: str,
    profile: str = "standard",
    event_ids: set[int] | None = None,
) -> tuple[dict[Any, dict[str, Any]], dict[str, Any]]:
    """The day's settled rows and the profile's screen prices, read exactly
    where audit_settlement 7c / 7d reads them: the database
    (sofa_settled_row, which regrade_settled.py corrects - 07_settled.json
    is not), and the profile's own screen file (a variant's slip on a fixture
    is a different slip from the coupon's)."""
    if not Path(db_path).exists():
        # Never "nothing settled": with no database every position would read
        # PENDING and overwrite a graded ledger row. A missing DB is a failure.
        raise FileNotFoundError(f"settled-row database not found: {db_path}")
    rows = settled_by_key(db_path, date, event_ids or set())
    path = mc.official_dir(runs_dir, date) / SCREEN_FILE[profile]
    screen = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    return rows, screen


def grade_official(
    runs_dir: str, date: str, section: dict[str, Any], db_path: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    ids = {int(p["source"]["sofascore_event_id"]) for p in section.get("singles", [])}
    ids |= {int(b["source"]["sofascore_event_id"]) for b in section.get("builders", [])}
    rows, screen = official_rows(runs_dir, date, db_path, event_ids=ids)
    return grade_confidence_positions(
        section.get("singles", []),
        section.get("builders", []),
        rows,
        screen,
        settle_ran=ran_on(rows, date),
    )


def ran_on(rows: dict[Any, dict[str, Any]], date: str) -> bool:
    """SETTLE ran for `date`: some row is filed under it (rows found under
    other dates do not say so)."""
    return any(r.get("run_date") == date for r in rows.values())


def settle_day(runs_dir: str, date: str, db_path: str) -> dict[str, Any] | None:
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
            singles, builders = grade_official(runs_dir, date, sec, db_path)
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


def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--from", dest="start", required=True)
    parser.add_argument("--to", dest="end", required=True)
    args = parser.parse_args()
    config = SofaConfig.from_env()
    runs_dir = config.runs_dir
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
            res = settle_day(runs_dir, day, config.db_path)
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
            # a defect, not a wait: two graders disagreeing on a leg
            open_rows += sum(1 for r in sec["rows"] if r["outcome"] == "MISMATCH")
        t = res["variant_total"]
        roi = "-" if t["roi"] is None else f"{t['roi']:+.1%}"
        print(
            f"| {day} | **variant total** | {t['positions']} | {t['settled']} | "
            f"{t['won']} | {t['lost']} | {t['not_counted']} | "
            f"{t['units']:+.2f} | {roi} |"
        )
    return 1 if open_rows else 0


def main() -> int:
    """An unexpected crash is FAILED (2), never read as "pending" (1)."""
    try:
        return _main()
    except SystemExit:
        raise
    except Exception as exc:
        print(f"FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
