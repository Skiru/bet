import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from pydantic import RootModel

from bet.sofa.config import SofaConfig
from bet.sofa.contracts import Fixture
from bet.sofa.offer import OfferFetcher
from bet.sofa.stage import set_stage
from bet.sofa.superbet import SuperbetClient
from bet.sofa.timeutil import now


def merge_with_previous(
    fresh: list[dict], previous: list[dict]
) -> tuple[list[dict], int]:
    """Refreshed fixtures win; every untouched fixture survives.

    A filtered refresh **merges**; it must never shrink the artifact. SHEET
    reads `04_offer.json` and prices what it finds, so writing only the 185
    fixtures that were re-priced would delete the other 893 from the day — the
    same shape of loss as the two `--refresh-offer` regressions in `simple`,
    where a late refresh matched 106 fixtures against the morning's 112 and the
    difference went out silently.

    Extracted from `main` so the test that pins this can call it. It used to
    live inline, and the test reimplemented the same four lines in its own
    body: deleting the production merge left that test green, which is the one
    thing a regression test must not do.

    Returns the merged list and how many entries were carried forward.
    """
    refreshed_ids = {o["sofascore_event_id"] for o in fresh}
    kept = [o for o in previous if o["sofascore_event_id"] not in refreshed_ids]
    return fresh + kept, len(kept)


def main() -> int:
    # Every request underneath this call is this stage's cost (F22).
    set_stage("OFFER")
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="YYYY-MM-DD", default=now().strftime("%Y-%m-%d"))
    parser.add_argument(
        "--min-minutes-to-kickoff",
        type=int,
        default=None,
        help=(
            "Only price fixtures starting at least this many minutes from now. "
            "For a late refresh: the stage otherwise re-prices the whole board, "
            "including the fixtures that have already been played, and a full "
            "pass costs ~90 minutes against Superbet — during which the "
            "fixtures that can still be bet keep kicking off. On 2026-09-20 "
            "that was 890 finished fixtures paid for to reach the 185 that "
            "were still open."
        ),
    )
    args = parser.parse_args()

    config = SofaConfig.from_env()
    client = SuperbetClient(
        base_url="https://production-superbet-offer-pl.freetls.fastly.net"
    )
    fetcher = OfferFetcher(client)

    fixtures_path = Path(config.runs_dir) / args.date / "02_fixtures.json"
    if not fixtures_path.exists():
        print(f"{fixtures_path} missing", file=sys.stderr)
        return 2

    with open(fixtures_path, "rb") as f:
        fixtures_data = f.read()

    fixtures = RootModel[list[Fixture]].model_validate_json(fixtures_data).root

    # Filter before the fetch, not after: the point is the requests not made.
    skipped_kicked_off = 0
    if args.min_minutes_to_kickoff is not None:
        cutoff = datetime.now(UTC) + timedelta(minutes=args.min_minutes_to_kickoff)
        kept = [f for f in fixtures if f.kickoff_utc > cutoff]
        skipped_kicked_off = len(fixtures) - len(kept)
        fixtures = kept

    try:
        offers = fetcher.fetch_offers(fixtures)
    except Exception as e:
        summary = {
            "stage": "OFFER",
            "verdict": "FAILED",
            "metrics": {"error": str(e)},
            "output_path": None,
        }
        print(f"SOFA_SUMMARY: {json.dumps(summary)}", flush=True)
        return 2

    out_path = Path(config.runs_dir) / args.date / "04_offer.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    dumped = [o.model_dump(mode="json") for o in offers]

    # See merge_with_previous: a filtered refresh may never shrink the file.
    carried_forward = 0
    if args.min_minutes_to_kickoff is not None and out_path.exists():
        with open(out_path, encoding="utf-8") as f:
            previous = json.load(f)
        dumped, carried_forward = merge_with_previous(dumped, previous)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(dumped, f, indent=2)

    total_two_way = sum(
        1
        for o in offers
        for r in o.rungs
        if r.over_odds is not None and r.under_odds is not None
    )
    total_unmapped = sum(len(o.unmapped_markets) for o in offers)
    total_collisions = sum(len(o.price_collisions) for o in offers)
    empty_offers = sum(1 for o in offers if not o.rungs)

    metrics: dict[str, Any] = {
        "input_fixtures": len(fixtures),
        "skipped_kicked_off": skipped_kicked_off,
        "carried_forward_from_previous_offer": carried_forward,
        "offers_written": len(dumped),
        "output_offers": len(offers),
        "total_two_way_rungs": total_two_way,
        "total_unmapped": total_unmapped,
        "price_collisions": total_collisions,
        "empty_offers": empty_offers,
    }

    # Fixtures on the board with no priced rung at all, and market names we
    # could not classify, are both diagnostics the operator has to see — a
    # market Superbet added should surface as unmapped, not vanish (T16).
    if fixtures and empty_offers == len(offers):
        verdict = "FAILED"
    elif empty_offers or total_unmapped or total_collisions:
        verdict = "PARTIAL"
    else:
        verdict = "OK"

    summary = {
        "stage": "OFFER",
        "verdict": verdict,
        "metrics": metrics,
        "output_path": str(out_path),
    }

    print(f"SOFA_SUMMARY: {json.dumps(summary)}", flush=True)
    return {"OK": 0, "PARTIAL": 1, "FAILED": 2}[verdict]


if __name__ == "__main__":
    sys.exit(main())
