"""T40 — the per-sport coverage floor (L32)."""

from __future__ import annotations

import json
from pathlib import Path

from bet.sofa.coverage import CoverageVerdict, check_coverage_floor


def create_run_data(
    base_dir: Path, date: str, football_ready: int, tennis_ready: int
) -> None:
    run_dir = base_dir / date
    run_dir.mkdir(parents=True, exist_ok=True)

    fixtures = []
    samples = []
    for i in range(football_ready):
        fid = 1000 + i
        fixtures.append({"sofascore_event_id": fid, "sport": "football"})
        samples.append({"sofascore_event_id": fid, "readiness": "READY"})
    for i in range(tennis_ready):
        fid = 2000 + i
        fixtures.append({"sofascore_event_id": fid, "sport": "tennis"})
        samples.append({"sofascore_event_id": fid, "readiness": "READY"})

    (run_dir / "02_fixtures.json").write_text(json.dumps(fixtures), encoding="utf-8")
    (run_dir / "03_samples.json").write_text(json.dumps(samples), encoding="utf-8")


def by_sport(verdicts: list[CoverageVerdict]) -> dict[str, CoverageVerdict]:
    return {v.sport: v for v in verdicts}


def test_a_drop_in_one_sport_is_flagged_and_the_other_is_not(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    create_run_data(runs_dir, "2026-09-10", 100, 50)
    create_run_data(runs_dir, "2026-09-11", 110, 48)
    create_run_data(runs_dir, "2026-09-12", 90, 52)
    create_run_data(runs_dir, "2026-09-13", 105, 50)
    create_run_data(runs_dir, "2026-09-14", 95, 49)
    create_run_data(runs_dir, "2026-09-15", 40, 45)

    verdicts = by_sport(check_coverage_floor(str(runs_dir), "2026-09-15"))
    assert verdicts["football"].status == "PARTIAL"
    assert verdicts["tennis"].status == "OK"
    assert "READY vs median" in verdicts["football"].detail


def test_a_moderate_drop_is_not_flagged(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    for date in ("2026-09-10", "2026-09-11", "2026-09-12"):
        create_run_data(runs_dir, date, 100, 50)
    create_run_data(runs_dir, "2026-09-13", 80, 50)  # 20% drop

    verdicts = by_sport(check_coverage_floor(str(runs_dir), "2026-09-13"))
    assert all(v.status == "OK" for v in verdicts.values())


def test_a_shared_median_would_have_missed_this(tmp_path: Path) -> None:
    """L32: tennis collapses while football grows.

    Pooled, today's 120 READY beats the pooled median of 105 and nothing fires.
    Per sport, tennis going 50 -> 5 is caught.
    """
    runs_dir = tmp_path / "runs"
    for date in ("2026-09-10", "2026-09-11", "2026-09-12", "2026-09-13"):
        create_run_data(runs_dir, date, 55, 50)
    create_run_data(runs_dir, "2026-09-14", 115, 5)

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
