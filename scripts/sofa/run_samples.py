#!/usr/bin/env python3
"""SAMPLES — E6. Builds 03_samples.json for the day's fixtures."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from pydantic import RootModel

from bet.sofa.artifact_guard import incomplete_reason
from bet.sofa.atomic import write_atomic
from bet.sofa.cache import SofaCache
from bet.sofa.client import SofascoreClient, breaker_tripped
from bet.sofa.config import SofaConfig
from bet.sofa.contracts import (
    Fixture,
    FixtureOffer,
    FixtureSamples,
    GapEntry,
    GapReason,
)
from bet.sofa.coverage import check_coverage_floor
from bet.sofa.epochs import (
    football_player_coverage,
    identity_gate_per_family,
    men_friendly_sample_window,
    player_name_surname,
    player_name_tokens,
    player_starts_only,
    shot_detail_markets,
)
from bet.sofa.late_resolve import merge_by_event, parse_event_ids
from bet.sofa.samples import (
    FRIENDLY_COMPETITION_IDS,
    compute_readiness,
    process_fixture_samples,
)
from bet.sofa.stage import current_stage, set_stage
from bet.sofa.superbet import SuperbetClient
from bet.sofa.timeutil import now

# Gaps that mean "we could not ask", as opposed to "we asked and there is
# nothing there". Only the first kind may be repaired from a previous run.
_PROVIDER_FAULT_GAPS = {GapReason.CIRCUIT_OPEN, GapReason.PROVIDER_ERROR}


def load_previous_samples(path: Path) -> dict[int, FixtureSamples]:
    if not path.exists():
        return {}
    try:
        previous = (
            RootModel[list[FixtureSamples]]
            .model_validate_json(path.read_bytes())
            .root
        )
    except (OSError, ValueError):
        return {}
    return {s.sofascore_event_id: s for s in previous}


def carry_over_on_provider_fault(
    fresh: FixtureSamples, previous: FixtureSamples | None
) -> tuple[FixtureSamples, bool]:
    """Keep what the last run knew when this run could not reach the provider.

    Deliberately narrow. It only fires when the fresh result has **no**
    metrics at all and **every** gap is a provider fault, and it never
    resurrects a fixture whose metrics are simply absent from the source or
    whose markets are no longer priced — a match that kicked off must drop off
    the day, and NO_PRICE is not a fault to repair.
    """
    if previous is None or not previous.metrics:
        return fresh, False
    if fresh.metrics:
        return fresh, False
    if not fresh.gaps:
        return fresh, False
    if not all(gap.reason in _PROVIDER_FAULT_GAPS for gap in fresh.gaps):
        return fresh, False

    return (
        fresh.model_copy(
            update={
                "metrics": previous.metrics,
                "readiness": previous.readiness,
                # The carried metrics were sampled under the previous run's
                # identity gate, not this run's (rebuild_plan step 1c
                # re-tries such an entry).
                "identity_gate": previous.identity_gate,
                "gaps": [
                    *fresh.gaps,
                    GapEntry(
                        reason=GapReason.PROVIDER_ERROR,
                        metric="all",
                        detail=(
                            "provider unreachable this run; sample carried "
                            "over from the previous run of this date"
                        ),
                    ),
                ],
            }
        ),
        True,
    )


# One Superbet client per worker thread. `SuperbetClient` wraps a curl_cffi
# Session, which is not documented thread-safe, and the fallback path in
# SAMPLES does reach it — an offer entry that names no market falls through to
# a live call. Sharing one session across the pool is the kind of defect that
# shows up as a corrupted response weeks later, so each thread gets its own.
_THREAD_LOCAL = threading.local()


def superbet_for_thread() -> SuperbetClient:
    client = getattr(_THREAD_LOCAL, "superbet", None)
    if client is None:
        client = SuperbetClient()
        _THREAD_LOCAL.superbet = client
    return client


def samples_verdict(
    *,
    ready: int,
    n_fixtures: int,
    unreachable: bool,
    coverage_partial: bool,
    provider_faulted: int,
    carried_over: int = 0,
) -> str:
    """FAILED with nothing READY, PARTIAL on any named shortfall, else OK.

    A sample carried over from the previous run on a provider fault is a
    shortfall too: the day was not asked. Before F6.1 a refused SAMPLES whose
    every fixture was carried over exited OK - a silent success.
    """
    if ready == 0 and n_fixtures:
        return "FAILED"
    if unreachable or coverage_partial or provider_faulted or carried_over:
        return "PARTIAL"
    return "OK"


def sample_fixtures_concurrently(
    fixtures: list[Fixture],
    client: SofascoreClient,
    cache: SofaCache,
    config: SofaConfig,
    offers_by_id: dict[int, FixtureOffer],
    *,
    token_fallback: bool = False,
    starts_only: bool = False,
    men_friendly_window: bool = False,
    surname_fallback: bool = False,
    shot_detail: bool = False,
    player_coverage: bool = False,
    per_family_identity: bool = False,
) -> list[FixtureSamples]:
    """One FixtureSamples per fixture, in the input's order.

    Order is part of the contract, not a nicety: 03_samples.json is diffed
    against the previous run and read by a human, so the artifact must not
    depend on which worker happened to finish first. `ThreadPoolExecutor.map`
    yields in submission order, which is what gives us that for free.

    Why a pool at all: the bridge round trip is ~175 ms and the userscript
    paces each *tab* at 350 ms, so one tab tops out near 2.9 req/s no matter
    what the Python side does. The queue in bridge_server.claim() is not bound
    to a tab — every /pull pops a different job — so K tabs serve K jobs at
    once, each still pacing itself. Concurrency here is what lets the pipeline
    actually have K jobs in flight to give them.

    It is not, on its own, a speed-up: `SofascoreClient` still holds one global
    token bucket at SOFA_TARGET_RPS, so with the default of 2 this pool will
    sit idle waiting for tokens. The rate and the tab count have to move
    together, and that is deliberately the operator's decision - see
    docs/sofa/CONFIG.md.
    """
    workers = max(1, config.max_concurrency)
    if workers == 1 or len(fixtures) < 2:
        return [
            process_fixture_samples(
                fixture,
                client,
                cache,
                superbet_for_thread(),
                config,
                offer=offers_by_id.get(fixture.sofascore_event_id),
                token_fallback=token_fallback,
                starts_only=starts_only,
                men_friendly_window=men_friendly_window,
                surname_fallback=surname_fallback,
                shot_detail=shot_detail,
                player_coverage=player_coverage,
                per_family_identity=per_family_identity,
            )
            for fixture in fixtures
        ]

    # `stage` is a ContextVar, and a fresh thread starts from the default
    # context - so without this every request a worker makes would log
    # stage "CLIENT" and the per-stage cost accounting (F8, F22) would
    # quietly stop working the moment the pool was switched on.
    stage = current_stage()

    def one(fixture: Fixture) -> FixtureSamples:
        set_stage(stage)
        return process_fixture_samples(
            fixture,
            client,
            cache,
            superbet_for_thread(),
            config,
            offer=offers_by_id.get(fixture.sofascore_event_id),
            token_fallback=token_fallback,
            starts_only=starts_only,
            men_friendly_window=men_friendly_window,
            surname_fallback=surname_fallback,
            shot_detail=shot_detail,
            player_coverage=player_coverage,
            per_family_identity=per_family_identity,
        )

    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(one, fixtures))


def main() -> int:
    # Every request underneath this call is this stage's cost (F22).
    set_stage("SAMPLES")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default=now().strftime("%Y-%m-%d"), help="YYYY-MM-DD")
    parser.add_argument(
        "--event-ids", default=None,
        help="comma-separated Sofascore event ids: sample only these fixtures and "
        "merge them into 03_samples.json, every other fixture's entry kept as it "
        "was (the late RESOLVE pass, bet.sofa.late_resolve)")
    args = parser.parse_args()
    only_ids = parse_event_ids(args.event_ids)

    config = SofaConfig.from_env()
    client = SofascoreClient(config)
    cache = SofaCache(config)

    run_dir = Path(config.runs_dir) / args.date
    fixtures_path = run_dir / "02_fixtures.json"
    if not fixtures_path.exists():
        print(f"{fixtures_path} missing", file=sys.stderr)
        return 2
    refusal = incomplete_reason(fixtures_path)
    if refusal:
        print(refusal, file=sys.stderr)
        return 2

    fixtures = (
        RootModel[list[Fixture]].model_validate_json(fixtures_path.read_bytes()).root
    )
    if only_ids is not None:
        fixtures = [f for f in fixtures if f.sofascore_event_id in only_ids]

    cache_hits = 0
    network_requests = 0
    original_get_event_stats = cache.get_event_stats
    # `x += 1` is load/add/store, so several workers can read the same value
    # and one increment is lost. These two numbers go into the run summary and
    # into the cache-efficiency argument; a counter that silently undercounts
    # is worse than no counter.
    counter_lock = threading.Lock()

    def tracked_get_event_stats(event_id: int, kickoff_ts: int | None = None) -> Any:
        nonlocal cache_hits, network_requests
        result = original_get_event_stats(event_id, kickoff_ts=kickoff_ts)
        with counter_lock:
            if result:
                cache_hits += 1
            else:
                network_requests += 1
        return result

    cache.get_event_stats = tracked_get_event_stats  # type: ignore[method-assign,assignment]

    all_samples = []
    gap_counts: dict[str, int] = defaultdict(int)
    readiness_counts: dict[str, int] = defaultdict(int)
    readiness_by_sport: dict[str, dict[str, int]] = defaultdict(
        lambda: defaultdict(int)
    )
    metric_sizes: dict[str, list[int]] = defaultdict(list)
    per_metric_readiness: dict[str, dict[str, int]] = defaultdict(
        lambda: defaultdict(int)
    )
    total_metrics = 0

    # The pre-sample OFFER's artifact, if it ran. Reading it here is what
    # turns that stage from a dead one into the gate A4 always described:
    # SAMPLES used to ask Superbet again, once per fixture, ~600 requests a
    # day to re-learn what this file already says (F19). A fixture the artifact
    # does not cover still falls back to a live call, so a missing or partial
    # offer costs requests rather than coverage.
    offer_path = run_dir / "04_offer.json"
    offers_by_id: dict[int, FixtureOffer] = {}
    if offer_path.exists():
        offers_by_id = {
            o.sofascore_event_id: o
            for o in RootModel[list[FixtureOffer]]
            .model_validate_json(offer_path.read_bytes())
            .root
        }
    print(
        f"offer artifact covers {len(offers_by_id)} of {len(fixtures)} fixtures",
        file=sys.stderr,
        flush=True,
    )

    # What this date already knew. A sample is history — the corners a team
    # took last month do not change because the provider timed out today — so
    # a run that cannot reach Sofascore must not *delete* them. Re-running
    # SAMPLES on 2026-09-18 to pick up a newly mapped metric dropped 13
    # fixtures off the day for exactly this reason: the circuit breaker
    # opened, every metric came back empty, and the artifact was overwritten
    # with the emptiness (F41).
    previous_by_id = load_previous_samples(run_dir / "03_samples.json")
    carried_over = 0
    # Fixtures that lost metrics to a provider fault and had nothing to carry
    # over. They used to leave the verdict OK (review 2026-10-01): a breaker
    # opening mid-SAMPLES thinned the day with nothing in the summary saying so.
    provider_faulted = 0

    sampled = sample_fixtures_concurrently(
        fixtures, client, cache, config, offers_by_id,
        token_fallback=player_name_tokens(args.date),
        starts_only=player_starts_only(args.date),
        # epochs.MEN_FRIENDLY_SAMPLE_WINDOW (off: byte-identical)
        men_friendly_window=men_friendly_sample_window(args.date),
        # epochs.PLAYER_NAME_SURNAME (identity plan K7; off: byte-identical)
        surname_fallback=player_name_surname(args.date),
        # epochs.SHOT_DETAIL_MARKETS (off: no shotmap asked, byte-identical)
        shot_detail=shot_detail_markets(args.date),
        # epochs.FOOTBALL_PLAYER_COVERAGE (off: byte-identical)
        player_coverage=football_player_coverage(args.date),
        # epochs.IDENTITY_GATE_PER_FAMILY (off: byte-identical - an unset
        # identity_gate is not written)
        per_family_identity=identity_gate_per_family(args.date),
    )

    for fixture, samples in zip(fixtures, sampled, strict=True):
        samples, carried = carry_over_on_provider_fault(
            samples, previous_by_id.get(fixture.sofascore_event_id)
        )
        if carried:
            carried_over += 1
        elif any(g.reason in _PROVIDER_FAULT_GAPS for g in samples.gaps):
            provider_faulted += 1
        all_samples.append(samples)

        readiness_counts[samples.readiness] += 1
        readiness_by_sport[fixture.sport][samples.readiness] += 1
        for gap in samples.gaps:
            gap_counts[gap.reason.value] += 1
        total_metrics += len(samples.metrics)

        _, per_metric = compute_readiness(samples.metrics, config.min_sample)
        for metric_name, state in per_metric.items():
            per_metric_readiness[metric_name][state] += 1

        for metric_name, metric_sample in samples.metrics.items():
            unique_ids = {
                o.sofascore_event_id
                for o in metric_sample.side_a + metric_sample.side_b + metric_sample.h2h
            }
            metric_sizes[metric_name].append(len(unique_ids))

    run_dir.mkdir(parents=True, exist_ok=True)
    out_path = run_dir / "03_samples.json"
    dumped = [s.model_dump(mode="json", exclude=None if s.identity_gate
                           else {"identity_gate"}) for s in all_samples]
    replaced_previous = 0
    if only_ids is not None:
        # the late RESOLVE pass: the other fixtures' entries as they were
        previous_raw = (json.loads(out_path.read_text(encoding="utf-8"))
                        if out_path.exists() else [])
        dumped, replaced_previous = merge_by_event(
            previous_raw, dumped, {f.sofascore_event_id for f in fixtures})
    write_atomic(
        out_path,
        json.dumps(
            dumped,
            indent=2,
            ensure_ascii=False,
        ),
    )

    # T40: the coverage floor, per sport, against this pipeline's own history.
    coverage = check_coverage_floor(config.runs_dir, args.date)
    # Not `verdict`: that name is the stage's own verdict a few lines below,
    # and one name for two things is how a type error hides in plain sight.
    for cov in coverage:
        if cov.status == "PARTIAL":
            print(f"COVERAGE_FLOOR {cov.sport}: {cov.detail}", file=sys.stderr)

    median_sizes = {
        m: statistics.median(sizes) for m, sizes in metric_sizes.items() if sizes
    }

    # §3.3/L14: a gate nobody can reach looks like missing data. Say it plainly.
    sports_present = {f.sport for f in fixtures}
    unreachable = [
        sport
        for sport in sorted(sports_present)
        if readiness_by_sport[sport].get("READY", 0) == 0
    ]

    coverage_partial = any(v.status == "PARTIAL" for v in coverage)
    verdict = samples_verdict(
        ready=readiness_counts.get("READY", 0),
        n_fixtures=len(fixtures),
        unreachable=bool(unreachable),
        coverage_partial=coverage_partial,
        provider_faulted=provider_faulted,
        carried_over=carried_over,
    )
    if only_ids is not None and verdict == "FAILED" and fixtures:
        # a late pass's handful of fixtures with nothing READY is a thin
        # addition, not a broken stage: the entries are written (BLOCKED)
        verdict = "PARTIAL"

    summary = {
        "stage": "SAMPLES",
        "verdict": verdict,
        "metrics": {
            "input_fixtures": len(fixtures),
            "output_samples": len(all_samples),
            **({"event_ids_only": len(only_ids),
                "replaced_previous_entries": replaced_previous,
                "entries_written": len(dumped)}
               if only_ids is not None else {}),
            "carried_over_on_provider_fault": carried_over,
            "provider_fault_fixtures": provider_faulted,
            # The breaker ended the stage open (F6.1): every fixture after it
            # was BLOCKED CIRCUIT_OPEN or carried over without a request.
            "breaker_open": breaker_tripped(client),
            "total_metrics_extracted": total_metrics,
            "readiness": dict(readiness_counts),
            "readiness_by_sport": {k: dict(v) for k, v in readiness_by_sport.items()},
            "readiness_by_metric": {
                k: dict(v) for k, v in sorted(per_metric_readiness.items())
            },
            "sports_with_zero_ready": unreachable,
            "gaps": dict(
                sorted(gap_counts.items(), key=lambda kv: kv[1], reverse=True)[:10]
            ),
            "cache_hits": cache_hits,
            "network_requests": network_requests,
            "median_sample_size": median_sizes,
            "friendly_competitions_excluded": len(FRIENDLY_COMPETITION_IDS),
            "coverage_floor": [
                {
                    "sport": v.sport,
                    "status": v.status,
                    "current": v.current,
                    "median": v.median,
                    "history_runs": v.history_runs,
                    # The quantity the verdict is actually decided on. `median`
                    # above is back-projected into counts for readability and
                    # is NOT what was compared — reporting only it is how a
                    # quiet Monday read as a matching regression.
                    "current_share": v.current_share,
                    "median_share": v.median_share,
                    "detail": v.detail,
                }
                for v in coverage
            ],
        },
        "output_path": str(out_path),
    }
    print(f"SOFA_SUMMARY: {json.dumps(summary)}", flush=True)
    return {"OK": 0, "PARTIAL": 1, "FAILED": 2}[verdict]


if __name__ == "__main__":
    sys.exit(main())
