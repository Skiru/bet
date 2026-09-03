#!/usr/bin/env python3
"""Draft the legs of one fixture's Bet Builder slip, and what each must pay.

Usage:
    python3 scripts/simple/bet_builder_draft.py --stats-sheet PATH --event-id ID \
        --offer runs/<date>/<date>_superbet_offer.json

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
from bet.simple_stats.contracts import StatsSheetV1, SuperbetOfferV1  # noqa: E402
from bet.simple_stats.superbet_offer import lookup_line, player_alias_index  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--stats-sheet", required=True, help="Path to STATS_SHEET_V1 JSON (from run_analyze.py)")
    parser.add_argument("--event-id", required=True, help="Which fixture to draft for")
    parser.add_argument("--max-legs", type=int, default=4)
    parser.add_argument(
        "--offer",
        required=True,
        help=(
            "Path to the SUPERBET_OFFER_V1 artifact for this day. **Required.** "
            "``draft_legs`` refuses any leg the book does not carry, and "
            "without the offer it cannot know -- so this CLI used to produce "
            "slips whose availability gate had never run. A slip is placed as "
            "one unit: a leg that is not on the screen does not make the slip "
            "worse, it makes the slip impossible, and five of the eight slips "
            "shipped on 2026-09-01 contained one."
        ),
    )
    args = parser.parse_args()

    sheet_path = Path(args.stats_sheet)
    if not sheet_path.exists():
        print(json.dumps({"error": f"stats sheet not found: {sheet_path}"}), file=sys.stderr)
        sys.exit(2)
    offer_path = Path(args.offer)
    if not offer_path.exists():
        print(json.dumps({"error": f"superbet offer not found: {offer_path}"}), file=sys.stderr)
        sys.exit(2)

    sheet = StatsSheetV1.model_validate_json(sheet_path.read_text(encoding="utf-8"))
    offer = SuperbetOfferV1.model_validate_json(offer_path.read_text(encoding="utf-8"))
    event_offer = next(
        (e for e in offer.events if e.event_id == args.event_id), None
    )
    our_players = {
        row.player_name for row in sheet.rows
        if row.event_id == args.event_id and row.player_name
    }
    aliases = player_alias_index(offer, {args.event_id: our_players}).get(args.event_id, {})

    def price_for(row):
        availability, exact, _near_line, _near_price = lookup_line(
            event_offer,
            market=row.market,
            line=row.line,
            direction=row.direction,
            team_name=row.team_name,
            player_name=row.player_name,
            player_aliases=aliases,
        )
        return availability, (exact.price if exact else None)

    draft = draft_legs(
        sheet,
        args.event_id,
        max_legs=args.max_legs,
        price_for=price_for,
        # Every leg must beat its own bar. A slip is not a place to keep a row
        # "as context": on 2026-09-03 six of 25 legs sat below their own
        # minimum price, and a leg priced below its bar lowers the slip's
        # expectation in exchange for looking like a fuller coupon.
        require_value=True,
    )

    payload = draft.model_dump(mode="json")
    payload["combined_price_note"] = (
        "not computed and never computable here -- read it off Superbet's own screen"
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    # A fixture with no eligible leg is a real answer, not an error.
    sys.exit(0 if draft.legs else 1)


if __name__ == "__main__":
    main()
