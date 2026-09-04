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


# Whoever discovered a prior day's fixture decides whether it counts towards
# today's floor, so the fixtures in these tests carry ``source_ids`` exactly as
# the real artifact does.
_ROSTER_SOURCE = {"football": "bzzoiro", "tennis": "odds-api"}


def _write_event_list(
    day_dir: Path,
    date: str,
    active_by_sport: dict[str, int],
    *,
    sources: dict[str, str] | None = None,
) -> None:
    """``active_by_sport`` fixtures per sport, each discovered by that sport's
    current roster source unless ``sources`` names another one."""
    day_dir.mkdir(parents=True, exist_ok=True)
    events = []
    n = 0
    for sport, count in active_by_sport.items():
        source = (sources or {}).get(sport, _ROSTER_SOURCE.get(sport, "bzzoiro"))
        for _ in range(count):
            n += 1
            events.append(
                {
                    "event_id": f"{sport}-{n}",
                    "sport": sport,
                    "status": "ACTIVE",
                    "source_ids": {source: f"{source}-{n}"},
                }
            )
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
            json.dumps(
                {
                    "events": [
                        {"sport": "football", "status": "ACTIVE", "source_ids": {"bzzoiro": "x"}}
                    ]
                    * 999
                }
            )
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

    def test_only_fixtures_todays_roster_could_have_found_are_counted(self, tmp_path, run_discover):
        """The roster changed on 2026-09-04 (football bzzoiro-only), and a
        floor built from the old roster's totals measures the change, not the
        day: live run, football 45 ACTIVE vs a raw median of 179."""
        _write_event_list(
            tmp_path / "2026-09-01",
            "2026-09-01",
            {"football": 175},
            sources={"football": "highlightly"},
        )
        _write_event_list(tmp_path / "2026-09-02", "2026-09-02", {"football": 50})
        _write_event_list(tmp_path / "2026-09-03", "2026-09-03", {"football": 52})
        history = run_discover._history_active_counts(tmp_path, "2026-09-04", ["football"])
        assert sorted(history["football"]) == [50, 52]
        assert coverage_floor_reasons({"football": 45}, {"football": [50, 52, 51]}) == []

    def test_a_fixture_both_rosters_found_still_counts(self, tmp_path, run_discover):
        """``source_ids`` is a union across sources (the dedup engine merges
        duplicates), so a day where highlightly *also* returned the fixture
        is still evidence about bzzoiro."""
        day = tmp_path / "2026-09-02"
        day.mkdir()
        (day / "2026-09-02_event_list.json").write_text(
            json.dumps(
                {
                    "events": [
                        {
                            "sport": "football",
                            "status": "ACTIVE",
                            "source_ids": {"highlightly": "h1", "bzzoiro": "b1"},
                        }
                    ]
                }
            )
        )
        history = run_discover._history_active_counts(tmp_path, "2026-09-04", ["football"])
        assert history["football"] == [1]

    def test_a_day_the_roster_never_ran_is_skipped_not_recorded_as_zero(self, tmp_path, run_discover):
        """Zero there is absence of evidence, and zeros in the sample only
        drag the median down and blind the floor. A real zero *today* is
        SPORT_EMPTY's job."""
        _write_event_list(
            tmp_path / "2026-09-01",
            "2026-09-01",
            {"football": 167},
            sources={"football": "highlightly"},
        )
        history = run_discover._history_active_counts(tmp_path, "2026-09-04", ["football"])
        assert history["football"] == []

    def test_a_sport_with_no_configured_roster_keeps_its_raw_count(self, tmp_path, run_discover):
        """No roster for the sport means no regime to correct for, so the
        old raw behaviour is the honest answer rather than a silent zero."""
        _write_event_list(
            tmp_path / "2026-09-01", "2026-09-01", {"snooker": 4}, sources={"snooker": "whoever"}
        )
        history = run_discover._history_active_counts(tmp_path, "2026-09-04", ["snooker"])
        assert history["snooker"] == [4]

    def test_the_roster_is_read_from_discover_not_hardcoded_here(self, run_discover):
        """If DISCOVERY_SOURCES_BY_SPORT changes again, the floor's history
        must follow it without a second edit."""
        from bet.simple_stats.discover import DISCOVERY_SOURCES_BY_SPORT

        assert run_discover.DISCOVERY_SOURCES_BY_SPORT is DISCOVERY_SOURCES_BY_SPORT
