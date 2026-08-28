#!/usr/bin/env python3
"""Draft the legs of one fixture's Bet Builder slip, and what each must pay.

Usage:
    python3 scripts/simple/bet_builder_draft.py --stats-sheet PATH --event-id ID
    python3 scripts/simple/bet_builder_draft.py --stats-sheet PATH --event-id ID --max-legs 3

Stateless: reads one artifact, prints JSON, writes nothing. No DB row, no
run_id, no network -- so running it twice costs nothing and changes nothing.

**It prints no combined price and cannot be made to.** There is no bet-builder
endpoint in any provider here, and multiplying the leg prices would be wrong:
corners, cards, fouls and shots in one match are strongly positively correlated,
so the product understates the parlay's real probability. Read the combined
price off Superbet's own screen and judge it there.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for entry in (str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from bet.simple_stats.bet_builder_draft import draft_legs  # noqa: E402
from bet.simple_stats.contracts import StatsSheetV1  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--stats-sheet", required=True, help="Path to STATS_SHEET_V1 JSON (from run_analyze.py)")
    parser.add_argument("--event-id", required=True, help="Which fixture to draft for")
    parser.add_argument("--max-legs", type=int, default=4)
    args = parser.parse_args()

    sheet_path = Path(args.stats_sheet)
    if not sheet_path.exists():
        print(json.dumps({"error": f"stats sheet not found: {sheet_path}"}), file=sys.stderr)
        sys.exit(2)

    sheet = StatsSheetV1.model_validate_json(sheet_path.read_text(encoding="utf-8"))
    draft = draft_legs(sheet, args.event_id, max_legs=args.max_legs)

    payload = draft.model_dump(mode="json")
    payload["combined_price_note"] = (
        "not computed and never computable here -- read it off Superbet's own screen"
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    # A fixture with no eligible leg is a real answer, not an error.
    sys.exit(0 if draft.legs else 1)


if __name__ == "__main__":
    main()
