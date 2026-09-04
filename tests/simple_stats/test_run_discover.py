"""Step 7 of the 2026-09-04 consolidation plan: a sport with zero ACTIVE
events must not read as a healthy verdict, and the coverage floor that
replaces ``SLATE_CRITICAL_SOURCES`` must cost zero provider calls.

``coverage_floor_reasons`` lives in ``discover.py`` (pure, no I/O).
``_history_active_counts`` lives in the script itself, since it is the one
piece of filesystem I/O involved -- scanning ``runs/`` for prior artifacts.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from bet.simple_stats.discover import coverage_floor_reasons

RUN_DISCOVER = Path(__file__).resolve().parents[2] / "scripts/simple/run_discover.py"


@pytest.fixture(scope="module")
def run_discover():
    spec = importlib.util.spec_from_file_location("run_discover_under_test", RUN_DISCOVER)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_event_list(day_dir: Path, date: str, active_by_sport: dict[str, int]) -> None:
    day_dir.mkdir(parents=True, exist_ok=True)
    events = []
    n = 0
    for sport, count in active_by_sport.items():
        for _ in range(count):
            n += 1
            events.append({"event_id": f"{sport}-{n}", "sport": sport, "status": "ACTIVE"})
    payload = {"run_id": "x", "generated_at": date, "date": date, "sports": list(active_by_sport), "events": events}
    (day_dir / f"{date}_event_list.json").write_text(json.dumps(payload))


class TestCoverageFloorReasons:
    def test_a_sport_far_below_its_own_median_is_flagged(self):
        reasons = coverage_floor_reasons(
            {"tennis": 2}, {"tennis": [40, 38, 42, 41, 39]}
        )
        assert len(reasons) == 1
        assert "tennis" in reasons[0]

    def test_a_sport_near_its_median_is_not_flagged(self):
        reasons = coverage_floor_reasons(
            {"football": 43}, {"football": [45, 44, 46, 45, 43]}
        )
        assert reasons == []

    def test_too_few_prior_runs_is_not_a_floor(self):
        """A median of one or two days is noise, not a floor -- skip it
        rather than flag every day as below a meaningless baseline."""
        reasons = coverage_floor_reasons({"tennis": 0}, {"tennis": [40, 38]})
        assert reasons == []

    def test_a_sport_with_no_history_at_all_is_not_flagged(self):
        reasons = coverage_floor_reasons({"tennis": 0}, {})
        assert reasons == []

    def test_a_zero_median_never_divides_or_flags(self):
        reasons = coverage_floor_reasons({"tennis": 0}, {"tennis": [0, 0, 0]})
        assert reasons == []

    def test_uses_get_not_indexing_for_a_sport_missing_from_history(self):
        """Roster discovery per sport: a sport present in today's counts but
        absent from history must not KeyError."""
        reasons = coverage_floor_reasons({"snooker": 5}, {})
        assert reasons == []


class TestHistoryActiveCounts:
    def test_reads_active_counts_from_prior_day_directories(self, tmp_path, run_discover):
        _write_event_list(tmp_path / "2026-09-01", "2026-09-01", {"football": 40, "tennis": 10})
        _write_event_list(tmp_path / "2026-09-02", "2026-09-02", {"football": 42, "tennis": 12})
        history = run_discover._history_active_counts(tmp_path, "2026-09-03", ["football", "tennis"])
        assert sorted(history["football"]) == [40, 42]
        assert sorted(history["tennis"]) == [10, 12]

    def test_ignores_dates_on_or_after_the_target_date(self, tmp_path, run_discover):
        _write_event_list(tmp_path / "2026-09-03", "2026-09-03", {"football": 999})
        _write_event_list(tmp_path / "2026-09-04", "2026-09-04", {"football": 999})
        history = run_discover._history_active_counts(tmp_path, "2026-09-03", ["football"])
        assert history["football"] == []

    def test_ignores_non_date_scratch_directories(self, tmp_path, run_discover):
        """Harness/debug runs like ``2026-09-04_step5_merged`` must never
        pollute the rolling median."""
        scratch = tmp_path / "2026-09-03_step5_merged"
        scratch.mkdir()
        (scratch / "2026-09-03_step5_merged_event_list.json").write_text(
            json.dumps({"events": [{"sport": "football", "status": "ACTIVE"}] * 999})
        )
        history = run_discover._history_active_counts(tmp_path, "2026-09-04", ["football"])
        assert history["football"] == []

    def test_a_missing_event_list_file_is_skipped_not_an_error(self, tmp_path, run_discover):
        (tmp_path / "2026-09-01").mkdir()
        history = run_discover._history_active_counts(tmp_path, "2026-09-02", ["football"])
        assert history["football"] == []

    def test_a_nonexistent_runs_root_returns_empty(self, tmp_path, run_discover):
        history = run_discover._history_active_counts(tmp_path / "nope", "2026-09-04", ["football"])
        assert history == {}
