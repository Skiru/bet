#!/usr/bin/env python3
"""Settle the dependence question: whose correlation is right, ours or the price's.

`derived.py` prices "każda z drużyn powyżej X" from each side's own marginal
and a dependence measured in `config/sofa_side_correlations.json`. Superbet
prices the same market with an implied dependence of roughly +0.25 in the band
where it is quoted. Those cannot both be right, and the difference is the
whole reason the family is worth pricing at all.

It is answerable without a single price, because "did both teams reach n" is a
fact about a finished match. This replays every finished match in the cache,
builds both sides' marginals from matches strictly before it, and compares
three predictions against what happened:

  * the joint under the measured residual correlation (what ships);
  * the joint under independence (the naive alternative);
  * the joint under +0.25 (what the market's price implies).

Measured on 2026-09-18 over 48,644 goal pairs: 0.3157 / 0.3172 / 0.3496
against an actual 0.3054. Ours is closest, the market's is furthest, and it
errs high — so the market overprices the "tak" side, which is the direction
`derived.py` was built on. It also shows our own joint still runs a little
high, which is why derived rows take the same calibration correction the
marginal path takes.
"""

from __future__ import annotations

import argparse
import collections
import json
import statistics
from pathlib import Path
from typing import Any

from bet.sofa.config import SofaConfig
from bet.sofa.derived import load_side_correlations
from bet.sofa.joint import build_joint
from scripts.sofa.calibrate_from_cache import MIN_SAMPLE, SAMPLE_N, load_cache

# What the market's price implies, taken from the corner ladders quoted on
# 2026-09-18. A single illustrative value, not a per-fixture read.
MARKET_IMPLIED_RHO = 0.25
MIN_ROWS = 200


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", default=None)
    parser.add_argument("--report", default=None)
    args = parser.parse_args()

    config = SofaConfig.from_env()
    played = load_cache(Path(args.db_path or config.db_path))
    correlations = load_side_correlations()

    history: dict[tuple[int, str], list[float]] = collections.defaultdict(list)
    totals: dict[str, list[float]] = collections.defaultdict(lambda: [0, 0, 0, 0])

    for match in played:
        for base, (home_value, away_value) in match.values.items():
            rho = correlations.get(base)
            if rho is None:
                continue
            past_home = history[(match.home_id, base)]
            past_away = history[(match.away_id, base)]
            if len(past_home) < MIN_SAMPLE or len(past_away) < MIN_SAMPLE:
                continue

            side_a = past_home[-SAMPLE_N:]
            side_b = past_away[-SAMPLE_N:]
            mean_a = statistics.mean(side_a)
            mean_b = statistics.mean(side_b)
            if mean_a <= 0 or mean_b <= 0:
                continue
            var_a = statistics.variance(side_a)
            var_b = statistics.variance(side_b)

            measured = build_joint(mean_a, var_a, mean_b, var_b, rho)
            independent = build_joint(mean_a, var_a, mean_b, var_b, 0.0)
            market = build_joint(
                mean_a, var_a, mean_b, var_b, MARKET_IMPLIED_RHO
            )

            for threshold in range(1, 9):
                p_measured = measured.p_both_at_least(threshold, threshold)
                # Only where the model claims to have an opinion at all.
                if not 0.05 <= p_measured <= 0.95:
                    continue
                bucket = totals[base]
                bucket[0] += 1
                bucket[1] += p_measured
                bucket[2] += independent.p_both_at_least(threshold, threshold)
                bucket[3] += market.p_both_at_least(threshold, threshold)
                totals[f"{base}__actual"][0] += 1
                totals[f"{base}__actual"][1] += (
                    1.0
                    if home_value >= threshold and away_value >= threshold
                    else 0.0
                )

        for base, (home_value, away_value) in match.values.items():
            history[(match.home_id, base)].append(home_value)
            history[(match.away_id, base)].append(away_value)

    report: dict[str, Any] = {}
    for base in sorted(b for b in totals if not b.endswith("__actual")):
        count, measured_sum, independent_sum, market_sum = totals[base]
        if count < MIN_ROWS:
            continue
        actual = totals[f"{base}__actual"]
        report[base] = {
            "rows": count,
            "measured_rho": round(correlations.get(base) or 0.0, 4),
            "predicted_measured": round(measured_sum / count, 4),
            "predicted_independent": round(independent_sum / count, 4),
            "predicted_market_rho": round(market_sum / count, 4),
            "actual": round(actual[1] / actual[0], 4),
            "closest": min(
                (
                    ("measured", abs(measured_sum / count - actual[1] / actual[0])),
                    (
                        "independent",
                        abs(independent_sum / count - actual[1] / actual[0]),
                    ),
                    ("market", abs(market_sum / count - actual[1] / actual[0])),
                ),
                key=lambda pair: pair[1],
            )[0],
        }

    if args.report:
        Path(args.report).write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    wins = sum(1 for entry in report.values() if entry["closest"] == "measured")
    summary = {
        "stage": "JOINT_CALIBRATION",
        "verdict": "OK" if report else "PARTIAL",
        "metrics": {
            "metrics_measured": len(report),
            "measured_rho_closest_on": wins,
            "detail": report,
        },
    }
    print(f"SOFA_SUMMARY: {json.dumps(summary)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
