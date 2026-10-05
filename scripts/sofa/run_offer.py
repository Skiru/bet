import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import IO, Any

from pydantic import RootModel

from bet.sofa import fixture_status as fs
from bet.sofa import timeutil
from bet.sofa.artifact_guard import incomplete_reason
from bet.sofa.atomic import write_atomic
from bet.sofa.config import SofaConfig
from bet.sofa.contracts import Fixture
from bet.sofa.locked_print import starts_after
from bet.sofa.offer import OfferFetcher
from bet.sofa.stage import set_stage
from bet.sofa.superbet import SuperbetClient
from bet.sofa.timeutil import frozen_clock_refusal


def merge_with_previous(
    fresh: list[dict[str, Any]], previous: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], int]:
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


def _z(t: datetime | None) -> str | None:
    return t.isoformat().replace("+00:00", "Z") if t is not None else None


def refresh_targets(
    fixtures: list[Fixture],
    previous: list[dict[str, Any]],
    status: dict[int, dict[str, Any]],
    cutoff: datetime,
) -> list[Fixture]:
    """The fixtures a --min-minutes-to-kickoff refresh re-prices: those whose
    earliest clock - CONFIDENCE's clocks (locked_print.kickoff_clocks):
    RESOLVE's two, Superbet's as the previous OFFER saw it, and
    FIXTURE_CHECK's fresh start (fixture_status.json) replacing the frozen
    ones - is after `cutoff`. The predicate is locked_print.starts_after,
    the one the rebuild plan's "open fixture" reads.

    Filtering on Sofascore's clock alone re-priced 22 ITF fixtures already in
    play on 2026-09-23 (it runs 7-9 h late there); filtering on RESOLVE's two
    frozen clocks alone skipped Gaubas and Monteiro - Moller on 2026-10-05
    (frozen 12:30Z, fresh 13:30Z / 13:00Z), which CONFIDENCE then printed on
    a 39-minute-old price."""
    seen = {
        int(o["sofascore_event_id"]): str(o["superbet_kickoff_seen_utc"])
        for o in previous if o.get("superbet_kickoff_seen_utc")
    }
    kept: list[Fixture] = []
    for f in fixtures:
        eid = int(f.sofascore_event_id)
        frozen = {"kickoff_utc": _z(f.kickoff_utc),
                  "superbet_kickoff_utc": _z(f.superbet_kickoff_utc)}
        if starts_after(frozen, seen.get(eid), status.get(eid), cutoff):
            kept.append(f)
    return kept


def main() -> int:
    # Every request underneath this call is this stage's cost (F22).
    set_stage("OFFER")
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--date", help="YYYY-MM-DD", default=timeutil.now().strftime("%Y-%m-%d")
    )
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
    _frozen = frozen_clock_refusal(config.runs_dir)
    if _frozen:
        print(_frozen, file=sys.stderr)
        return 2
    client = SuperbetClient(
        base_url="https://production-superbet-offer-pl.freetls.fastly.net"
    )
    fetcher = OfferFetcher(client)

    fixtures_path = Path(config.runs_dir) / args.date / "02_fixtures.json"
    if not fixtures_path.exists():
        print(f"{fixtures_path} missing", file=sys.stderr)
        return 2
    refusal = incomplete_reason(fixtures_path)
    if refusal:
        print(refusal, file=sys.stderr)
        return 2

    f: IO[Any]
    with open(fixtures_path, "rb") as f:
        fixtures_data = f.read()

    fixtures = RootModel[list[Fixture]].model_validate_json(fixtures_data).root

    # Filter before the fetch, not after: the point is the requests not made.
    skipped_kicked_off = 0
    if args.min_minutes_to_kickoff is not None:
        cutoff = timeutil.now() + timedelta(minutes=args.min_minutes_to_kickoff)
        # CONFIDENCE's clocks, not RESOLVE's frozen ones (refresh_targets).
        run = Path(config.runs_dir) / args.date
        prev_path = run / "04_offer.json"
        previous_offer = (
            json.loads(prev_path.read_text(encoding="utf-8"))
            if prev_path.exists() else []
        )
        kept = refresh_targets(fixtures, previous_offer, fs.load(run), cutoff)
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
    previous: list[dict[str, Any]] = []
    if out_path.exists():
        with open(out_path, encoding="utf-8") as f:
            previous = json.load(f)
    if args.min_minutes_to_kickoff is not None and previous:
        dumped, carried_forward = merge_with_previous(dumped, previous)
    # Fixtures Superbet's open breaker kept this run from asking (F6.1): what
    # the previous file knew about them stays - "not asked" is not "no price".
    # Their fetched_at_utc stays too, so every freshness gate still sees the
    # price for the age it is. A full run used to drop them from the day.
    not_reached = set(fetcher.not_reached)
    carried_not_reached = 0
    if not_reached and previous:
        written = {o["sofascore_event_id"] for o in dumped}
        unasked = [o for o in previous
                if o["sofascore_event_id"] in not_reached
                and o["sofascore_event_id"] not in written]
        dumped = dumped + unasked
        carried_not_reached = len(unasked)

    write_atomic(out_path, json.dumps(dumped, indent=2))

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
        "fetch_errors": len(fetcher.errors),
        "breaker_open": fetcher.breaker_open,
        "not_reached_breaker_open": len(not_reached),
        "carried_forward_not_reached": carried_not_reached,
    }
    for su_id, err in fetcher.errors[:20]:
        print(f"OFFER_FETCH_ERROR superbet={su_id}: {err}", file=sys.stderr)
    if not_reached:
        print(
            f"OFFER_BREAKER_OPEN: Superbet's breaker opened; {len(not_reached)} "
            f"fixture(s) not asked, {carried_not_reached} kept from the "
            "previous offer",
            file=sys.stderr,
        )

    # Fixtures on the board with no priced rung at all, and market names we
    # could not classify, are both diagnostics the operator has to see — a
    # market Superbet added should surface as unmapped, not vanish (T16).
    if fixtures and empty_offers == len(offers):
        verdict = "FAILED"
    elif (empty_offers or total_unmapped or total_collisions or fetcher.errors
          or not_reached):
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
