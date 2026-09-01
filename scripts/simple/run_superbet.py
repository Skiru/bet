#!/usr/bin/env python3
"""SUPERBET: the operator's own book, and how the sheet compares to it.

Usage:
    python3 scripts/simple/run_superbet.py --event-list PATH --output-dir PATH [-v]
    python3 scripts/simple/run_superbet.py --event-list PATH --output-dir PATH \
        --stats-sheet runs/<date>/<date>_event_dossiers_stats_sheet.json

Writes ``<date>_superbet_offer.json`` always, and ``<date>_superbet_comparison.json``
when a stats sheet is passed. The comparison is what a human reads; the offer is
what makes it reproducible.

Why this is its own step and not part of MARKET_CONTEXT
-------------------------------------------------------
MARKET_CONTEXT answers "what does the market think" from bzzoiro's grid of ~88
bookmakers. **Superbet is not one of them** and never has been. This step
answers a different question -- *is this line on the operator's screen, and at
what price* -- and the two must not be conflated, because a reference price
agreeing with our read says nothing about whether the bet can be taken.

It is optional and additive, exactly like MARKET_CONTEXT and TIPSTERS: nothing
it produces reaches ``p_low``, and a betting day that loses it loses a column,
not a verdict. A Superbet price is a price, not an observation.

Cost: one request for the day plus one per matched fixture. Public, unmetered,
no credential. Nothing here authenticates, holds a session or can place a bet.

Exit codes: 0 = OK, 1 = PARTIAL (ran, thin or blocked), 2 = PRECONDITION_FAILED.
"""
from __future__ import annotations

import argparse
import sys
import traceback
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for entry in (str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from agent_output import AgentOutput, add_agent_args  # noqa: E402

from bet.simple_stats.artifact_io import sha256_file, write_json_atomic  # noqa: E402
from bet.simple_stats.contracts import EventListV1, StatsSheetV1  # noqa: E402
from bet.simple_stats.run_context import record_run  # noqa: E402
from bet.simple_stats.superbet_identity import (  # noqa: E402
    build_identity_bridge,
    disabled as bridge_disabled,
)
from bet.simple_stats.superbet_offer import (  # noqa: E402
    collect_superbet_offer,
    compare_sheet_to_offer,
    summarize_offer,
)

STEP = "simple_stats:SUPERBET"


def main() -> None:
    parser = argparse.ArgumentParser(description="SUPERBET: the operator's own book")
    parser.add_argument("--event-list", required=True, help="Path to EVENT_LIST_V1 JSON")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument(
        "--stats-sheet", default=None,
        help="Path to STATS_SHEET_V1. When given, also writes the comparison artifact.",
    )
    parser.add_argument(
        "--max-events", type=int, default=250,
        help="Fixtures to price, at one request each (default: 250). The offer is "
             "public and unmetered, so this guards a runaway loop, not a quota.",
    )
    parser.add_argument(
        "--min-p-low", type=float, default=0.50,
        help="Compare only rows at or above this p_low (default: 0.50, the coupon's "
             "own floor). Pass 0.0 for the full sweep -- that is the aggressive "
             "mode, and on a 98-fixture day it writes ~20k rows and 14 MB, most of "
             "them rows nobody would ever print. The comparison is still wider than "
             "the coupon at the default: it keeps every line and every per-team row, "
             "where the coupon takes one single per market family.",
    )
    parser.add_argument(
        "--oddspapi-bridge", choices=("auto", "on", "off"), default="auto",
        help="Name Superbet fixtures by Betradar id via OddsPapi instead of by "
             "spelling (default: auto -- on when ODDSPAPI_API_KEY is set and the "
             "plan has quota to spare). Costs one /account probe, cached six "
             "hours, plus one /fixtures call per sport. It can only *add* "
             "matches: with it off, or on any failure, the fixture matcher "
             "behaves exactly as it did before. 'on' still degrades rather than "
             "failing the step -- it forces the attempt, not the outcome.",
    )
    parser.add_argument("--db-path", default=None, help="SQLite path for the pipeline_runs row")
    parser.add_argument("--no-persist", action="store_true", help="Write only artifacts, no DB row")
    add_agent_args(parser)
    args = parser.parse_args()

    out = AgentOutput(STEP, verbose=args.verbose, stop_on_error=args.stop_on_error)
    started_at = datetime.now(UTC).isoformat()

    def record(date: str, run_id: str, status: str, stats: dict, error: str | None = None) -> None:
        if args.no_persist:
            return
        try:
            record_run(
                date=date, step="SUPERBET", status=status, run_id=run_id,
                db_path=args.db_path, stats=stats, error_message=error, started_at=started_at,
            )
        except Exception as exc:  # noqa: BLE001 - bookkeeping never masks the run's result
            print(f"[{STEP}] WARNING: could not record pipeline_runs row: {exc}", file=sys.stderr)

    event_list_path = Path(args.event_list)
    if not event_list_path.exists():
        out.error(f"event list not found: {event_list_path}", recoverable=False)
        out.summary(verdict="PRECONDITION_FAILED", metrics={"event_list": str(event_list_path)})
        sys.exit(2)

    event_list = EventListV1.model_validate_json(event_list_path.read_text(encoding="utf-8"))
    out.event("run_start", run_id=event_list.run_id, date=event_list.date, events=len(event_list.events))

    if args.oddspapi_bridge == "off":
        bridge = bridge_disabled("disabled by --oddspapi-bridge=off")
    else:
        # Never lets an optional identity lookup take a betting day down: the
        # builder already swallows its own failures, and this is the last rail.
        try:
            bridge = build_identity_bridge(event_list)
        except Exception as exc:  # noqa: BLE001
            bridge = bridge_disabled(f"identity bridge crashed: {exc}")
    for note in bridge.notes:
        out.event("oddspapi_bridge", note=note)
    if bridge.enabled:
        out.event(
            "oddspapi_bridge_ready",
            events=len(bridge.betradar_by_event_id),
            requests=bridge.requests_made,
            quota_remaining=bridge.quota_remaining,
        )

    try:
        offer = collect_superbet_offer(
            event_list, max_events=args.max_events, identity_bridge=bridge
        )
    except Exception as exc:
        traceback.print_exc(file=sys.stderr)
        out.error(f"superbet offer run crashed: {exc}", recoverable=True)
        record(event_list.date, event_list.run_id, "PARTIAL", {"events_matched": 0}, str(exc))
        out.summary(verdict="PARTIAL", metrics={"error": str(exc), "events_matched": 0})
        sys.exit(1)

    output_dir = Path(args.output_dir)
    offer_path = output_dir / f"{event_list.date}_superbet_offer.json"
    write_json_atomic(offer_path, offer.model_dump(mode="json"))
    offer_digest = sha256_file(offer_path)
    out.event("artifact_written", path=str(offer_path), sha256=offer_digest, events=len(offer.events))

    metrics = {
        "run_id": offer.run_id,
        "date": offer.date,
        **summarize_offer(offer),
        "events_matched_by_id": offer.events_matched_by_id,
        **bridge.as_metrics(),
        "offer_path": str(offer_path),
        "offer_sha256": offer_digest,
    }

    comparison = None
    if args.stats_sheet:
        sheet_path = Path(args.stats_sheet)
        if not sheet_path.exists():
            out.warning(f"stats sheet not found, writing offer only: {sheet_path}")
        else:
            sheet = StatsSheetV1.model_validate_json(sheet_path.read_text(encoding="utf-8"))
            comparison = compare_sheet_to_offer(
                sheet, offer, event_list, min_p_low=args.min_p_low
            )
            comparison_path = output_dir / f"{event_list.date}_superbet_comparison.json"
            write_json_atomic(comparison_path, comparison.model_dump(mode="json"))
            comparison_digest = sha256_file(comparison_path)
            out.event(
                "artifact_written",
                path=str(comparison_path),
                sha256=comparison_digest,
                rows=len(comparison.rows),
            )
            metrics.update(
                comparison_path=str(comparison_path),
                comparison_sha256=comparison_digest,
                rows_considered=comparison.rows_considered,
                rows_compared=comparison.rows_compared,
                verdict_counts=comparison.verdict_counts,
                value_rows=comparison.verdict_counts.get("VALUE", 0),
                markets_with_no_line_overlap=sorted(
                    key for key, value in comparison.line_coverage.items() if value["no_overlap"]
                ),
            )

    # The two warnings that matter most, said out loud rather than left in JSON.
    if comparison is not None:
        dead = [key for key, value in comparison.line_coverage.items() if value["no_overlap"]]
        if dead:
            out.warning(
                "line ladders do not overlap for: " + ", ".join(dead) + ". Superbet "
                "lists these markets but never at a line this pipeline generates, so "
                "every row in them is unbettable regardless of its p_low."
            )
        if not comparison.verdict_counts.get("VALUE"):
            out.warning(
                "no row on this sheet reaches its minimum acceptable odds at Superbet. "
                "That is an answer about the day, not a failure of this step."
            )

    if offer.our_events_kicked_off:
        out.event(
            "fixtures_already_started",
            count=len(offer.our_events_kicked_off),
            of_unmatched=len(offer.our_events_without_offer),
            note="offerState=prematch drops a live fixture, so these are absent "
                 "from the book by its clock, not by a matching failure",
        )

    if offer.data_gaps:
        for gap in offer.data_gaps[:10]:
            out.warning(f"superbet gap: {gap}")

    if args.verbose:
        for event in offer.events[:30]:
            out.candidate(
                (event.event_id or event.superbet_event_id)[:12],
                f"{len(event.lines)} priced lines",
                superbet=event.superbet_match_name,
                quality=event.match_quality,
                kickoff_delta_min=event.kickoff_delta_minutes,
                unmapped=len(event.unmapped_markets),
            )

    if not offer.events:
        verdict = "PARTIAL"
    elif offer.data_gaps:
        verdict = "PARTIAL"
    else:
        verdict = "OK"

    record(offer.date, offer.run_id, verdict, metrics)
    out.summary(verdict=verdict, metrics=metrics)
    sys.exit(0 if verdict == "OK" else 1)


if __name__ == "__main__":
    main()
