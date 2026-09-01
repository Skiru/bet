#!/usr/bin/env python3
"""TIPSTERS: public-opinion coverage for one betting day, as its own artifact.

Usage:
    python3 scripts/simple/run_tipsters.py --event-list PATH --output-dir PATH [-v]

Runs the compliance-gated live scrapers, matches every pick to a discovered
event and classifies each claim, then writes TIPSTER_SIGNAL_V1. ANALYZE reads
that file to fill one optional column of the stats sheet.

This step is optional by construction. It touches third-party sites that can
change or go down at any time, and a betting day must not be lost because a
tipster page moved. A failure here therefore returns PARTIAL, never FAILED: the
stats sheet is the deliverable and it does not depend on this.

Nothing produced here is a probability. See
src/bet/simple_stats/tipster_signal.py for why that separation is structural.

Exit codes: 0 = OK, 1 = PARTIAL (ran, thin or blocked), 2 = PRECONDITION_FAILED.
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for entry in (str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from agent_output import AgentOutput, add_agent_args  # noqa: E402

from bet.simple_stats.artifact_io import sha256_file, write_json_atomic  # noqa: E402
from bet.simple_stats.contracts import EventListV1  # noqa: E402
from bet.simple_stats.persistence import default_db_path  # noqa: E402
from bet.simple_stats.run_context import record_run  # noqa: E402
from bet.simple_stats.tipster_signal import build_tipster_signal, summarize  # noqa: E402
from bet.tipsters.live import DEFAULT_LIVE_SOURCE_IDS, DEFAULT_REVIEW_PATH, run_live  # noqa: E402
from bet.tipsters.source_registry import SOURCES  # noqa: E402
from bet.tipsters.storage import persist_sqlite  # noqa: E402

STEP = "simple_stats:TIPSTERS"


def main() -> None:
    parser = argparse.ArgumentParser(description="TIPSTERS: public-opinion column source")
    parser.add_argument("--event-list", required=True, help="Path to EVENT_LIST_V1 JSON (from run_discover.py)")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument(
        "--review-json",
        default=str(DEFAULT_REVIEW_PATH),
        help=f"Operator robots/terms attestation (default: {DEFAULT_REVIEW_PATH})",
    )
    parser.add_argument(
        "--source", action="append", choices=sorted(SOURCES),
        help=f"Repeatable. Default: {','.join(DEFAULT_LIVE_SOURCE_IDS)}",
    )
    parser.add_argument(
        "--max-pages-per-source", type=int, default=None,
        help="Hard ceiling on pages fetched per source. Unset means each source "
             "uses its own max_pages_per_run, which is the number configured "
             "next to its rate limit and is what should normally govern.",
    )
    parser.add_argument("--timeout-seconds", type=float, default=12.0)
    parser.add_argument(
        "--drop-undated", action="store_true",
        help="Discard picks whose source states no fixture date. Correct for a "
             "backfill; for a same-day run it throws away every Typersi pick.",
    )
    # Named --db-path to match run_discover/run_enrich/run_analyze, because
    # run_pipeline.py forwards that flag to every step it runs.
    parser.add_argument(
        "--db-path", default=None,
        help=f"SQLite sink for tipster_picks_v2 / tipster_consensus_v2 (default: {default_db_path()}). "
             "Never writes the stale legacy tipster_picks table.",
    )
    parser.add_argument(
        "--no-persist", action="store_true",
        help="Write only the artifact. Otherwise picks accumulate in the DB, "
             "which is how a usable tipster history gets rebuilt.",
    )
    add_agent_args(parser)
    args = parser.parse_args()

    out = AgentOutput(STEP, verbose=args.verbose, stop_on_error=args.stop_on_error)
    started_at = datetime.now(timezone.utc).isoformat()

    def record(date: str, run_id: str, status: str, stats: dict, error: str | None = None) -> None:
        """Lineage, on every exit path including the failures.

        bet-analyst is instructed to cross-check pipeline_runs for the day. A
        step that writes no row there is indistinguishable from a step that was
        never asked to run, which is exactly the question an operator has when
        the agreement column is empty.
        """
        if args.no_persist:
            return
        try:
            record_run(
                date=date, step="TIPSTERS", status=status, run_id=run_id,
                db_path=args.db_path, stats=stats, error_message=error, started_at=started_at,
            )
        except Exception as exc:  # noqa: BLE001 - bookkeeping never masks the run's own result
            print(f"[{STEP}] WARNING: could not record pipeline_runs row: {exc}", file=sys.stderr)

    event_list_path = Path(args.event_list)
    if not event_list_path.exists():
        out.error(f"event list not found: {event_list_path}", recoverable=False)
        out.summary(verdict="PRECONDITION_FAILED", metrics={"event_list": str(event_list_path)})
        sys.exit(2)

    review_path = Path(args.review_json)
    if not review_path.exists():
        # Fail closed and say what is missing. This file is the operator's
        # attestation that each source was reviewed; without it nothing may be
        # fetched, and inventing a default would defeat the point of having one.
        out.error(
            f"no operator review file at {review_path}: no source may be fetched without an attestation",
            recoverable=False,
        )
        out.summary(verdict="PRECONDITION_FAILED", metrics={"review_json": str(review_path)})
        sys.exit(2)

    event_list = EventListV1.model_validate_json(event_list_path.read_text(encoding="utf-8"))
    sources = tuple(args.source) if args.source else DEFAULT_LIVE_SOURCE_IDS
    out.event("run_start", run_id=event_list.run_id, date=event_list.date, events=len(event_list.events), sources=list(sources))

    try:
        live = run_live(
            event_list.date,
            review_path=review_path,
            source_ids=sources,
            max_pages_per_source=args.max_pages_per_source,
            timeout=args.timeout_seconds,
            drop_undated=args.drop_undated,
            verbose=args.verbose,
        )
    except Exception as exc:
        traceback.print_exc(file=sys.stderr)
        out.error(f"live tipster run crashed: {exc}", recoverable=True)
        record(event_list.date, event_list.run_id, "PARTIAL", {"picks_ingested": 0}, str(exc))
        out.summary(verdict="PARTIAL", metrics={"error": str(exc), "picks_ingested": 0})
        sys.exit(1)

    results = live["results"]
    picks = [pick for result in results for pick in result.picks]

    blocked = [
        {"source_id": r.source_id, "reason": r.block_reason or r.skip_reason or "", "url": r.url}
        for r in results
        if r.block_reason or r.skip_reason
    ]
    for entry in blocked:
        out.warning(f"{entry['source_id']}: {entry['reason']}", url=entry["url"])

    signal = build_tipster_signal(
        event_list,
        picks,
        date_filter=live["date_filter"],
        sources_attempted=list(sources),
        sources_blocked=blocked,
    )

    output_path = Path(args.output_dir) / f"{event_list.date}_tipster_signal.json"
    write_json_atomic(output_path, signal.model_dump(mode="json"))
    digest = sha256_file(output_path)
    out.event("artifact_written", path=str(output_path), sha256=digest, events=len(signal.events))

    if args.verbose:
        for event in signal.events[:30]:
            countable = sum(1 for p in event.picks if p.countable)
            out.candidate(
                event.event_id[:12],
                f"{event.home_team} - {event.away_team}",
                picks=len(event.picks),
                countable=countable,
                match=f"{event.match_quality}/{event.match_score}",
                public_lean=event.public_lean or "-",
            )

    persisted = None
    persist_error = None
    if not args.no_persist:
        db_path = Path(args.db_path or default_db_path())
        try:
            persisted = persist_sqlite(results, db_path)
            out.event("db_persisted", table="tipster_picks_v2", **persisted)
        except Exception as exc:  # a reporting sink must not fail the step
            persist_error = str(exc)
            out.warning(f"tipster persistence failed: {exc}", db_path=str(db_path))

    metrics = {
        "run_id": signal.run_id,
        **summarize(signal),
        "raw_pick_count": live["raw_pick_count"],
        "sources_attempted": list(sources),
        "sources_blocked": [e["source_id"] for e in blocked],
        "output_path": str(output_path),
        "output_sha256": digest,
        "persisted": persisted,
        "persist_error": persist_error,
    }

    # Verdicts describe usefulness, not mere completion. A run that fetched
    # nothing, or matched nothing to today's fixtures, technically succeeded and
    # is worth nothing to the column, so it reports PARTIAL rather than OK.
    if not picks:
        out.warning("no tipster picks ingested: every source was blocked, empty or filtered out by date")
        verdict = "PARTIAL"
    elif not signal.events:
        out.warning(f"{len(picks)} picks ingested but none matched a discovered fixture")
        verdict = "PARTIAL"
    elif signal.countable_claims == 0:
        out.warning(
            f"{signal.picks_matched} picks matched but none is a plain match total: "
            "every column will read NO_COVERAGE (tipsters publish mostly 1X2)"
        )
        verdict = "PARTIAL"
    else:
        verdict = "OK"

    record(signal.date, signal.run_id, verdict, metrics, persist_error)
    out.summary(verdict=verdict, metrics=metrics)
    sys.exit(0 if verdict == "OK" else 1)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        # The docstring above promises that a failure here returns PARTIAL and
        # never takes a betting day down. That promise only held for exceptions
        # raised inside main(); anything raised on the way to it exited 1 with
        # no summary and no pipeline_runs row, which is precisely how this step
        # failed silently for two days. An operator asking "why is the tipster
        # column empty" must always find an answer in the run output.
        traceback.print_exc(file=sys.stderr)
        print(
            "AGENT_SUMMARY:" + json.dumps({
                "step": STEP,
                "verdict": "PARTIAL",
                "metrics": {"error": str(exc), "picks_ingested": 0},
                "issues": [{"level": "error", "message": f"TIPSTERS crashed: {exc}"}],
            }),
        )
        sys.exit(1)
