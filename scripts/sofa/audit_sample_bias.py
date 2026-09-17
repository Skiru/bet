#!/usr/bin/env python3
"""T41 — does the sample measure the quantity the bookmaker settles?

Every rule below is an arithmetic identity or a set membership computed from
the day's real artifacts. A rule that cannot be evaluated reports
``UNVERIFIABLE`` with the reason; it never reports ``OK``. "OK" here means
"evaluated on N observations and found no violation", and the N is printed.

Usage:
    python -m scripts.sofa.audit_sample_bias --date 2026-09-18
Exit: 0 = no flags, 1 = flags raised, 2 = could not run.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from bet.sofa.cache import SofaCache
from bet.sofa.config import SofaConfig
from bet.sofa.metrics import infer_best_of
from bet.sofa.samples import FRIENDLY_COMPETITION_IDS

# Metric pairs where the first counts card points and the second counts only
# yellows. cards_points >= cards must hold on every event (L4).
CARD_PAIRS = [("cards_points_total", "cards_total"), ("cards_points_for", "cards_for")]

# (total metric, per-side metric) pairs that must satisfy total == for_a + for_b.
TOTAL_FOR_PAIRS = [
    ("goals_total", "goals_for"),
    ("goals_1h_total", "goals_1h_for"),
    ("goals_2h_total", "goals_2h_for"),
    ("corners_total", "corners_for"),
    ("cards_total", "cards_for"),
    ("cards_points_total", "cards_points_for"),
    ("fouls_total", "fouls_for"),
    ("offsides_total", "offsides_for"),
    ("shots_total", "shots_for"),
    ("shots_on_target_total", "shots_on_target_for"),
    ("games_total", "games_won_for"),
    ("aces_total", "aces_for"),
    ("double_faults_total", "double_faults_for"),
]


@dataclass
class RuleResult:
    name: str
    status: str  # OK | FLAGGED | UNVERIFIABLE
    observations: int = 0
    detail: str = ""
    flags: list[str] = field(default_factory=list)


def _side_observations(metric: dict[str, Any], side: str) -> list[dict[str, Any]]:
    value = metric.get(side)
    return value if isinstance(value, list) else []


def _all_observations(metric: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for side in ("side_a", "side_b", "h2h"):
        out.extend(_side_observations(metric, side))
    return out


def check_card_points(samples: list[dict[str, Any]]) -> RuleResult:
    """Card points must never be below the yellow-only count for the same event."""
    checked = 0
    flags: list[str] = []
    for fixture in samples:
        metrics = fixture.get("metrics", {})
        for points_metric, yellow_metric in CARD_PAIRS:
            if points_metric not in metrics or yellow_metric not in metrics:
                continue
            for side in ("side_a", "side_b"):
                points_by_event = {
                    o["sofascore_event_id"]: o["value"]
                    for o in _side_observations(metrics[points_metric], side)
                }
                for obs in _side_observations(metrics[yellow_metric], side):
                    event_id = obs["sofascore_event_id"]
                    if event_id not in points_by_event:
                        continue
                    checked += 1
                    if points_by_event[event_id] < obs["value"]:
                        flags.append(
                            f"event {event_id}: {points_metric}="
                            f"{points_by_event[event_id]} < {yellow_metric}="
                            f"{obs['value']} — points sample is counting yellows"
                        )
    if checked == 0:
        return RuleResult(
            "cards: points vs yellows",
            "UNVERIFIABLE",
            0,
            "no event carried both a card-points and a yellow-card sample",
        )
    status = "FLAGGED" if flags else "OK"
    return RuleResult("cards: points vs yellows", status, checked, flags=flags)


def check_tiebreak_games(samples: list[dict[str, Any]]) -> RuleResult:
    """games_total must be at least 6 per set played (L5).

    ``serviceGamesTotal`` is one-directionally short by one game per tie-break
    set, so a sample built from it lands below this floor on tie-break matches.
    """
    checked = 0
    flags: list[str] = []
    for fixture in samples:
        metrics = fixture.get("metrics", {})
        if "games_total" not in metrics or "sets_total" not in metrics:
            continue
        sets_by_event = {
            o["sofascore_event_id"]: o["value"]
            for o in _all_observations(metrics["sets_total"])
        }
        for obs in _all_observations(metrics["games_total"]):
            event_id = obs["sofascore_event_id"]
            if event_id not in sets_by_event:
                continue
            checked += 1
            floor = 6.0 * sets_by_event[event_id]
            if obs["value"] < floor:
                flags.append(
                    f"event {event_id}: games_total={obs['value']} below the "
                    f"floor of {floor:g} for {sets_by_event[event_id]:g} sets "
                    "— tie-break games are missing from the sample"
                )
    if checked == 0:
        return RuleResult(
            "tennis: games include tie-breaks",
            "UNVERIFIABLE",
            0,
            "no event carried both a games_total and a sets_total sample",
        )
    status = "FLAGGED" if flags else "OK"
    return RuleResult("tennis: games include tie-breaks", status, checked, flags=flags)


def check_total_vs_for(samples: list[dict[str, Any]]) -> RuleResult:
    """total == for(side_a) + for(side_b) on the same historical event (L6)."""
    checked = 0
    flags: list[str] = []
    for fixture in samples:
        metrics = fixture.get("metrics", {})
        for total_metric, for_metric in TOTAL_FOR_PAIRS:
            if total_metric not in metrics or for_metric not in metrics:
                continue
            # A historical event appears in side_a's history from side_a's
            # perspective; the same event carries both participants' values
            # only when it is a head-to-head. Use h2h, where both are present.
            for_a = {
                o["sofascore_event_id"]: o["value"]
                for o in _side_observations(metrics[for_metric], "side_a")
            }
            for_b = {
                o["sofascore_event_id"]: o["value"]
                for o in _side_observations(metrics[for_metric], "side_b")
            }
            totals = {
                o["sofascore_event_id"]: o["value"]
                for o in _all_observations(metrics[total_metric])
            }
            for event_id in set(for_a) & set(for_b) & set(totals):
                checked += 1
                expected = for_a[event_id] + for_b[event_id]
                if abs(totals[event_id] - expected) > 1e-6:
                    flags.append(
                        f"event {event_id}: {total_metric}={totals[event_id]} "
                        f"but {for_metric} sides sum to {expected} "
                        f"({for_a[event_id]} + {for_b[event_id]})"
                    )
    if checked == 0:
        return RuleResult(
            "_total vs _for",
            "UNVERIFIABLE",
            0,
            "no head-to-head event carried both a _total and both sides' _for",
        )
    status = "FLAGGED" if flags else "OK"
    return RuleResult("_total vs _for", status, checked, flags=flags)


def check_friendlies(
    samples: list[dict[str, Any]], sport_by_event: dict[int, str]
) -> RuleResult:
    """No friendly competition may contribute to a football counting sample."""
    checked = 0
    flags: list[str] = []
    for fixture in samples:
        if sport_by_event.get(fixture["sofascore_event_id"]) != "football":
            continue
        for metric_name, metric in fixture.get("metrics", {}).items():
            for obs in _all_observations(metric):
                checked += 1
                comp_id = obs.get("competition_id")
                if comp_id is not None and int(comp_id) in FRIENDLY_COMPETITION_IDS:
                    flags.append(
                        f"fixture {fixture['sofascore_event_id']} metric "
                        f"{metric_name}: event {obs['sofascore_event_id']} is "
                        f"from friendly competition {comp_id}"
                    )
    if checked == 0:
        return RuleResult(
            "football: friendlies excluded",
            "UNVERIFIABLE",
            0,
            "no football observation in this run",
        )
    status = "FLAGGED" if flags else "OK"
    return RuleResult("football: friendlies excluded", status, checked, flags=flags)


def check_tennis_surface(
    samples: list[dict[str, Any]],
    fixtures_by_id: dict[int, dict[str, Any]],
    cache: SofaCache | None,
) -> RuleResult:
    """Every tennis observation must come from the fixture's own surface and format.

    Ground type is not carried on ``Observation``, so this reads the cached
    entity listings the sample was built from. Without that cache the rule is
    UNVERIFIABLE — it is never reported as passing.
    """
    if cache is None:
        return RuleResult(
            "tennis: surface and best_of",
            "UNVERIFIABLE",
            0,
            "no cache database available to look up each event's groundType",
        )

    ground_by_event: dict[int, tuple[str | None, int | None]] = {}
    for entity_id, kind, page, payload in cache.iter_entity_events():
        del entity_id, kind, page
        for event in payload.get("events", []):
            event_id = event.get("id")
            if event_id is not None:
                # Format comes from infer_best_of, not from defaultPeriodCount:
                # that field is absent from every listing event, so reading it
                # here would flag every tennis observation as a mismatch and
                # bury the real ones. This must use the same rule the sampler
                # filtered on, or the audit is checking a different pipeline.
                ground_by_event[int(event_id)] = (
                    event.get("groundType"),
                    infer_best_of(event),
                )

    checked = 0
    unknown = 0
    flags: list[str] = []
    for fixture in samples:
        meta = fixtures_by_id.get(fixture["sofascore_event_id"])
        if not meta or meta.get("sport") != "tennis":
            continue
        want_ground = meta.get("ground_type")
        want_best_of = meta.get("best_of")
        for metric_name, metric in fixture.get("metrics", {}).items():
            for obs in _all_observations(metric):
                event_id = obs["sofascore_event_id"]
                if event_id not in ground_by_event:
                    unknown += 1
                    continue
                checked += 1
                got_ground, got_best_of = ground_by_event[event_id]
                if want_ground is not None and got_ground != want_ground:
                    flags.append(
                        f"fixture {fixture['sofascore_event_id']} metric "
                        f"{metric_name}: event {event_id} played on "
                        f"{got_ground!r}, fixture is {want_ground!r}"
                    )
                if want_best_of is not None and got_best_of != want_best_of:
                    flags.append(
                        f"fixture {fixture['sofascore_event_id']} metric "
                        f"{metric_name}: event {event_id} is best-of-"
                        f"{got_best_of}, fixture is best-of-{want_best_of}"
                    )
    if checked == 0:
        return RuleResult(
            "tennis: surface and best_of",
            "UNVERIFIABLE",
            0,
            f"no tennis observation could be traced to a cached listing "
            f"({unknown} untraceable)",
        )
    status = "FLAGGED" if flags else "OK"
    detail = f"{unknown} observation(s) untraceable to a cached listing"
    return RuleResult(
        "tennis: surface and best_of", status, checked, detail, flags=flags
    )


def check_zero_inflation(samples: list[dict[str, Any]]) -> RuleResult:
    """A metric whose pooled median is 0 is a provider gap wearing a value (L1)."""
    checked = 0
    values_by_metric: dict[str, list[float]] = defaultdict(list)
    for fixture in samples:
        for metric_name, metric in fixture.get("metrics", {}).items():
            for obs in _all_observations(metric):
                values_by_metric[metric_name].append(float(obs["value"]))
                checked += 1

    flags: list[str] = []
    for metric_name, values in sorted(values_by_metric.items()):
        if len(values) < 5:
            continue
        if statistics.median(values) == 0.0:
            zeros = sum(1 for v in values if v == 0.0)
            flags.append(
                f"{metric_name}: median is 0 over {len(values)} observations "
                f"({zeros} of them exactly 0) — likely a missing key read as zero"
            )
    if checked == 0:
        return RuleResult("zero inflation", "UNVERIFIABLE", 0, "no observations")
    status = "FLAGGED" if flags else "OK"
    return RuleResult("zero inflation", status, checked, flags=flags)


def check_one_row_one_sample(samples: list[dict[str, Any]]) -> RuleResult:
    """One historical event contributes one observation per side (L13)."""
    checked = 0
    flags: list[str] = []
    for fixture in samples:
        for metric_name, metric in fixture.get("metrics", {}).items():
            for side in ("side_a", "side_b"):
                seen: set[int] = set()
                for obs in _side_observations(metric, side):
                    checked += 1
                    event_id = obs["sofascore_event_id"]
                    if event_id in seen:
                        flags.append(
                            f"fixture {fixture['sofascore_event_id']} metric "
                            f"{metric_name} {side}: event {event_id} appears twice"
                        )
                    seen.add(event_id)
    if checked == 0:
        return RuleResult("one row, one sample", "UNVERIFIABLE", 0, "no observations")
    status = "FLAGGED" if flags else "OK"
    return RuleResult("one row, one sample", status, checked, flags=flags)


def run_audit(
    samples: list[dict[str, Any]],
    fixtures: list[dict[str, Any]],
    cache: SofaCache | None,
) -> list[RuleResult]:
    fixtures_by_id = {int(f["sofascore_event_id"]): f for f in fixtures}
    sport_by_event = {k: str(v.get("sport", "")) for k, v in fixtures_by_id.items()}
    return [
        check_card_points(samples),
        check_tiebreak_games(samples),
        check_total_vs_for(samples),
        check_friendlies(samples, sport_by_event),
        check_tennis_surface(samples, fixtures_by_id, cache),
        check_zero_inflation(samples),
        check_one_row_one_sample(samples),
    ]


def render_report(results: list[RuleResult], date_str: str) -> str:
    lines = [
        "# Sample Bias Audit (T41)",
        "",
        f"Run date: `{date_str}`",
        "",
        "Does the sample measure the quantity the bookmaker settles? Each rule "
        "below was evaluated against this day's real observations. `OK` means "
        "evaluated and clean; `UNVERIFIABLE` means the data to evaluate it was "
        "not present and the rule was *not* checked.",
        "",
        "| Rule | Status | Observations checked | Flags |",
        "|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| {r.name} | **{r.status}** | {r.observations} | {len(r.flags)} |"
        )

    lines.append("")
    for r in results:
        lines.append(f"## {r.name}")
        lines.append("")
        lines.append(f"- Status: **{r.status}**")
        lines.append(f"- Observations checked: {r.observations}")
        if r.detail:
            lines.append(f"- Note: {r.detail}")
        if r.flags:
            lines.append("- Violations:")
            for flag in r.flags[:50]:
                lines.append(f"  - {flag}")
            if len(r.flags) > 50:
                lines.append(f"  - … and {len(r.flags) - 50} more")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit sample bias (T41)")
    parser.add_argument("--date", required=True, help="Run date YYYY-MM-DD")
    args = parser.parse_args()

    config = SofaConfig.from_env()
    run_dir = Path(config.runs_dir) / args.date
    samples_path = run_dir / "03_samples.json"
    fixtures_path = run_dir / "02_fixtures.json"

    if not samples_path.exists():
        print(f"File not found: {samples_path}", file=sys.stderr)
        return 2

    samples = json.loads(samples_path.read_text(encoding="utf-8"))
    fixtures = (
        json.loads(fixtures_path.read_text(encoding="utf-8"))
        if fixtures_path.exists()
        else []
    )

    cache: SofaCache | None
    try:
        cache = SofaCache(config)
    except Exception:  # noqa: BLE001 - a missing DB makes one rule UNVERIFIABLE
        cache = None

    results = run_audit(samples, fixtures, cache)

    report_path = run_dir / "audit_sample_bias_report.md"
    report_path.write_text(render_report(results, args.date), encoding="utf-8")

    flagged = [r for r in results if r.status == "FLAGGED"]
    unverifiable = [r for r in results if r.status == "UNVERIFIABLE"]
    summary = {
        "stage": "AUDIT_BIAS",
        "verdict": "PARTIAL" if flagged else "OK",
        "metrics": {
            "rules": len(results),
            "flagged": len(flagged),
            "unverifiable": len(unverifiable),
            "flags": sum(len(r.flags) for r in results),
        },
        "output_path": str(report_path),
    }
    print(f"SOFA_SUMMARY: {json.dumps(summary)}")
    return 1 if flagged else 0


if __name__ == "__main__":
    sys.exit(main())
