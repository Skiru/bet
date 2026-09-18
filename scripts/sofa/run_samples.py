#!/usr/bin/env python3
"""SAMPLES — E6. Builds 03_samples.json for the day's fixtures."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from pydantic import RootModel

from bet.sofa.cache import SofaCache
from bet.sofa.client import SofascoreClient
from bet.sofa.config import SofaConfig
from bet.sofa.contracts import Fixture
from bet.sofa.coverage import check_coverage_floor
from bet.sofa.samples import (
    FRIENDLY_COMPETITION_IDS,
    compute_readiness,
    process_fixture_samples,
)
from bet.sofa.superbet import SuperbetClient
from bet.sofa.timeutil import now


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default=now().strftime("%Y-%m-%d"), help="YYYY-MM-DD")
    args = parser.parse_args()

    config = SofaConfig.from_env()
    client = SofascoreClient(config)
    cache = SofaCache(config)
    superbet_client = SuperbetClient()

    run_dir = Path(config.runs_dir) / args.date
    fixtures_path = run_dir / "02_fixtures.json"
    if not fixtures_path.exists():
        print(f"{fixtures_path} missing", file=sys.stderr)
        return 2

    fixtures = (
        RootModel[list[Fixture]].model_validate_json(fixtures_path.read_bytes()).root
    )

    cache_hits = 0
    network_requests = 0
    original_get_event_stats = cache.get_event_stats

    def tracked_get_event_stats(event_id: int) -> Any:
        nonlocal cache_hits, network_requests
        result = original_get_event_stats(event_id)
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

    for fixture in fixtures:
        samples = process_fixture_samples(
            fixture, client, cache, superbet_client, config
        )
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
    out_path.write_text(
        json.dumps(
            [s.model_dump(mode="json") for s in all_samples],
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
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
    if readiness_counts.get("READY", 0) == 0 and fixtures:
        verdict = "FAILED"
    elif unreachable or coverage_partial:
        verdict = "PARTIAL"
    else:
        verdict = "OK"

    summary = {
        "stage": "SAMPLES",
        "verdict": verdict,
        "metrics": {
            "input_fixtures": len(fixtures),
            "output_samples": len(all_samples),
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
                    "detail": v.detail,
                }
                for v in coverage
            ],
        },
        "output_path": str(out_path),
    }
    print(f"SOFA_SUMMARY: {json.dumps(summary)}")
    return {"OK": 0, "PARTIAL": 1, "FAILED": 2}[verdict]


if __name__ == "__main__":
    sys.exit(main())
