"""T40 — the per-sport coverage floor (L32).

The floor measures a **share**, not a count, since 2026-09-21. Its own message
claims "a matching regression until proven otherwise", and a matching
regression is a fall in the fraction of fixtures we can sample — not a fall in
how many fixtures the calendar produced. See `test_a_quiet_monday_is_not_a_
regression` for the run that forced the change.
"""

from __future__ import annotations

import json
from pathlib import Path

from bet.sofa.coverage import CoverageVerdict, check_coverage_floor


def create_run_data(
    base_dir: Path,
    date: str,
    football_ready: int,
    tennis_ready: int,
    football_total: int | None = None,
    tennis_total: int | None = None,
) -> None:
    """One run directory. `*_total` defaults to `*_ready` (a perfect day)."""
    football_total = football_ready if football_total is None else football_total
    tennis_total = tennis_ready if tennis_total is None else tennis_total
    assert football_ready <= football_total and tennis_ready <= tennis_total

    run_dir = base_dir / date
    run_dir.mkdir(parents=True, exist_ok=True)

    fixtures = []
    samples = []
    for i in range(football_total):
        fid = 1000 + i
        fixtures.append({"sofascore_event_id": fid, "sport": "football"})
        samples.append(
            {
                "sofascore_event_id": fid,
                "readiness": "READY" if i < football_ready else "BLOCKED",
            }
        )
    for i in range(tennis_total):
        fid = 2000 + i
        fixtures.append({"sofascore_event_id": fid, "sport": "tennis"})
        samples.append(
            {
                "sofascore_event_id": fid,
                "readiness": "READY" if i < tennis_ready else "BLOCKED",
            }
        )

    (run_dir / "02_fixtures.json").write_text(json.dumps(fixtures), encoding="utf-8")
    (run_dir / "03_samples.json").write_text(json.dumps(samples), encoding="utf-8")


def by_sport(verdicts: list[CoverageVerdict]) -> dict[str, CoverageVerdict]:
    return {v.sport: v for v in verdicts}


def test_a_quiet_monday_is_not_a_regression(tmp_path: Path) -> None:
    """The run that forced this: 2026-09-21.

    Superbet's board went from 1040 football fixtures on the Sunday to 102 on
    the Monday. The counting floor read "66 READY vs median 406" and declared
    a matching regression, while the day's RESOLVE rate of 79.4% sat squarely
    inside the 72-90% of the very days it was being compared against. Nothing
    was broken except the comparison.
    """
    runs_dir = tmp_path / "runs"
    for date in ("2026-09-18", "2026-09-19", "2026-09-20"):
        create_run_data(runs_dir, date, 406, 40, football_total=500, tennis_total=50)
    # Monday: a tenth of the slate, the same sampling quality.
    create_run_data(runs_dir, "2026-09-21", 66, 40, football_total=81, tennis_total=50)

    verdicts = by_sport(check_coverage_floor(str(runs_dir), "2026-09-21"))
    assert verdicts["football"].status == "OK", verdicts["football"].detail
    assert verdicts["football"].current == 66


def test_a_real_matching_regression_is_still_caught(tmp_path: Path) -> None:
    """Same slate size, far fewer of them sampled. This is what the floor is for."""
    runs_dir = tmp_path / "runs"
    for date in ("2026-09-10", "2026-09-11", "2026-09-12"):
        create_run_data(runs_dir, date, 90, 50, football_total=100, tennis_total=55)
    create_run_data(runs_dir, "2026-09-13", 30, 50, football_total=100, tennis_total=55)

    verdicts = by_sport(check_coverage_floor(str(runs_dir), "2026-09-13"))
    assert verdicts["football"].status == "PARTIAL"
    assert verdicts["tennis"].status == "OK"
    assert "matching regression" in verdicts["football"].detail


def test_a_moderate_drop_is_not_flagged(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    for date in ("2026-09-10", "2026-09-11", "2026-09-12"):
        create_run_data(runs_dir, date, 100, 50, football_total=100, tennis_total=50)
    # 20% of the board lost, well inside MAX_DROP.
    create_run_data(runs_dir, "2026-09-13", 80, 50, football_total=100, tennis_total=50)

    verdicts = by_sport(check_coverage_floor(str(runs_dir), "2026-09-13"))
    assert all(v.status == "OK" for v in verdicts.values())


def test_a_shared_median_would_have_missed_this(tmp_path: Path) -> None:
    """L32: tennis collapses while football grows."""
    runs_dir = tmp_path / "runs"
    for date in ("2026-09-10", "2026-09-11", "2026-09-12", "2026-09-13"):
        create_run_data(runs_dir, date, 55, 50, football_total=60, tennis_total=55)
    create_run_data(runs_dir, "2026-09-14", 115, 5, football_total=120, tennis_total=55)

    verdicts = by_sport(check_coverage_floor(str(runs_dir), "2026-09-14"))
    pooled_today = verdicts["football"].current + verdicts["tennis"].current
    assert pooled_today > 105, "the pooled view really would have looked healthy"
    assert verdicts["tennis"].status == "PARTIAL"
    assert verdicts["football"].status == "OK"


def test_too_little_history_is_no_baseline_not_ok(tmp_path: Path) -> None:
    """Two past runs do not make a median; saying OK would be a claim."""
    runs_dir = tmp_path / "runs"
    create_run_data(runs_dir, "2026-09-10", 100, 50)
    create_run_data(runs_dir, "2026-09-11", 100, 50)
    create_run_data(runs_dir, "2026-09-12", 1, 1)

    verdicts = by_sport(check_coverage_floor(str(runs_dir), "2026-09-12"))
    assert all(v.status == "NO_BASELINE" for v in verdicts.values())


def test_missing_current_artifacts_is_no_baseline(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    create_run_data(runs_dir, "2026-09-10", 100, 50)
    verdicts = check_coverage_floor(str(runs_dir), "2026-09-11")
    assert all(v.status == "NO_BASELINE" for v in verdicts)


def test_incomplete_past_runs_are_skipped_not_counted_as_zero(tmp_path: Path) -> None:
    """A half-written past run is not evidence that coverage was zero that day."""
    runs_dir = tmp_path / "runs"
    for date in ("2026-09-10", "2026-09-11", "2026-09-12"):
        create_run_data(runs_dir, date, 100, 50)
    (runs_dir / "2026-09-13").mkdir(parents=True)  # no artifacts at all
    create_run_data(runs_dir, "2026-09-14", 100, 50)

    verdicts = by_sport(check_coverage_floor(str(runs_dir), "2026-09-14"))
    assert verdicts["football"].history_runs == 3
    assert verdicts["football"].status == "OK"


def test_a_sport_absent_today_is_no_baseline_not_a_zero_share(tmp_path: Path) -> None:
    """No fixtures is not the same as none of them worked."""
    runs_dir = tmp_path / "runs"
    for date in ("2026-09-10", "2026-09-11", "2026-09-12"):
        create_run_data(runs_dir, date, 100, 50)
    create_run_data(runs_dir, "2026-09-13", 100, 0, tennis_total=0)

    verdicts = by_sport(check_coverage_floor(str(runs_dir), "2026-09-13"))
    assert verdicts["tennis"].status == "NO_BASELINE"
    assert verdicts["football"].status == "OK"
