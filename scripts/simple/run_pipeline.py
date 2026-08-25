#!/usr/bin/env python3
"""Canonical entrypoint for a betting day: DISCOVER -> ENRICH -> ANALYZE.

    python3 scripts/simple/run_pipeline.py                     # today, UTC
    python3 scripts/simple/run_pipeline.py --date 2026-08-25 -v

The three steps stay independently runnable (scripts/simple/run_discover.py and
friends), because being able to re-run one step against a saved artifact is how
you debug a bad day. This wrapper is what you run when you are not debugging: it
mints one ``run_id``, threads each step's artifact into the next, and returns a
single verdict.

Artifact paths are read from each step's own ``AGENT_SUMMARY.metrics.output_path``
rather than reconstructed from a filename convention here -- a convention
duplicated in two places is a convention that silently drifts.

Output is the repo's standard agent contract (scripts/agent_output.py). Exactly
one ``AGENT_SUMMARY:`` line is emitted, by this process; each child's summary is
re-emitted as a ``step_summary`` event so a monitoring agent sees per-step
detail without having to guess which of four summaries is the run's verdict.

Exit codes: 0 = OK, 1 = PARTIAL, 2 = FAILED or PRECONDITION_FAILED.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
scripts_path = str(ROOT / "scripts")
src_path = str(ROOT / "src")
for entry in (scripts_path, src_path):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from agent_output import AgentOutput, add_agent_args  # noqa: E402

from bet.simple_stats.run_context import new_run_id  # noqa: E402

# TIPSTERS sits between ENRICH and ANALYZE because it needs DISCOVER's event
# list and ANALYZE consumes its output, and it is listed as a full step so
# --start-at / --stop-after can address it. It is the only optional step: its
# inputs are third-party web pages, so it reports PARTIAL rather than FAILED and
# the run continues without the column.
STEPS = ("discover", "enrich", "tipsters", "analyze")
OPTIONAL_STEPS = frozenset({"tipsters"})

# Indirection so tests can substitute stub steps: the wrapper's job is
# sequencing, artifact threading and verdict aggregation, and none of that
# should need live providers to exercise.
STEP_SCRIPTS = {
    "discover": "scripts/simple/run_discover.py",
    "enrich": "scripts/simple/run_enrich.py",
    "tipsters": "scripts/simple/run_tipsters.py",
    "analyze": "scripts/simple/run_analyze.py",
}

# Ordered worst-last: the run's verdict is the worst any step reached.
_SEVERITY = {"OK": 0, "NO_BET": 1, "PARTIAL": 2, "PRECONDITION_FAILED": 3, "FAILED": 4}


def _utc_today() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def _run_step(
    out: AgentOutput,
    name: str,
    argv: list[str],
    *,
    verbose: bool,
) -> tuple[str, dict, int]:
    """Run one step, streaming its output. Returns (verdict, metrics, exit code).

    The child's own ``AGENT_SUMMARY:`` line is intercepted rather than echoed,
    so this process emits exactly one.
    """
    started = time.monotonic()
    out.event("step_start", pipeline_step=name, argv=" ".join(argv[1:]))

    process = subprocess.Popen(
        [sys.executable, *argv],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=None,  # stderr passes through: tracebacks belong on the terminal
        text=True,
        bufsize=1,
    )

    summary: dict = {}
    assert process.stdout is not None
    for line in process.stdout:
        if line.startswith("AGENT_SUMMARY:"):
            try:
                summary = json.loads(line[len("AGENT_SUMMARY:"):])
            except json.JSONDecodeError:
                out.warning(f"{name}: unparseable AGENT_SUMMARY", pipeline_step=name)
            continue
        if line.strip():
            print(line, end="", flush=True)

    code = process.wait()
    elapsed = round(time.monotonic() - started, 1)

    verdict = summary.get("verdict") or ("FAILED" if code else "OK")
    metrics = summary.get("metrics") or {}

    # A step that dies without a summary (crash, OOM, SIGKILL) would otherwise
    # be read as a clean OK by anything looking only at the verdict.
    if not summary:
        out.error(
            f"{name} produced no AGENT_SUMMARY (exit {code})",
            recoverable=False,
            pipeline_step=name,
            exit_code=code,
        )
        verdict = "FAILED"

    out.event(
        "step_summary",
        pipeline_step=name,
        verdict=verdict,
        exit_code=code,
        elapsed_s=elapsed,
        metrics=metrics if verbose else {
            k: metrics[k] for k in ("run_id", "output_path", "persisted") if k in metrics
        },
    )
    for issue in summary.get("issues", []):
        if issue.get("level") == "error":
            out.error(f"{name}: {issue.get('message')}", recoverable=True, pipeline_step=name)
        else:
            out.warning(f"{name}: {issue.get('message')}", pipeline_step=name)

    return verdict, metrics, code


def _preflight_only(sports: list[str], args) -> None:
    """Answer 'is today's run worth starting' without spending a single call.

    Deliberately runs before DISCOVER rather than inside ENRICH: finding out at
    10:00 that nothing can corroborate anything is worth knowing at 09:00, and
    the answer does not depend on which fixtures exist today.
    """
    from bet.api_clients.rate_limiter import RateLimiter
    from bet.simple_stats.preflight import preflight_for_sports

    out = AgentOutput("simple_stats:PREFLIGHT", verbose=args.verbose)
    result = preflight_for_sports(sports, RateLimiter(), planned_events=args.max_events)

    usable = result["usable_providers"]
    coverage = result["coverage_by_sport"]
    recommended = result["recommended_max_events"]

    if not args.verbose:
        print(f"{'provider':22} {'left':>6} {'limit':>7}  status")
        print("-" * 64)
        blocked_by_provider = {b["provider"]: b for b in result["blocked"]}
        for quota in result["quotas"]:
            provider = quota["provider"]
            block = blocked_by_provider.get(provider)
            status = block["kind"] if block else "usable"
            limit = quota["limit"]
            left = "inf" if limit is None else max(0, limit - quota["used_hint"])
            print(f"{provider:22} {left:>6} {str(limit if limit is not None else 'inf'):>7}  {status}")
        print()
        for sport in sports:
            cover = coverage.get(sport)
            print(f"  {sport:10} two-provider coverage: {'unlimited' if cover is None else cover} events")

    for block in result["blocked"]:
        out.warning(f"{block['provider']}: {block['reason']}", kind=block["kind"])

    # 'Can run' and 'worth running' are different questions. One provider is
    # enough to produce an artifact, but nothing in it will be corroborated, and
    # corroboration is the only reason this pipeline exists.
    if result["verdict"] == "PRECONDITION_FAILED":
        verdict, advice = "PRECONDITION_FAILED", "NO-GO: no usable provider. Fix the blocked ones above."
    elif not recommended:
        verdict, advice = "PARTIAL", (
            "GO, but nothing will be corroborated: only one provider covers a sport, "
            "so every row lands at SINGLE_SOURCE / confidence=LOW."
        )
    elif recommended < args.max_events:
        verdict, advice = "PARTIAL", (
            f"GO with --max-events {recommended} "
            f"(quota corroborates {recommended}, not the {args.max_events} planned)."
        )
    else:
        verdict, advice = "OK", f"GO: quota corroborates all {args.max_events} planned events."

    print(f"\n{advice}")
    out.summary(
        verdict=verdict,
        metrics={
            "sports": sports,
            "usable_providers": usable,
            "blocked_providers": [b["provider"] for b in result["blocked"]],
            "coverage_by_sport": coverage,
            "recommended_max_events": recommended,
            "planned_events": args.max_events,
            "advice": advice,
        },
    )
    sys.exit(0 if verdict == "OK" else (1 if verdict == "PARTIAL" else 2))


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--date", default=None, help="Betting day YYYY-MM-DD (default: today, UTC)")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Artifact directory (default: runs/<date>)",
    )
    parser.add_argument("--run-id", default=None, help="Reuse an existing run id instead of minting one")
    parser.add_argument("--sports", default=None, help="Comma-separated (default: football,tennis)")
    parser.add_argument("--max-events", type=int, default=40, help="Enrichment cap (default: 40)")
    parser.add_argument(
        "--provider-call-budget", type=int, default=100,
        help="Per-provider ceiling inside this run (default: 100)",
    )
    parser.add_argument("--db-path", default=None, help="Override the SQLite path for all three steps")
    parser.add_argument(
        "--skip-preflight", action="store_true",
        help="Run ENRICH even when every provider is exhausted (produces an all-gaps artifact)",
    )
    parser.add_argument(
        "--start-at", choices=STEPS, default="discover",
        help="Resume from a step, reusing artifacts already in --output-dir",
    )
    parser.add_argument("--stop-after", choices=STEPS, default="analyze")
    parser.add_argument(
        "--skip-tipsters", action="store_true",
        help="Do not fetch public tipster pages. The stats sheet is produced "
             "without the agreement column.",
    )
    parser.add_argument(
        "--tipster-source", action="append", default=None,
        help="Repeatable. Overrides the default live tipster source set.",
    )
    parser.add_argument(
        "--preflight", action="store_true",
        help="Check providers and stop. Spends nothing -- run this first, in the morning.",
    )
    add_agent_args(parser)
    args = parser.parse_args()

    date = args.date or _utc_today()
    sports = [s.strip() for s in (args.sports or "football,tennis").split(",") if s.strip()]

    if args.preflight:
        _preflight_only(sports, args)  # exits

    output_dir = Path(args.output_dir) if args.output_dir else ROOT / "runs" / date
    output_dir.mkdir(parents=True, exist_ok=True)

    out = AgentOutput("simple_stats:PIPELINE", verbose=args.verbose, stop_on_error=args.stop_on_error)
    started_at = datetime.now(UTC).isoformat(timespec="seconds")
    wall_start = time.monotonic()

    run_id = args.run_id or new_run_id(date)
    out.event(
        "run_start",
        run_id=run_id,
        date=date,
        output_dir=str(output_dir),
        start_at=args.start_at,
        stop_after=args.stop_after,
    )

    common = ["--output-dir", str(output_dir)]
    if args.db_path:
        common += ["--db-path", args.db_path]
    if args.verbose:
        common.append("--verbose")
    if args.stop_on_error:
        common.append("--stop-on-error")

    # Resume needs the artifact the skipped step would have written. The
    # convention lives in run_discover.py / run_enrich.py; these are the
    # fallbacks used only when that step did not run in this process.
    event_list = output_dir / f"{date}_event_list.json"
    dossier = output_dir / f"{date}_event_dossiers.json"
    tipster_signal = output_dir / f"{date}_tipster_signal.json"

    first = STEPS.index(args.start_at)
    last = STEPS.index(args.stop_after)
    if last < first:
        parser.error(f"--stop-after {args.stop_after} precedes --start-at {args.start_at}")

    step_results: dict[str, dict] = {}
    verdicts: list[str] = []
    stats_sheet: str | None = None

    for name in STEPS[first : last + 1]:
        if name == "discover":
            argv = [STEP_SCRIPTS["discover"], "--date", date, "--run-id", run_id, *common]
            if args.sports:
                argv += ["--sports", args.sports]
        elif name == "enrich":
            if not event_list.exists():
                out.error(
                    f"cannot start at ENRICH: {event_list} is missing -- run DISCOVER first",
                    recoverable=False,
                )
                out.summary(verdict="PRECONDITION_FAILED", metrics={"run_id": run_id, "date": date})
                sys.exit(2)
            argv = [
                STEP_SCRIPTS["enrich"],
                "--event-list", str(event_list),
                "--max-events", str(args.max_events),
                "--provider-call-budget", str(args.provider_call_budget),
                *common,
            ]
            if args.skip_preflight:
                argv.append("--skip-preflight")
        elif name == "tipsters":
            if args.skip_tipsters:
                out.event("step_skipped", pipeline_step=name, reason="--skip-tipsters")
                continue
            if not event_list.exists():
                out.warning(
                    f"skipping TIPSTERS: {event_list} is missing, so no pick can be "
                    "attributed to a fixture",
                    pipeline_step=name,
                )
                continue
            argv = [
                STEP_SCRIPTS["tipsters"],
                "--event-list", str(event_list),
                *common,
            ]
            for source in args.tipster_source or []:
                argv += ["--source", source]
        else:
            if not dossier.exists():
                out.error(
                    f"cannot start at ANALYZE: {dossier} is missing -- run ENRICH first",
                    recoverable=False,
                )
                out.summary(verdict="PRECONDITION_FAILED", metrics={"run_id": run_id, "date": date})
                sys.exit(2)
            argv = [STEP_SCRIPTS["analyze"], "--dossier", str(dossier), *common]
            # Absent unless TIPSTERS actually wrote it, so a skipped or failed
            # tipster step leaves ANALYZE exactly as it was before this stage
            # existed.
            if tipster_signal.exists():
                argv += ["--tipster-signal", str(tipster_signal)]

        verdict, metrics, code = _run_step(out, name, argv, verbose=args.verbose)
        # An optional step's verdict is recorded per step but kept out of the
        # run verdict: a tipster page that moved overnight is not a bad betting
        # day, and reporting it as one would train the operator to ignore the
        # field that matters.
        if name not in OPTIONAL_STEPS:
            verdicts.append(verdict)

        # On a resumed run, ENRICH/ANALYZE inherit the run_id stamped into the
        # artifact they read, which is the id of the original run -- not the one
        # minted above. Adopt theirs, or this summary would report a run_id no
        # step and no DB row ever used.
        step_run_id = metrics.get("run_id")
        if step_run_id and step_run_id != run_id:
            out.event("run_id_adopted", from_step=name, run_id=step_run_id, minted=run_id)
            run_id = step_run_id

        step_results[name] = {
            "verdict": verdict,
            "exit_code": code,
            "output_path": metrics.get("output_path"),
            "persisted": metrics.get("persisted"),
            "metrics": metrics,
        }

        produced = metrics.get("output_path")
        if produced:
            if name == "discover":
                event_list = Path(produced)
            elif name == "enrich":
                dossier = Path(produced)
            elif name == "tipsters":
                tipster_signal = Path(produced)
            else:
                stats_sheet = produced

        # DISCOVER/ENRICH failing means the next step has no input to read.
        # There is nothing to salvage by continuing, and continuing would spend
        # provider quota producing an artifact nobody can use.
        if verdict in ("FAILED", "PRECONDITION_FAILED") and name not in OPTIONAL_STEPS:
            out.error(
                f"{name} returned {verdict} -- stopping before {STEPS[STEPS.index(name) + 1]}"
                if name != "analyze" else f"{name} returned {verdict}",
                recoverable=False,
                pipeline_step=name,
            )
            break

    worst = max(verdicts, key=lambda v: _SEVERITY.get(v, 4)) if verdicts else "FAILED"

    metrics = {
        "run_id": run_id,
        "date": date,
        "output_dir": str(output_dir),
        "steps_run": list(step_results),
        "step_verdicts": {name: r["verdict"] for name, r in step_results.items()},
        "stats_sheet": stats_sheet,
        "tipster_signal": str(tipster_signal) if tipster_signal.exists() else None,
        "elapsed_s": round(time.monotonic() - wall_start, 1),
        "started_at": started_at,
    }
    for name, result in step_results.items():
        metrics[f"{name}_metrics"] = result["metrics"]

    # A machine-readable receipt for the whole run, next to the artifacts it
    # describes -- so a later session can reconstruct what happened without
    # scrollback.
    receipt = output_dir / f"{date}_run_summary.json"
    receipt.write_text(
        json.dumps(
            {"run_id": run_id, "date": date, "verdict": worst, "steps": step_results,
             "started_at": started_at, "elapsed_s": metrics["elapsed_s"]},
            indent=2, default=str,
        ),
        encoding="utf-8",
    )
    out.event("receipt_written", path=str(receipt))

    if stats_sheet:
        out.event("deliverable", path=stats_sheet, detail="stats sheet -- pick lines by hand in Superbet")

    out.summary(verdict=worst, metrics=metrics)
    sys.exit(0 if worst == "OK" else (1 if worst in ("PARTIAL", "NO_BET") else 2))


if __name__ == "__main__":
    main()
