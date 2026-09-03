#!/usr/bin/env python3
"""DISCOVER: collect football/tennis events for a date into EVENT_LIST_V1.

Usage:
    python3 scripts/simple/run_discover.py --date 2026-08-25 [--sports football,tennis] --output-dir PATH [-v]

Mints the run_id that ENRICH and ANALYZE inherit through their artifacts.
Emits the repo-standard AGENT_SUMMARY:{json} contract via scripts/agent_output.py
(step / verdict / metrics / issues / counts / ts). With -v, every source and
every discovered event is also streamed as a JSON-line event so a monitoring
agent sees progress during the run, not only at the end.

Exit codes: 0 = OK, 1 = PARTIAL, 2 = FAILED.
"""
import argparse
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
src_path = str(ROOT / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)
scripts_path = str(ROOT / "scripts")
if scripts_path not in sys.path:
    sys.path.insert(0, scripts_path)

from agent_output import AgentOutput, add_agent_args  # noqa: E402

from bet.simple_stats.artifact_io import sha256_file, write_json_atomic  # noqa: E402
from bet.simple_stats.discover import discover_events  # noqa: E402
from bet.simple_stats.persistence import default_db_path, persist_pipeline_run  # noqa: E402
from bet.simple_stats.run_context import new_run_id, record_run  # noqa: E402

STEP = "simple_stats:DISCOVER"


def main() -> None:
    parser = argparse.ArgumentParser(description="DISCOVER: simple_stats event discovery")
    parser.add_argument("--date", required=True, help="Target date YYYY-MM-DD")
    parser.add_argument("--sports", default=None, help="Comma-separated sports (default: football,tennis)")
    parser.add_argument("--output-dir", required=True, help="Directory to write EVENT_LIST_V1 JSON into")
    parser.add_argument("--run-id", default=None, help="Reuse an existing run id instead of minting one")
    parser.add_argument(
        "--db-path", default=None, help=f"SQLite DB to persist into (default: {default_db_path()})"
    )
    add_agent_args(parser)
    args = parser.parse_args()

    out = AgentOutput(STEP, verbose=args.verbose, stop_on_error=args.stop_on_error)
    started_at = datetime.now(timezone.utc).isoformat()
    run_id = args.run_id or new_run_id(args.date)
    sports = args.sports.split(",") if args.sports else None

    out.event("run_start", run_id=run_id, date=args.date, sports=sports or ["football", "tennis"])

    try:
        result = discover_events(date=args.date, sports=sports, run_id=run_id)
    except Exception as exc:
        traceback.print_exc(file=sys.stderr)
        out.error(f"discovery crashed: {exc}", recoverable=False, run_id=run_id)
        _record(args, run_id, "FAILED", {"error": str(exc)}, started_at, str(exc))
        out.summary(verdict="FAILED", metrics={"total_events": 0, "run_id": run_id})
        sys.exit(2)

    output_path = Path(args.output_dir) / f"{args.date}_event_list.json"
    write_json_atomic(output_path, result.model_dump(mode="json"))
    digest = sha256_file(output_path)
    out.event("artifact_written", path=str(output_path), sha256=digest, events=len(result.events))

    active = [e for e in result.events if e.status == "ACTIVE"]
    blocked = [e for e in result.events if e.status == "BLOCKED_IDENTITY"]
    by_source: dict[str, int] = {}
    for event in result.events:
        for source in event.source_ids:
            by_source[source] = by_source.get(source, 0) + 1

    for event in blocked:
        out.warning(
            "event blocked at discovery: ambiguous identity",
            event_id=event.event_id,
            reason=event.terminal_reason,
        )
    if args.verbose:
        for index, event in enumerate(active, start=1):
            out.progress(index, len(active), f"{event.competition}: {event.event_id[:12]}")

    metrics = {
        "run_id": run_id,
        "date": args.date,
        "total_events": len(result.events),
        "active_events": len(active),
        "blocked_identity_events": len(blocked),
        "confirmed_identity_events": sum(1 for e in active if e.identity_confidence == "CONFIRMED"),
        "multi_source_events": sum(1 for e in active if len(e.source_ids) > 1),
        "events_by_source": by_source,
        "output_path": str(output_path),
        "output_sha256": digest,
    }

    if not active:
        # Fail-closed on an empty universe (plan section 2). The repo's agent
        # contract only accepts OK/PARTIAL/FAILED/NO_BET/PRECONDITION_FAILED,
        # so the specific cause travels in issues rather than as a made-up
        # verdict a monitoring agent would not recognise.
        out.error("BLOCK_NO_EVENTS: discovery returned no ACTIVE events", recoverable=False, date=args.date)
        _record(args, run_id, "FAILED", metrics, started_at, "BLOCK_NO_EVENTS")
        out.summary(verdict="FAILED", metrics=metrics)
        sys.exit(2)

    persisted, persist_error = _persist(out, args, result)
    metrics["persisted"] = persisted
    metrics["persist_error"] = persist_error

    # A slate a quota cut short is not an OK slate.
    #
    # ``highlightly`` drives discovery breadth rather than corroboration, so
    # running out of its quota removes about 77% of the day's fixtures. On
    # 2026-09-03 it was already 101/100 when the run started, the slate came
    # out at 165 fixtures against a Superbet offer of 3,691 events, and this
    # step reported OK -- so nothing downstream, and no operator reading the
    # summary, had any reason to wait for the quota to reset.
    #
    # PARTIAL and not a new verdict word: the repo's agent contract accepts
    # OK/PARTIAL/FAILED/NO_BET/PRECONDITION_FAILED and nothing else, so the
    # cause travels in ``issues`` and ``metrics`` exactly as BLOCK_NO_EVENTS
    # already does. The handoff note asked for "DEGRADED"; a verdict a
    # monitoring agent does not recognise is worse than a PARTIAL it does.
    metrics["degraded_reasons"] = list(result.degraded_reasons)
    metrics["source_errors"] = {k: len(v) for k, v in result.source_errors.items()}
    for reason in result.degraded_reasons:
        out.error(
            f"SLATE_DEGRADED: {reason}. This slate is a fraction of the day. "
            "Wait for the quota to reset, or accept espn-football as the only "
            "corroborator (docs/SIMPLE_STATS_RUNBOOK.md).",
            recoverable=True,
            date=args.date,
        )

    verdict = (
        "OK"
        if (persisted and not blocked and not result.degraded_reasons)
        else "PARTIAL"
    )
    _record(args, run_id, verdict, metrics, started_at, persist_error)
    out.summary(verdict=verdict, metrics=metrics)
    sys.exit(0 if verdict == "OK" else 1)


def _persist(out: AgentOutput, args, result) -> tuple[bool, str | None]:
    try:
        persist_pipeline_run(result, None, None, betting_date=args.date, db_path=args.db_path)
        out.event("db_persisted", table="fixtures+fixture_sources", events=len(result.events))
        return True, None
    except Exception as exc:
        out.error(f"DB persistence failed: {exc}", recoverable=True)
        return False, str(exc)


def _record(args, run_id: str, status: str, stats: dict, started_at: str, error: str | None) -> None:
    try:
        record_run(
            date=args.date,
            step="DISCOVER",
            status=status,
            run_id=run_id,
            db_path=args.db_path,
            stats=stats,
            error_message=error,
            started_at=started_at,
        )
    except Exception as exc:  # noqa: BLE001 - bookkeeping must never mask the run's own result
        print(f"[{STEP}] WARNING: could not record pipeline_runs row: {exc}", file=sys.stderr)


if __name__ == "__main__":
    main()
