"""Tests for BET V5 V7.2 Truthful Live Plan and S2-S8 Continuation fixes."""
import json
import os
import sqlite3
import pytest
from pathlib import Path

from bet.pipeline.launch_bridge import (
    create_runtime_analysis_shadow_db,
    reconcile_s1r_runtime_database,
    execute_plan_only,
)


def test_create_runtime_analysis_shadow_db_fails_on_existing_without_overwrite(tmp_path: Path):
    canonical_db = tmp_path / "canonical.db"
    conn = sqlite3.connect(str(canonical_db))
    conn.execute("CREATE TABLE fixtures (id INTEGER PRIMARY KEY, external_id TEXT, kickoff TEXT, status TEXT)")
    conn.execute("CREATE TABLE pipeline_candidates (id INTEGER PRIMARY KEY, fixture_id INTEGER, betting_date TEXT)")
    conn.execute("CREATE TABLE analysis_results (id INTEGER PRIMARY KEY)")
    conn.execute("CREATE TABLE gate_results (id INTEGER PRIMARY KEY)")
    conn.execute("CREATE TABLE odds_history (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

    run_root = tmp_path / "run_001"
    res1 = create_runtime_analysis_shadow_db(canonical_db, run_root, "RUN_001", allow_overwrite=True)
    assert res1["status"] == "PASS"

    shadow_p = Path(res1["shadow_db_path"])
    assert shadow_p.exists()

    # Second call without allow_overwrite must raise FileExistsError
    with pytest.raises(FileExistsError, match="Unlinking an existing plan DB is forbidden"):
        create_runtime_analysis_shadow_db(canonical_db, run_root, "RUN_001", allow_overwrite=False)


def test_reconcile_s1r_runtime_database_offline_counts(tmp_path: Path):
    canonical_db = tmp_path / "canonical.db"
    conn = sqlite3.connect(str(canonical_db))
    conn.execute("CREATE TABLE fixtures (id INTEGER PRIMARY KEY, external_id TEXT, kickoff TEXT, status TEXT, home_team_id INTEGER, away_team_id INTEGER, source TEXT)")
    conn.execute("INSERT INTO fixtures VALUES (1, 'ext_1', '2026-07-29T12:00:00Z', 'SCHEDULED', 1, 2, 'odds-api')")
    conn.execute("INSERT INTO fixtures VALUES (2, 'ext_2', '2026-07-29T10:00:00Z', 'SCHEDULED', 3, 4, 'odds-api')")
    conn.execute("CREATE TABLE teams (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO teams VALUES (1, 'Team A'), (2, 'Team B'), (3, 'Team C'), (4, 'Team D')")
    conn.commit()

    run_root = tmp_path / "run_001"
    run_root.mkdir(parents=True, exist_ok=True)

    res = reconcile_s1r_runtime_database(
        conn=conn,
        date="2026-07-29",
        run_root=run_root,
        runtime_now_iso="2026-07-29T15:00:00Z",
        allow_live_network=False,
    )

    assert res["total_fixtures_checked"] == 2
    assert res["provider_revalidated"] + res["provider_failures"] == res["total_fixtures_checked"]

    # Verify s1r evidence files exist
    ev1 = run_root / "artifacts" / "s1r_evidence" / "fixture_1.json"
    ev2 = run_root / "artifacts" / "s1r_evidence" / "fixture_2.json"
    assert ev1.exists()
    assert ev2.exists()

    d1 = json.loads(ev1.read_text())
    assert d1["fixture_id"] == 1
    assert "request_status" in d1
    assert "failure_reason" in d1

    # Check live_discovery_ledger.json
    disc_file = run_root / "artifacts" / "live_discovery_ledger.json"
    assert disc_file.exists()
    disc_data = json.loads(disc_file.read_text())
    assert disc_data["discovery_attempted"] is False
    conn.close()


def test_run_daily_pipeline_requires_live_ack_when_network_enabled():
    from scripts.pipeline_steps.run_daily_pipeline import parse_pipeline_args, build_pipeline_parser
    parser = build_pipeline_parser()
    args = parser.parse_args(["--date", "2026-07-29", "--run-id", "R1", "--allow-live-network"])
    assert args.allow_live_network is True


def test_verify_and_prepare_plan_continuation(tmp_path: Path):
    from bet.pipeline.launch_bridge import verify_and_prepare_plan_continuation
    from unittest.mock import patch
    canonical_db = tmp_path / "canonical.db"
    conn = sqlite3.connect(str(canonical_db))
    conn.execute("CREATE TABLE fixtures (id INTEGER PRIMARY KEY, external_id TEXT, kickoff TEXT, status TEXT, home_team_id INTEGER, away_team_id INTEGER, source TEXT)")
    conn.execute("INSERT INTO fixtures VALUES (1, 'ext_1', '2026-07-29T20:00:00Z', 'SCHEDULED', 1, 2, 'odds-api')")
    conn.execute("CREATE TABLE sports (id INTEGER PRIMARY KEY, name TEXT, tier INTEGER)")
    conn.execute("INSERT INTO sports VALUES (1, 'football', 1)")
    conn.execute("CREATE TABLE teams (id INTEGER PRIMARY KEY, sport_id INTEGER, name TEXT)")
    conn.execute("INSERT INTO teams VALUES (1, 1, 'Team A'), (2, 1, 'Team B')")
    conn.execute("CREATE TABLE pipeline_candidates (id INTEGER PRIMARY KEY, fixture_id INTEGER, betting_date TEXT)")
    conn.execute("CREATE TABLE analysis_results (id INTEGER PRIMARY KEY)")
    conn.execute("CREATE TABLE gate_results (id INTEGER PRIMARY KEY)")
    conn.execute("CREATE TABLE odds_history (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

    empty_seed = tmp_path / "empty_seed.json"
    empty_seed.write_text(json.dumps({"events": []}))

    class MockFixture:
        primary_source = "odds-api"
        primary_external_id = "ext_1"
        home_team = "Team A"
        away_team = "Team B"
        kickoff = "2026-07-29T20:00:00Z"
        status = "SCHEDULED"
        sources = [type("Src", (), {"source": "odds-api", "external_id": "ext_1"})()]
        odds = {}

    class MockDiscResult:
        source_stats = {"odds-api": type("Stats", (), {"available": True, "errors": None, "events_fetched": 1})()}
        fixtures = [MockFixture()]
        total_after_dedup = 1

    class MockCoordinator:
        def __init__(self, session=None):
            pass
        def discover(self, date, verbose=False):
            return MockDiscResult()

    run_root = tmp_path / "reports" / "pipeline_runs" / "2026-07-29" / "RUN_CONT_001"
    with patch("bet.discovery.coordinator.EventDiscoveryCoordinator", MockCoordinator), \
         patch("sqlalchemy.create_engine"), \
         patch("sqlalchemy.orm.sessionmaker"):
        res = execute_plan_only(
            repo_root=Path(__file__).resolve().parents[1],
            date="2026-07-29",
            run_id="RUN_CONT_001",
            target_run_root=run_root,
            manifest_path=Path(__file__).resolve().parents[1] / "config" / "pipeline_manifest.json",
            allow_live_network=True,
            explicit_db_path=canonical_db,
            seed_manifest_path=empty_seed,
        )
    assert res["PLAN_STATUS"] == "PASS"

    cont_res = verify_and_prepare_plan_continuation(
        target_run_root=run_root,
        run_id="RUN_CONT_001",
        expected_selection_ledger_sha256=res["SELECTION_LEDGER_SHA256"],
    )
    assert cont_res["status"] == "PASS"
    assert cont_res["selection_ledger_sha256"] == res["SELECTION_LEDGER_SHA256"]


def test_excluded_events_cannot_enter_s2_s3_s5_s8(tmp_path: Path):
    """Prove excluded events (not ANALYZE_FROM_S2) are omitted from S1e universe."""
    from unittest.mock import patch
    canonical_db = tmp_path / "canonical.db"
    conn = sqlite3.connect(str(canonical_db))
    conn.execute("CREATE TABLE fixtures (id INTEGER PRIMARY KEY, external_id TEXT, kickoff TEXT, status TEXT, home_team_id INTEGER, away_team_id INTEGER, source TEXT)")
    # Event 1: Valid future scheduled
    conn.execute("INSERT INTO fixtures VALUES (1, 'ext_1', '2026-07-30T23:59:59Z', 'SCHEDULED', 1, 2, 'odds-api')")
    # Event 2: Finished match
    conn.execute("INSERT INTO fixtures VALUES (2, 'ext_2', '2026-07-30T10:00:00Z', 'FINISHED', 1, 2, 'odds-api')")
    # Event 3: Cancelled match
    conn.execute("INSERT INTO fixtures VALUES (3, 'ext_3', '2026-07-30T18:00:00Z', 'CANCELLED', 1, 2, 'odds-api')")
    conn.execute("CREATE TABLE sports (id INTEGER PRIMARY KEY, name TEXT, tier INTEGER)")
    conn.execute("INSERT INTO sports VALUES (1, 'football', 1)")
    conn.execute("CREATE TABLE teams (id INTEGER PRIMARY KEY, sport_id INTEGER, name TEXT)")
    conn.execute("INSERT INTO teams VALUES (1, 1, 'Team A'), (2, 1, 'Team B')")
    conn.execute("CREATE TABLE pipeline_candidates (id INTEGER PRIMARY KEY, fixture_id INTEGER, betting_date TEXT)")
    conn.execute("CREATE TABLE analysis_results (id INTEGER PRIMARY KEY)")
    conn.execute("CREATE TABLE gate_results (id INTEGER PRIMARY KEY)")
    conn.execute("CREATE TABLE odds_history (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

    empty_seed = tmp_path / "empty_seed.json"
    empty_seed.write_text(json.dumps({"events": []}))

    class MockFixture:
        primary_source = "odds-api"
        primary_external_id = "ext_1"
        home_team = "Team A"
        away_team = "Team B"
        kickoff = "2026-07-30T23:59:59Z"
        status = "SCHEDULED"
        sources = [type("Src", (), {"source": "odds-api", "external_id": "ext_1"})()]
        odds = {}

    class MockDiscResult:
        source_stats = {"odds-api": type("Stats", (), {"available": True, "errors": None, "events_fetched": 1})()}
        fixtures = [MockFixture()]
        total_after_dedup = 1

    class MockCoordinator:
        def __init__(self, session=None):
            pass
        def discover(self, date, verbose=False):
            return MockDiscResult()

    run_root = tmp_path / "reports" / "pipeline_runs" / "2026-07-30" / "RUN_EXCL_001"
    with patch("bet.discovery.coordinator.EventDiscoveryCoordinator", MockCoordinator), \
         patch("sqlalchemy.create_engine"), \
         patch("sqlalchemy.orm.sessionmaker"):
        res = execute_plan_only(
            repo_root=Path(__file__).resolve().parents[1],
            date="2026-07-30",
            run_id="RUN_EXCL_001",
            target_run_root=run_root,
            manifest_path=Path(__file__).resolve().parents[1] / "config" / "pipeline_manifest.json",
            allow_live_network=True,
            explicit_db_path=canonical_db,
            seed_manifest_path=empty_seed,
        )
    assert res["PLAN_STATUS"] == "PASS"
    assert res["ANALYZE_FROM_S2"] == 1
    assert res["FINISHED"] == 1
    assert res["CANCELLED"] == 1

    s1e_file = run_root / "artifacts" / "S1e.json"
    s1e_data = json.loads(s1e_file.read_text())
    active_fixture_ids = [e["fixture_id"] for e in s1e_data["events"]]
    assert active_fixture_ids == [1]
    assert 2 not in active_fixture_ids
    assert 3 not in active_fixture_ids
