"""T40 — the coverage floor (PLAN §E12, L32).

Silent degradation is the failure mode this catches: `/search/all` changes its
behaviour, matching quietly gets worse, the slate shrinks and nobody notices
because a smaller slate looks exactly like a quieter day.

Computed **per sport**. A shared median fires on whichever sport happens to have
grown and stays silent about the one that collapsed.
"""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass
from pathlib import Path

SPORTS = ("football", "tennis")

# A drop of more than this fraction below the rolling median is a PARTIAL.
MAX_DROP = 0.40
HISTORY_WINDOW = 10
# Fewer past runs than this and the median is not a median.
MIN_HISTORY = 3


@dataclass(frozen=True)
class CoverageVerdict:
    sport: str
    current: int
    median: float
    history_runs: int
    status: str  # OK | PARTIAL | NO_BASELINE
    detail: str


def _ready_counts(run_dir: Path) -> dict[str, int] | None:
    """READY fixtures per sport for one run directory, or None if incomplete."""
    samples_path = run_dir / "03_samples.json"
    fixtures_path = run_dir / "02_fixtures.json"
    if not samples_path.exists() or not fixtures_path.exists():
        return None

    try:
        samples = json.loads(samples_path.read_text(encoding="utf-8"))
        fixtures = json.loads(fixtures_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None

    sport_by_event = {f["sofascore_event_id"]: f["sport"] for f in fixtures}
    counts = dict.fromkeys(SPORTS, 0)
    for sample in samples:
        if sample.get("readiness") != "READY":
            continue
        sport = sport_by_event.get(sample["sofascore_event_id"])
        if sport in counts:
            counts[sport] += 1
    return counts


def check_coverage_floor(runs_dir: str, current_date: str) -> list[CoverageVerdict]:
    """Compare today's READY count per sport to its own rolling median."""
    root = Path(runs_dir)
    current = _ready_counts(root / current_date)
    if current is None:
        return [
            CoverageVerdict(
                sport, 0, 0.0, 0, "NO_BASELINE", "no artifacts for the current date"
            )
            for sport in SPORTS
        ]

    history: dict[str, list[int]] = {sport: [] for sport in SPORTS}
    if root.exists():
        past_dates = sorted(
            d.name
            for d in root.iterdir()
            if d.is_dir() and len(d.name) == 10 and d.name < current_date
        )
        for date in past_dates[-HISTORY_WINDOW:]:
            counts = _ready_counts(root / date)
            if counts is None:
                continue
            for sport in SPORTS:
                history[sport].append(counts[sport])

    verdicts: list[CoverageVerdict] = []
    for sport in SPORTS:
        past = history[sport]
        if len(past) < MIN_HISTORY:
            verdicts.append(
                CoverageVerdict(
                    sport,
                    current[sport],
                    0.0,
                    len(past),
                    "NO_BASELINE",
                    f"only {len(past)} comparable past run(s), need {MIN_HISTORY}",
                )
            )
            continue

        median = statistics.median(past)
        if median <= 0:
            verdicts.append(
                CoverageVerdict(
                    sport,
                    current[sport],
                    median,
                    len(past),
                    "NO_BASELINE",
                    "rolling median is zero; nothing to drop from",
                )
            )
            continue

        floor = median * (1.0 - MAX_DROP)
        if current[sport] < floor:
            verdicts.append(
                CoverageVerdict(
                    sport,
                    current[sport],
                    median,
                    len(past),
                    "PARTIAL",
                    f"{current[sport]} READY vs median {median:g} "
                    f"(floor {floor:.1f}); a drop this size is a matching "
                    f"regression until proven otherwise",
                )
            )
        else:
            verdicts.append(
                CoverageVerdict(
                    sport,
                    current[sport],
                    median,
                    len(past),
                    "OK",
                    f"{current[sport]} READY vs median {median:g}",
                )
            )
    return verdicts
