"""T40 — the coverage floor (PLAN §E12, L32).

Silent degradation is the failure mode this catches: `/search/all` changes its
behaviour, matching quietly gets worse, the slate shrinks and nobody notices
because a smaller slate looks exactly like a quieter day.

Computed **per sport**. A shared median fires on whichever sport happens to have
grown and stays silent about the one that collapsed.

Measured as a **share of the board, not a count** (2026-09-21). The floor's own
message says "a matching regression until proven otherwise", and a matching
regression is a fall in the fraction of discovered fixtures we can sample — it
is not a fall in how many fixtures exist. Slate size belongs to the calendar:
2026-09-20 (Sunday) put 1040 football fixtures on Superbet's board, 2026-09-21
(Monday) put 102. Against a median built from three weekend runs, that Monday
read "66 READY vs median 406" and declared a regression, while its RESOLVE rate
of 79.4% sat squarely inside the 72-90% of the days it was being compared to.
A counting floor cannot tell a quiet Monday from a broken matcher; a ratio can.
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
    # The quantity actually compared: READY as a share of the board. The count
    # fields above stay because the operator reads them, but they are not what
    # decides the verdict.
    current_share: float | None = None
    median_share: float | None = None


def _board_counts(run_dir: Path) -> dict[str, int] | None:
    """Fixtures per sport that RESOLVE was given, for one run directory.

    The denominator of the ratio. Read from 02_fixtures.json rather than
    01_board.json so the share measures sampling, not name-matching — RESOLVE
    has its own recall number and conflating the two hides both.
    """
    fixtures_path = run_dir / "02_fixtures.json"
    if not fixtures_path.exists():
        return None
    try:
        fixtures = json.loads(fixtures_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    counts = dict.fromkeys(SPORTS, 0)
    for f in fixtures:
        if f.get("sport") in counts:
            counts[f["sport"]] += 1
    return counts


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


def _ready_share(run_dir: Path) -> dict[str, float | None] | None:
    """READY as a fraction of the fixtures RESOLVE produced, per sport."""
    ready = _ready_counts(run_dir)
    board = _board_counts(run_dir)
    if ready is None or board is None:
        return None
    # A sport with no fixtures has no share — not a share of zero. Counting it
    # as 0.0 would drag every median down on days one sport simply did not run.
    return {
        sport: (ready[sport] / board[sport] if board[sport] > 0 else None)
        for sport in SPORTS
    }


def check_coverage_floor(runs_dir: str, current_date: str) -> list[CoverageVerdict]:
    """Compare today's READY *share* per sport to its own rolling median."""
    root = Path(runs_dir)
    current = _ready_counts(root / current_date)
    current_share = _ready_share(root / current_date)
    if current is None or current_share is None:
        return [
            CoverageVerdict(
                sport, 0, 0.0, 0, "NO_BASELINE", "no artifacts for the current date"
            )
            for sport in SPORTS
        ]

    history: dict[str, list[float]] = {sport: [] for sport in SPORTS}
    if root.exists():
        past_dates = sorted(
            d.name
            for d in root.iterdir()
            if d.is_dir() and len(d.name) == 10 and d.name < current_date
        )
        for date in past_dates[-HISTORY_WINDOW:]:
            shares = _ready_share(root / date)
            if shares is None:
                continue
            for sport in SPORTS:
                past_share = shares[sport]
                if past_share is not None:
                    history[sport].append(past_share)

    verdicts: list[CoverageVerdict] = []
    for sport in SPORTS:
        past = history[sport]
        share = current_share[sport]
        if share is None:
            verdicts.append(
                CoverageVerdict(
                    sport,
                    current[sport],
                    0.0,
                    len(past),
                    "NO_BASELINE",
                    "no fixtures for this sport today",
                )
            )
            continue
        if len(past) < MIN_HISTORY:
            verdicts.append(
                CoverageVerdict(
                    sport,
                    current[sport],
                    0.0,
                    len(past),
                    "NO_BASELINE",
                    f"only {len(past)} comparable past run(s), need {MIN_HISTORY}",
                    share,
                    None,
                )
            )
            continue

        median = statistics.median(past)
        if median <= 0:
            verdicts.append(
                CoverageVerdict(
                    sport,
                    current[sport],
                    0.0,
                    len(past),
                    "NO_BASELINE",
                    "rolling median share is zero; nothing to drop from",
                    share,
                    median,
                )
            )
            continue

        floor = median * (1.0 - MAX_DROP)
        if share < floor:
            verdicts.append(
                CoverageVerdict(
                    sport,
                    current[sport],
                    round(median * current[sport] / share, 1) if share > 0 else 0.0,
                    len(past),
                    "PARTIAL",
                    f"{current[sport]} READY = {share:.1%} of this sport's "
                    f"fixtures, vs median {median:.1%} (floor {floor:.1%}); "
                    f"a drop this size is a matching regression until proven "
                    f"otherwise",
                    share,
                    median,
                )
            )
        else:
            verdicts.append(
                CoverageVerdict(
                    sport,
                    current[sport],
                    round(median * current[sport] / share, 1) if share > 0 else 0.0,
                    len(past),
                    "OK",
                    f"{current[sport]} READY = {share:.1%} of this sport's "
                    f"fixtures, vs median {median:.1%}",
                    share,
                    median,
                )
            )
    return verdicts
