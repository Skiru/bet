#!/usr/bin/env python3
"""MARKET_CONTEXT: bookmaker prices and model reads for one betting day.

Usage:
    python3 scripts/simple/run_market_context.py --event-list PATH --output-dir PATH [-v]

Fetches, per football fixture, the corners quotes every tracked bookmaker is
publishing, the provider's consensus block, the per-bookmaker comparison grid
(entitlement permitting) and bzzoiro's own CatBoost forecast, then writes
MARKET_CONTEXT_V1. ANALYZE reads that file to fill one optional column of the
stats sheet.

This step is optional by construction, for the same reason TIPSTERS is: the
stats sheet is the deliverable and it does not depend on this. A failure here
returns PARTIAL, never FAILED.

Nothing produced here is a probability this pipeline computed. A price is what a
bookmaker thinks and a prediction is what a model thinks; neither has a sample
behind it, and neither ever reaches ``p_low``. See
src/bet/simple_stats/market_context.py for why that separation is structural.

Unlike TIPSTERS, this step spends real provider quota -- hence --max-events and
--provider-call-budget. Football is uncapped on the PRO plan, so those are
guards against a runaway loop rather than rationing.

Exit codes: 0 = OK, 1 = PARTIAL (ran, thin or blocked), 2 = PRECONDITION_FAILED.
"""
from __future__ import annotations

import argparse
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for entry in (str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from agent_output import AgentOutput, add_agent_args  # noqa: E402

from bet.api_clients.rate_limiter import RateLimiter  # noqa: E402
from bet.simple_stats.artifact_io import sha256_file, write_json_atomic  # noqa: E402
from bet.simple_stats.contracts import EventListV1  # noqa: E402
from bet.simple_stats.market_context import (  # noqa: E402
    CALLS_PER_EVENT,
    collect_market_context,
    eligible_events,
    summarize,
)
from bet.simple_stats.providers import RunBudget  # noqa: E402
from bet.simple_stats.run_context import record_run  # noqa: E402

STEP = "simple_stats:MARKET_CONTEXT"


def main() -> None:
    parser = argparse.ArgumentParser(description="MARKET_CONTEXT: odds and model reads")
    parser.add_argument("--event-list", required=True, help="Path to EVENT_LIST_V1 JSON (from run_discover.py)")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument(
        "--max-events", type=int, default=40,
        help=f"Fixtures to fetch context for, at ~{CALLS_PER_EVENT} calls each (default: 40)",
    )
    parser.add_argument(
        "--provider-call-budget", type=int, default=100,
        help="Per-provider ceiling inside this run (default: 100). bzzoiro is "
             "exempted upward by RUN_BUDGET_OVERRIDES, as in ENRICH.",
    )
    # Named --db-path to match the other steps, because run_pipeline.py forwards
    # that flag to every step it runs.
    parser.add_argument("--db-path", default=None, help="SQLite path for the pipeline_runs row")
    parser.add_argument(
        "--no-persist", action="store_true",
        help="Write only the artifact, no pipeline_runs row.",
    )
    add_agent_args(parser)
    args = parser.parse_args()

    out = AgentOutput(STEP, verbose=args.verbose, stop_on_error=args.stop_on_error)
    started_at = datetime.now(timezone.utc).isoformat()

    def record(date: str, run_id: str, status: str, stats: dict, error: str | None = None) -> None:
        """Lineage on every exit path, including the failures. A step that writes
        no pipeline_runs row is indistinguishable from a step that was never
        asked to run -- which is the exact question an operator has when the
        market column is empty."""
        if args.no_persist:
            return
        try:
            record_run(
                date=date, step="MARKET_CONTEXT", status=status, run_id=run_id,
                db_path=args.db_path, stats=stats, error_message=error, started_at=started_at,
            )
        except Exception as exc:  # noqa: BLE001 - bookkeeping never masks the run's own result
            print(f"[{STEP}] WARNING: could not record pipeline_runs row: {exc}", file=sys.stderr)

    event_list_path = Path(args.event_list)
    if not event_list_path.exists():
        out.error(f"event list not found: {event_list_path}", recoverable=False)
        out.summary(verdict="PRECONDITION_FAILED", metrics={"event_list": str(event_list_path)})
        sys.exit(2)

    event_list = EventListV1.model_validate_json(event_list_path.read_text(encoding="utf-8"))
    candidates = eligible_events(event_list)
    out.event(
        "run_start",
        run_id=event_list.run_id,
        date=event_list.date,
        events=len(event_list.events),
        eligible=len(candidates),
        planned_calls=min(len(candidates), args.max_events) * CALLS_PER_EVENT,
    )

    if not candidates:
        # Not a failure: a tennis-only slate, or a day whose football fixtures
        # were all found by some other source, has nothing here to fetch.
        out.warning(
            "no eligible fixture: this stage is football-only and needs bzzoiro's "
            "own event id, which tennis events and other-source events do not carry"
        )

    try:
        context = collect_market_context(
            event_list,
            RateLimiter(),
            max_events=args.max_events,
            budget=RunBudget(args.provider_call_budget),
        )
    except Exception as exc:
        traceback.print_exc(file=sys.stderr)
        out.error(f"market context run crashed: {exc}", recoverable=True)
        record(event_list.date, event_list.run_id, "PARTIAL", {"events_with_odds": 0}, str(exc))
        out.summary(verdict="PARTIAL", metrics={"error": str(exc), "events_with_odds": 0})
        sys.exit(1)

    output_path = Path(args.output_dir) / f"{event_list.date}_market_context.json"
    write_json_atomic(output_path, context.model_dump(mode="json"))
    digest = sha256_file(output_path)
    out.event("artifact_written", path=str(output_path), sha256=digest, events=len(context.events))

    if context.football_unlimited_entitled is False:
        out.warning(
            "account is not entitled to Football Unlimited: the per-bookmaker "
            "comparison grid is unavailable. Consensus and per-event quotes are "
            "unaffected, so the corners signal still works."
        )

    if args.verbose:
        for event in context.events[:30]:
            corners = [q for q in event.odds if q.market == "total_corners"]
            model = event.predictions
            out.candidate(
                event.event_id[:12],
                f"{len(corners)} corner quotes",
                lines=sorted({q.line for q in corners if q.line is not None}),
                model_corners=(
                    [model.prob_corners_over_85, model.prob_corners_over_95, model.prob_corners_over_105]
                    if model is not None
                    else "-"
                ),
                entitlement=event.comparison_entitlement,
                gaps=len(event.data_gaps),
            )

    metrics = {
        "run_id": context.run_id,
        **summarize(context),
        "output_path": str(output_path),
        "output_sha256": digest,
    }

    # Verdicts describe usefulness, not completion. An artifact with no corner
    # quotes and no model probabilities is a valid file worth nothing to the
    # column it exists to fill, so it reports PARTIAL rather than OK.
    summary_metrics = summarize(context)
    if not context.events:
        verdict = "PARTIAL"
    elif not summary_metrics["events_with_odds"] and not summary_metrics["events_with_corner_model"]:
        out.warning(
            f"{len(context.events)} fixtures fetched but none has corners odds or a "
            "corners model probability: every market column will read NO_MARKET_DATA"
        )
        verdict = "PARTIAL"
    else:
        verdict = "OK"

    # Said out loud rather than left in the artifact. A structurally empty
    # tennis column reads identically to a slate with no tennis on it, and on
    # 2026-09-02 that difference was invisible: 38 tennis fixtures, zero with a
    # bzzoiro-tennis id, 406 tennis rows with a market signal and not one with
    # a model probability. It does not change the verdict -- an unbought addon
    # is not a bad run -- but it must not be inferred from silence.
    for note in summary_metrics.get("tennis_model_unavailable", []):
        out.warning(f"tennis model: {note}")

    record(context.date, context.run_id, verdict, metrics)
    out.summary(verdict=verdict, metrics=metrics)
    sys.exit(0 if verdict == "OK" else 1)


if __name__ == "__main__":
    main()
