"""Integration tests for V7.3 Provider Gating and Plan Continuation Fail-Closed Protections."""

import json
import sqlite3
import pytest
from pathlib import Path
from unittest.mock import patch

from bet.pipeline.launch_bridge import (
    execute_plan_only,
    verify_and_prepare_plan_continuation,
)


def _setup_test_db(
    db_path: Path, kickoff_iso: str = "2027-07-30T20:00:00Z", status: str = "SCHEDULED"
) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE fixtures (id INTEGER PRIMARY KEY, external_id TEXT, kickoff TEXT, status TEXT, home_team_id INTEGER, away_team_id INTEGER, source TEXT)"
    )
    conn.execute(
        "INSERT INTO fixtures VALUES (1, 'ext_1', ?, ?, 1, 2, 'odds-api')",
        (kickoff_iso, status),
    )
    conn.execute(
        "CREATE TABLE sports (id INTEGER PRIMARY KEY, name TEXT, tier INTEGER)"
    )
    conn.execute("INSERT INTO sports VALUES (1, 'football', 1)")
    conn.execute(
        "CREATE TABLE teams (id INTEGER PRIMARY KEY, sport_id INTEGER, name TEXT)"
    )
    conn.execute("INSERT INTO teams VALUES (1, 1, 'Team A'), (2, 1, 'Team B')")
    conn.execute(
        "CREATE TABLE pipeline_candidates (id INTEGER PRIMARY KEY, fixture_id INTEGER, betting_date TEXT)"
    )
    conn.execute("CREATE TABLE analysis_results (id INTEGER PRIMARY KEY)")
    conn.execute("CREATE TABLE gate_results (id INTEGER PRIMARY KEY)")
    conn.execute("CREATE TABLE odds_history (id INTEGER PRIMARY KEY)")
    migrations = Path(__file__).resolve().parents[1] / "src/bet/db/migrations"
    conn.executescript(
        (migrations / "023_pipeline_provider_observation_attempts.sql").read_text()
    )
    conn.executescript(
        (migrations / "024_pipeline_event_stage_artifacts.sql").read_text()
    )
    conn.commit()
    conn.close()


def test_failed_provider_observation_results_in_provider_recheck_required(
    tmp_path: Path,
):
    """Prove that failed provider observation yields PROVIDER_RECHECK_REQUIRED, never ANALYZE_FROM_S2."""
    canonical_db = tmp_path / "canonical.db"
    _setup_test_db(canonical_db)

    empty_seed = tmp_path / "empty_seed.json"
    empty_seed.write_text(json.dumps({"events": []}))

    run_root = tmp_path / "reports" / "pipeline_runs" / "2027-07-30" / "RUN_FAIL_001"
    res = execute_plan_only(
        repo_root=Path(__file__).resolve().parents[1],
        date="2027-07-30",
        run_id="RUN_FAIL_001",
        target_run_root=run_root,
        manifest_path=Path(__file__).resolve().parents[1]
        / "config"
        / "pipeline_manifest.json",
        allow_live_network=False,
        explicit_db_path=canonical_db,
        seed_manifest_path=empty_seed,
    )

    assert res["ANALYZE_FROM_S2"] == 0
    assert res["PROVIDER_RECHECK_REQUIRED"] == 1
    assert res["PROVIDER_REVALIDATED"] == 0
    assert res["READY_FOR_BET_EXECUTOR_ANALYSIS_SESSION"] == "NO"
    assert res["DECISION"] == "BLOCKED_FOR_PROVIDER_DATA"
    shadow = sqlite3.connect(run_root / "data" / "runtime_analysis_shadow.db")
    assert (
        shadow.execute(
            "SELECT status FROM pipeline_runtime_plans WHERE run_id = 'RUN_FAIL_001'"
        ).fetchone()[0]
        == "FAILED"
    )
    shadow.close()


def test_successful_provider_observation_results_in_analyze_from_s2(tmp_path: Path):
    """Prove that successful provider observation + future kickoff yields ANALYZE_FROM_S2."""
    canonical_db = tmp_path / "canonical.db"
    _setup_test_db(canonical_db, kickoff_iso="2027-07-30T20:00:00Z")

    empty_seed = tmp_path / "empty_seed.json"
    empty_seed.write_text(json.dumps({"events": []}))

    class MockFixture:
        primary_source = "odds-api"
        primary_external_id = "ext_1"
        home_team = "Team A"
        away_team = "Team B"
        kickoff = "2027-07-30T20:00:00Z"
        status = "SCHEDULED"
        sources = []
        odds = {}

    class MockDiscResult:
        source_stats = {
            "odds-api": type(
                "Stats", (), {"available": True, "errors": None, "events_fetched": 1}
            )()
        }
        fixtures = [MockFixture()]
        total_after_dedup = 1

    class MockCoordinator:
        def __init__(self, session=None):
            pass

        def discover(self, date, verbose=False):
            return MockDiscResult()

    run_root = tmp_path / "reports" / "pipeline_runs" / "2027-07-30" / "RUN_PASS_001"

    with (
        patch("bet.discovery.coordinator.EventDiscoveryCoordinator", MockCoordinator),
        patch("sqlalchemy.create_engine"),
        patch("sqlalchemy.orm.sessionmaker"),
    ):
        res = execute_plan_only(
            repo_root=Path(__file__).resolve().parents[1],
            date="2027-07-30",
            run_id="RUN_PASS_001",
            target_run_root=run_root,
            manifest_path=Path(__file__).resolve().parents[1]
            / "config"
            / "pipeline_manifest.json",
            allow_live_network=True,
            explicit_db_path=canonical_db,
            seed_manifest_path=empty_seed,
        )

    assert res["PLAN_STATUS"] == "PASS"
    assert res["ANALYZE_FROM_S2"] == 1
    assert res["PROVIDER_REVALIDATED"] == 1
    assert res["PROVIDER_RECHECK_REQUIRED"] == 0
    assert res["SELECTED_EVENTS_WITHOUT_PROVIDER_SUCCESS"] == 0
    assert res["READY_FOR_BET_EXECUTOR_ANALYSIS_SESSION"] == "YES"
    assert res["DECISION"] == "READY_FOR_FINAL_INDEPENDENT_LAUNCH_REVIEW"


def test_changed_queue_pre_s2_returns_plan_refresh_required(tmp_path: Path):
    """Prove that queue modification pre-S2 returns PLAN_REFRESH_REQUIRED fail closed."""
    canonical_db = tmp_path / "canonical.db"
    _setup_test_db(canonical_db, kickoff_iso="2027-07-30T20:00:00Z")

    empty_seed = tmp_path / "empty_seed.json"
    empty_seed.write_text(json.dumps({"events": []}))

    class MockFixture:
        primary_source = "odds-api"
        primary_external_id = "ext_1"
        home_team = "Team A"
        away_team = "Team B"
        kickoff = "2027-07-30T20:00:00Z"
        status = "SCHEDULED"
        sources = []
        odds = {}

    class MockDiscResult:
        source_stats = {
            "odds-api": type(
                "Stats", (), {"available": True, "errors": None, "events_fetched": 1}
            )()
        }
        fixtures = [MockFixture()]
        total_after_dedup = 1

    class MockCoordinator:
        def __init__(self, session=None):
            pass

        def discover(self, date, verbose=False):
            return MockDiscResult()

    run_root = tmp_path / "reports" / "pipeline_runs" / "2027-07-30" / "RUN_CONT_001"

    with (
        patch("bet.discovery.coordinator.EventDiscoveryCoordinator", MockCoordinator),
        patch("sqlalchemy.create_engine"),
        patch("sqlalchemy.orm.sessionmaker"),
    ):
        plan_res = execute_plan_only(
            repo_root=Path(__file__).resolve().parents[1],
            date="2027-07-30",
            run_id="RUN_CONT_001",
            target_run_root=run_root,
            manifest_path=Path(__file__).resolve().parents[1]
            / "config"
            / "pipeline_manifest.json",
            allow_live_network=True,
            explicit_db_path=canonical_db,
            seed_manifest_path=empty_seed,
        )

    assert plan_res["ANALYZE_FROM_S2"] == 1

    # Simulate queue change: fixture kickoff passed or status changed to FINISHED in shadow DB
    shadow_db = run_root / "data" / "runtime_analysis_shadow.db"
    conn = sqlite3.connect(str(shadow_db))
    conn.execute("UPDATE fixtures SET status = 'FINISHED' WHERE id = 1")
    conn.commit()
    conn.close()

    cont_res = verify_and_prepare_plan_continuation(
        target_run_root=run_root,
        run_id="RUN_CONT_001",
        expected_selection_ledger_sha256=plan_res["SELECTION_LEDGER_SHA256"],
    )

    assert cont_res["status"] == "BLOCKED"
    assert cont_res["blocker"] == "PLAN_REFRESH_REQUIRED"
    assert cont_res["reason"]
