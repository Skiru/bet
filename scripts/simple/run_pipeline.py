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

from bet.simple_stats.providers import PRIMARY_PROVIDER_BY_SPORT  # noqa: E402
from bet.simple_stats.run_context import new_run_id  # noqa: E402

# MARKET_CONTEXT and TIPSTERS both sit between ENRICH and ANALYZE: each needs
# DISCOVER's event list, ANALYZE consumes both outputs, and each is listed as a
# full step so --start-at / --stop-after can address it.
#
# Both are optional, for the same structural reason and with different failure
# modes. TIPSTERS reads third-party web pages that can move overnight;
# MARKET_CONTEXT reads a paid API whose entitlement can lapse. Neither produces
# anything the stats sheet depends on -- they fill columns beside p_low, never
# inside it -- so both report PARTIAL rather than FAILED and the run continues.
# SUPERBET joins them (2026-08-31) for the same structural reason and one
# extra one. Structurally: it needs DISCOVER's event list, ANALYZE consumes
# its output, and it fills a column beside p_low rather than inside it. The
# extra one: it is the only stage that reads the book the operator actually
# bets into. bzzoiro's grid of ~88 bookmakers does not contain Superbet, so
# until this step existed the pipeline could not tell "priced too short"
# from "not on the screen at all" -- and on the 2026-08-31 night slate the
# second was true of eight of fifteen singles.
#
# SUPERBET moved ahead of ENRICH on 2026-09-02, and that is the one ordering
# constraint in this list that is about money rather than about inputs. It
# still only needs the event list, so nothing forced it to run last; running it
# last meant the expensive step could not know which fixtures were on the board.
# Measured on 2026-09-02: of 325 dossiers, 113 were already past kickoff when
# ENRICH ran and 155 had no Superbet offer -- ~82% of the slate was enriched at
# full provider cost and could never reach a coupon. Ahead of ENRICH the same
# artifact becomes the slate gate (enrich.SlateGate).
#
# It stays optional. When it fails or is skipped the gate keeps its first two
# rules and simply does not apply the third, which is the pre-2026-09-02
# behaviour minus the fixtures no provider of record covers.
STEPS = ("discover", "superbet", "enrich", "market_context", "tipsters", "analyze")

# SUPERBET's fixture cap, deliberately not ``--max-events``.
#
# The two caps bound different things. ``--max-events`` bounds *provider quota*:
# a fixture costs ENRICH several dozen metered calls. SUPERBET's bounds a public,
# unmetered endpoint at one request per matched fixture, and its own help text
# calls it "a guard against a runaway loop, not a quota".
#
# Sharing them was harmless while SUPERBET ran last. It stopped being harmless
# the moment ENRICH started reading the offer as a slate gate: a fixture the
# book prices but SUPERBET never fetched lines for is indistinguishable, in the
# artifact, from one the book declines to price. Measured on the live
# 2026-09-03 run with ``--max-events 30``: **9 priced fixtures read as
# unpriced**, against 1 genuine absence when the offer was collected uncapped.
#
# High enough never to bind on a real slate (the widest recorded day matched
# 170), low enough to stop a runaway.
SUPERBET_OFFER_CAP = 400


def preflight_advice(
    verdict: str,
    coverage: dict[str, int | None],
    recommended: int | None,
    max_events: int,
) -> tuple[str, str]:
    """The morning GO / NO-GO line, and the verdict that goes with it.

    Pure, and separate from the printing, because three genuinely different
    situations used to share one branch -- all three made
    ``recommended_max_events`` falsy:

    * coverage ``None``   -- nothing bounds the run. The healthy answer.
    * coverage ``0``      -- the provider of record reaches none of today's
                             fixtures, so the slate gate will refuse all of
                             them. The run would spend a full ENRICH to produce
                             an empty sheet.
    * ``recommended == 0``-- the same thing, arrived at from the other side.

    The middle one is the failure this architecture made possible, and it was
    getting the most reassuring wording of the three: "GO, bzzoiro alone reaches
    READY and CALL", printed at the exact moment bzzoiro reached nothing.
    """
    if verdict == "PRECONDITION_FAILED":
        return "PRECONDITION_FAILED", "NO-GO: no usable provider. Fix the blocked ones above."

    zero = sorted(sport for sport, cover in coverage.items() if cover == 0)
    if zero and len(zero) == len(coverage):
        return "PRECONDITION_FAILED", (
            f"NO-GO: {', '.join(zero)} -- the provider of record reaches none of "
            f"today's fixtures, so the slate gate will refuse all of them and the "
            f"run would produce an empty sheet at full cost."
        )
    if zero:
        return "PARTIAL", (
            f"GO for the rest, but {', '.join(zero)} will produce nothing: the provider "
            f"of record reaches none of today's fixtures there."
        )
    if recommended is None:
        return "OK", "GO: no provider bounds the run -- every sport's coverage is unlimited."
    if recommended < max_events:
        return "PARTIAL", (
            f"GO with --max-events {recommended} "
            f"(quota corroborates {recommended}, not the {max_events} planned)."
        )
    return "OK", f"GO: quota corroborates all {max_events} planned events."
OPTIONAL_STEPS = frozenset({"market_context", "tipsters", "superbet"})

# Indirection so tests can substitute stub steps: the wrapper's job is
# sequencing, artifact threading and verdict aggregation, and none of that
# should need live providers to exercise.
STEP_SCRIPTS = {
    "discover": "scripts/simple/run_discover.py",
    "enrich": "scripts/simple/run_enrich.py",
    "market_context": "scripts/simple/run_market_context.py",
    "tipsters": "scripts/simple/run_tipsters.py",
    "superbet": "scripts/simple/run_superbet.py",
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
            # Named for what it now measures. For a sport with a primary
            # provider this is that provider's own reach (football: bzzoiro),
            # because readiness is measured on its sample and the slate gate
            # refuses fixtures it never discovered. For a sport without one
            # (tennis) it is still what two providers can jointly reach.
            basis = (
                f"{PRIMARY_PROVIDER_BY_SPORT[sport]} coverage"
                if sport in PRIMARY_PROVIDER_BY_SPORT
                else "two-provider coverage"
            )
            print(f"  {sport:10} {basis}: {'unlimited' if cover is None else cover} events")

    for block in result["blocked"]:
        out.warning(f"{block['provider']}: {block['reason']}", kind=block["kind"])

    # 'Can run' and 'worth running' are different questions. One provider is
    # enough to produce an artifact, but nothing in it will be corroborated, and
    # corroboration is the only reason this pipeline exists.
    verdict, advice = preflight_advice(
        result["verdict"], coverage, recommended, args.max_events
    )

    print(f"\n{advice}")
    # This entrypoint runs before DISCOVER, so it has no slate and cannot know
    # which competitions are on it. Every figure above is therefore a quota
    # statement only. Capability is per competition and can veto a provider
    # outright: on 2026-08-25 espn-football had 10000 requests free and served
    # none of the Saudi and Korean leagues that made up the day, so a coverage
    # of 3 delivered 0 corroborated rows. The ENRICH preflight inside the run
    # applies the capability caps; this one must not be read as a promise.
    capability_note = None
    if "football" in sports:
        capability_note = (
            "coverage above counts quota only -- how many fixtures bzzoiro actually "
            "discovers is unknown until DISCOVER runs, and since 2026-09-02 that is "
            "the slate: ENRICH refuses a football fixture the primary never found. "
            "Expect the enriched slate to be a fraction of what DISCOVER reports "
            "(287 -> 49 on 2026-09-02), and read ENRICH's slate_gate_drops for why"
        )
        out.warning(capability_note, pipeline_step="simple_stats:PREFLIGHT")

    out.summary(
        verdict=verdict,
        metrics={
            "sports": sports,
            "usable_providers": usable,
            "blocked_providers": [b["provider"] for b in result["blocked"]],
            "coverage_by_sport": coverage,
            "coverage_basis": "quota_only",
            "capability_note": capability_note,
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
    parser.add_argument(
        "--max-events", type=int, default=None,
        help="Enrichment cap (default: 40 on a fresh run; required explicitly "
             "when resuming at a step that consumes it)",
    )
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
        "--player-props", action="store_true",
        help="Pass through to ENRICH: also collect per-player prop history "
             "(~20 extra bzzoiro calls per event). Off by default.",
    )
    parser.add_argument(
        "--start-at", choices=STEPS, default="discover",
        help="Resume from a step, reusing artifacts already in --output-dir",
    )
    parser.add_argument("--stop-after", choices=STEPS, default="analyze")
    parser.add_argument(
        "--skip-market-context", action="store_true",
        help="Do not fetch bookmaker odds or model predictions. The stats sheet "
             "is produced without the market column.",
    )
    parser.add_argument(
        "--skip-tipsters", action="store_true",
        help="Do not fetch public tipster pages. The stats sheet is produced "
             "without the agreement column.",
    )
    parser.add_argument(
        "--skip-superbet", action="store_true",
        help="Do not read Superbet's public offer. The stats sheet is produced "
             "without the column that says whether a line is on the operator's "
             "screen at all -- so every min-odds figure in the coupon becomes a "
             "target rather than a comparison.",
    )
    parser.add_argument(
        "--oddspapi-bridge", choices=("auto", "on", "off"), default="auto",
        help="Passed to SUPERBET. Names Superbet fixtures by Betradar id via "
             "OddsPapi rather than by spelling, which recovered eight fixtures "
             "on the 2026-09-01 slate that no name rule could reach. Costs two "
             "or three requests out of a 250-request lifetime allowance, so "
             "'off' is the setting for a day when that allowance is needed "
             "elsewhere.",
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

    # A resume must state its own breadth. ENRICH overwrites the dossier and
    # SUPERBET/MARKET_CONTEXT cap how many fixtures they read, so resuming a
    # 250-event day under a silent default of 40 rebuilds the dossier at a
    # sixth of its size -- the sheet shrinks ~84% and nothing reports why.
    # The first pass's breadth is not recoverable from a default, so ask.
    if args.max_events is None:
        if args.start_at in ("enrich", "market_context", "superbet"):
            parser.error(
                f"--start-at {args.start_at} requires an explicit --max-events: "
                "the default of 40 would silently shrink a wider first pass"
            )
        args.max_events = 40

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
    market_context = output_dir / f"{date}_market_context.json"
    tipster_signal = output_dir / f"{date}_tipster_signal.json"
    superbet_offer = output_dir / f"{date}_superbet_offer.json"

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
            # Absent unless SUPERBET actually wrote one, exactly as ANALYZE
            # treats it: a skipped or failed offer step leaves the gate with
            # its first two rules rather than an empty board it would read as
            # "Superbet prices nothing today".
            if superbet_offer.exists():
                argv += ["--superbet-offer", str(superbet_offer)]
            if args.skip_preflight:
                argv.append("--skip-preflight")
            if args.player_props:
                argv.append("--player-props")
        elif name == "market_context":
            if args.skip_market_context:
                out.event("step_skipped", pipeline_step=name, reason="--skip-market-context")
                continue
            if not event_list.exists():
                out.warning(
                    f"skipping MARKET_CONTEXT: {event_list} is missing, so no price "
                    "can be attributed to a fixture",
                    pipeline_step=name,
                )
                continue
            argv = [
                STEP_SCRIPTS["market_context"],
                "--event-list", str(event_list),
                "--max-events", str(args.max_events),
                "--provider-call-budget", str(args.provider_call_budget),
                *common,
            ]
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
        elif name == "superbet":
            if args.skip_superbet:
                out.event("step_skipped", pipeline_step=name, reason="--skip-superbet")
                continue
            if not event_list.exists():
                out.warning(
                    f"skipping SUPERBET: {event_list} is missing, so no offer can be "
                    "matched to a fixture",
                    pipeline_step=name,
                )
                continue
            argv = [
                STEP_SCRIPTS["superbet"],
                "--event-list", str(event_list),
                # SUPERBET_OFFER_CAP, never args.max_events -- see the constant.
                "--max-events", str(max(args.max_events, SUPERBET_OFFER_CAP)),
                "--oddspapi-bridge", args.oddspapi_bridge,
                *common,
            ]
        else:
            if not dossier.exists():
                out.error(
                    f"cannot start at ANALYZE: {dossier} is missing -- run ENRICH first",
                    recoverable=False,
                )
                out.summary(verdict="PRECONDITION_FAILED", metrics={"run_id": run_id, "date": date})
                sys.exit(2)
            # The event list is the dossier's peer, not an optional column: it
            # is the only source of competition names, and without them the
            # best-of-five gate goes silently inert -- on 2026-09-01 that put
            # ATP tautologies at the top of the sheet. DISCOVER always writes
            # it, so the only way to get here without one is a resume in the
            # wrong directory, which deserves the same hard stop as a missing
            # dossier rather than a sheet that looks fine and is not.
            if not event_list.exists():
                out.error(
                    f"cannot start at ANALYZE: {event_list} is missing -- without "
                    "competition names the best-of-five gate is inert",
                    recoverable=False,
                )
                out.summary(verdict="PRECONDITION_FAILED", metrics={"run_id": run_id, "date": date})
                sys.exit(2)
            argv = [
                STEP_SCRIPTS["analyze"],
                "--dossier", str(dossier),
                "--event-list", str(event_list),
                *common,
            ]
            # Each absent unless its step actually wrote it, so a skipped or
            # failed optional step leaves ANALYZE exactly as it was before that
            # stage existed.
            if market_context.exists():
                argv += ["--market-context", str(market_context)]
            if tipster_signal.exists():
                argv += ["--tipster-signal", str(tipster_signal)]
            if superbet_offer.exists():
                argv += ["--superbet-offer", str(superbet_offer)]

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

        # SUPERBET reports its artifact as ``offer_path``: it writes two
        # (the offer and, later, the comparison) and neither is "the output".
        # Read by name, because ENRICH now gates the slate on this file and
        # falling back to the filename convention would hand it an artifact
        # this run never wrote.
        if name == "superbet" and metrics.get("offer_path"):
            superbet_offer = Path(metrics["offer_path"])

        produced = metrics.get("output_path")
        if produced:
            if name == "discover":
                event_list = Path(produced)
            elif name == "enrich":
                dossier = Path(produced)
            elif name == "market_context":
                market_context = Path(produced)
            elif name == "tipsters":
                tipster_signal = Path(produced)
            elif name == "analyze":
                # By name, not by elimination: a catch-all here would adopt any
                # ``output_path`` another step ever grows as the day's stats
                # sheet.
                stats_sheet = produced

        # SUPERBET's comparison, re-run against the sheet that actually shipped.
        #
        # Not a step in ``STEPS``, deliberately: it is the tail of ANALYZE, it
        # takes no argument of its own, and it must never be addressable by
        # ``--stop-after`` -- a run that stops before it produces a comparison
        # describing a sheet nobody has.
        #
        # It exists because the first SUPERBET pass structurally cannot answer
        # the question its own summary is read for. That pass runs *before*
        # ANALYZE (it has to: ANALYZE consumes its offer), so the only sheet it
        # can be handed is the one about to be overwritten. Measured on
        # 2026-09-02: the comparison covered 8,958 rows over 56 events and the
        # sheet that shipped had 12,300 over 78, so ``verdict_counts.VALUE``
        # read 52 against 82 actually bettable -- 22 whole fixtures missing,
        # and the number was quoted to the operator as the day's yield.
        #
        # ``--offer`` makes this free: no HTTP, no OddsPapi probe, no rewrite
        # of the offer artifact. The prices are the ones ANALYZE priced against,
        # which is the right vintage -- comparing the shipped sheet to a
        # *newer* offer would reintroduce the same skew in the other direction.
        if (
            name == "analyze"
            and stats_sheet
            and superbet_offer.exists()
            and verdict not in ("FAILED", "PRECONDITION_FAILED")
        ):
            compare_verdict, compare_metrics, compare_code = _run_step(
                out,
                "superbet_comparison",
                [
                    STEP_SCRIPTS["superbet"],
                    "--event-list", str(event_list),
                    "--offer", str(superbet_offer),
                    "--stats-sheet", stats_sheet,
                    *common,
                ],
                verbose=args.verbose,
            )
            step_results["superbet_comparison"] = {
                "verdict": compare_verdict,
                "exit_code": compare_code,
                "output_path": compare_metrics.get("comparison_path"),
                "persisted": compare_metrics.get("persisted"),
                "metrics": compare_metrics,
            }

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
        "market_context": str(market_context) if market_context.exists() else None,
        "tipster_signal": str(tipster_signal) if tipster_signal.exists() else None,
        "elapsed_s": round(time.monotonic() - wall_start, 1),
        "started_at": started_at,
    }
    for name, result in step_results.items():
        metrics[f"{name}_metrics"] = result["metrics"]

    # The three fields a reader is told to lead the run report with, hoisted to
    # the top level of this summary. They were only ever reachable inside a
    # nested step block, and only from a pass whose numbers described the wrong
    # sheet -- so the operator either dug for them or quoted them stale. Absent
    # here means SUPERBET did not run or ANALYZE produced no sheet; absent has
    # never meant "empty" and still does not.
    comparison_metrics = step_results.get("superbet_comparison", {}).get("metrics", {})
    for field in ("markets_with_no_line_overlap", "verdict_counts", "value_rows"):
        if field in comparison_metrics:
            metrics[field] = comparison_metrics[field]

    # A machine-readable receipt for the whole run, next to the artifacts it
    # describes -- so a later session can reconstruct what happened without
    # scrollback.
    receipt = output_dir / f"{date}_run_summary.json"
    receipt.write_text(
        json.dumps(
            {"run_id": run_id, "date": date, "verdict": worst, "steps": step_results,
             "started_at": started_at, "elapsed_s": metrics["elapsed_s"],
             # The same block the AGENT_SUMMARY line carries. Omitting it left
             # the receipt without the one field docs/MORNING.md and the
             # run-day command both tell an operator to read
             # (.metrics.analyze_metrics.total_rows), so the documented
             # verification step answered null on every run ever made.
             "metrics": metrics},
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
