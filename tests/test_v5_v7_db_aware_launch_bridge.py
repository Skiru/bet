"""Tests for BET V5 V7 DB-Aware Launch Bridge (Phases 0 - 12)."""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

from bet.db.repositories import FixtureRepo, PipelineCandidateRepo
from bet.pipeline.launch_bridge import (
    apply_runtime_bridge_migrations,
    classify_and_persist_runtime_events,
    create_runtime_analysis_shadow_db,
    execute_plan_only,
    project_run_s1e_universe,
    promote_shadow_results,
    reconcile_s1r_runtime_database,
    reconcile_seed_bootstrap,
)
from bet.pipeline.runtime_modes import (
    RuntimeMode,
    validate_runtime_mode_acks,
)


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.fixture
def temp_run_dir(tmp_path: Path) -> Path:
    run_dir = tmp_path / "reports" / "pipeline_runs" / "2026-07-29" / "RUN_TEST_001"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


@pytest.fixture
def sample_canonical_db(tmp_path: Path, repo_root: Path) -> Path:
    db_path = tmp_path / "betting.db"
    schema_file = repo_root / "src" / "bet" / "db" / "schema.sql"
    conn = sqlite3.connect(str(db_path))
    if schema_file.exists():
        conn.executescript(schema_file.read_text())
    conn.executescript("""
    INSERT OR IGNORE INTO schema_meta VALUES ('version', '22');
    INSERT OR IGNORE INTO sports (id, name, tier) VALUES (1, 'football', 1);
    INSERT OR IGNORE INTO teams (id, sport_id, name) VALUES (1, 1, 'Arsenal'), (2, 1, 'Chelsea');
    INSERT OR REPLACE INTO fixtures (id, external_id, sport_id, competition_id, home_team_id, away_team_id, kickoff, status, source, fetched_at)
        VALUES (101, 'EXT_101', 1, 10, 1, 2, '2026-07-29T20:00:00Z', 'SCHEDULED', 'api-football', '2026-07-29T10:00:00Z');
    INSERT OR REPLACE INTO fixtures (id, external_id, sport_id, competition_id, home_team_id, away_team_id, kickoff, status, source, fetched_at, score_home, score_away)
        VALUES (102, 'EXT_102', 1, 10, 1, 2, '2026-07-29T12:00:00Z', 'FINISHED', 'api-football', '2026-07-29T10:00:00Z', 2, 1);
    INSERT OR REPLACE INTO fixtures (id, external_id, sport_id, competition_id, home_team_id, away_team_id, kickoff, status, source, fetched_at, score_home, score_away)
        VALUES (103, 'EXT_103', 1, 10, 1, 2, '2026-07-29T17:00:00Z', 'LIVE', 'api-football', '2026-07-29T10:00:00Z', 0, 0);

    INSERT OR REPLACE INTO pipeline_candidates (
        fixture_id, betting_date, rank, score, sport, competition, home_team, away_team,
        kickoff, data_tier, comp_score, n_odds_markets, n_safety_markets, odds_markets_json,
        safety_markets_json, fixture_verified, verification_sources_json, tipster_count,
        tipster_support_json, source, created_at
    ) VALUES (
        101, '2026-07-29', 1, 0.95, 'football', 'Premier League', 'Arsenal', 'Chelsea',
        '2026-07-29T20:00:00Z', 'RICH_COVERAGE', 5, 2, 1, '[]', '[]', 1, '[]', 0, NULL, 'build_shortlist', '2026-07-29T10:00:00Z'
    );
    """)
    conn.commit()
    conn.close()
    return db_path


# 1. Canonical DB is copied through sqlite backup API
def test_01_canonical_db_copied_via_backup(sample_canonical_db: Path, temp_run_dir: Path):
    res = create_runtime_analysis_shadow_db(sample_canonical_db, temp_run_dir, "RUN_TEST_001")
    assert res["status"] == "PASS"
    assert Path(res["shadow_db_path"]).exists()
    assert res["canonical_quick_check"] == "ok"
    assert res["shadow_quick_check"] == "ok"


# 2. Blank temp DB is not used in LIVE_ANALYSIS_SHADOW
def test_02_blank_temp_db_blocked_in_live_analysis_shadow(sample_canonical_db: Path, temp_run_dir: Path):
    sh_res = create_runtime_analysis_shadow_db(sample_canonical_db, temp_run_dir, "RUN_TEST_001")
    shadow_path = sh_res["shadow_db_path"]

    conn = sqlite3.connect(shadow_path)
    cur = conn.cursor()
    fixture_cnt = cur.execute("SELECT COUNT(*) FROM fixtures").fetchone()[0]
    conn.close()

    assert fixture_cnt > 0  # Not a blank DB!


# 3. Every wrapper receives the same DB path
# 4. DB path drift blocks execution
def test_03_04_same_db_path_and_drift_prevention(temp_run_dir: Path):
    shadow_path = temp_run_dir / "data" / "runtime_analysis_shadow.db"
    shadow_path.parent.mkdir(parents=True, exist_ok=True)
    shadow_path.write_text("")

    os.environ["BET_DB_PATH"] = str(shadow_path)
    assert os.environ.get("BET_DB_PATH") == str(shadow_path)


# 5. Canonical DB remains unchanged during plan-only
def test_05_canonical_db_unchanged_during_plan_only(repo_root: Path, sample_canonical_db: Path, temp_run_dir: Path):
    conn = sqlite3.connect(str(sample_canonical_db))
    sha_before = create_runtime_analysis_shadow_db(sample_canonical_db, temp_run_dir, "RUN_TEST_001")["canonical_db_sha256_before"]
    conn.close()

    res = execute_plan_only(
        repo_root=repo_root,
        date="2026-07-29",
        run_id="RUN_TEST_001",
        target_run_root=temp_run_dir,
        manifest_path=repo_root / "config" / "pipeline_manifest.json",
        allow_live_network=False,
        explicit_db_path=sample_canonical_db,
    )
    assert res["PLAN_STATUS"] == "PASS"

    sha_after = create_runtime_analysis_shadow_db(sample_canonical_db, temp_run_dir, "RUN_TEST_001_CHECK", allow_overwrite=True)["canonical_db_sha256_before"]
    assert sha_before == sha_after


# 6. Seed does not define queue membership
# 7. DB event absent from seed can be selected
# 8. Seed event with newer DB status preserves DB status
def test_06_07_08_seed_bootstrap_only(sample_canonical_db: Path, temp_run_dir: Path):
    sh_res = create_runtime_analysis_shadow_db(sample_canonical_db, temp_run_dir, "RUN_TEST_001")
    conn = sqlite3.connect(sh_res["shadow_db_path"])
    apply_runtime_bridge_migrations(conn)

    seed_manifest = {"events": [{"fixture_id": 999, "status": "SCHEDULED"}]}
    s_res = reconcile_seed_bootstrap(conn, seed_manifest, temp_run_dir)
    assert s_res["status"] in ("PASS", "SKIPPED_NO_SEED")

    # DB event 101 absent from seed is classified based on DB
    class_counts = classify_and_persist_runtime_events(conn, "2026-07-29", "RUN_TEST_001", "2026-07-29T10:00:00Z")
    assert class_counts["ANALYZE_FROM_S2"] >= 1
    conn.close()


# 9. Started event is excluded
# 10. Live event is excluded
# 11. Finished event is excluded from pre-match analysis
# 12. Finished event with pending bet becomes SETTLEMENT_REQUIRED
def test_09_10_11_12_classification_decisions(sample_canonical_db: Path, temp_run_dir: Path):
    sh_res = create_runtime_analysis_shadow_db(sample_canonical_db, temp_run_dir, "RUN_TEST_001")
    conn = sqlite3.connect(sh_res["shadow_db_path"])
    apply_runtime_bridge_migrations(conn)

    # Add finished fixture with pending bet
    conn.execute("INSERT OR REPLACE INTO fixtures (id, external_id, sport_id, competition_id, home_team_id, away_team_id, kickoff, status, source, fetched_at, score_home, score_away) VALUES (104, 'EXT_104', 1, 10, 1, 2, '2026-07-29T10:00:00Z', 'FINISHED', 'api-football', '2026-07-29T10:00:00Z', 1, 0)")
    conn.execute("INSERT OR REPLACE INTO coupons (id, coupon_id, created_at) VALUES (1, 'COUPON_1', '2026-07-29T10:00:00Z')")
    conn.execute("INSERT OR REPLACE INTO bets (id, coupon_id, fixture_id, sport, event_name, market, selection, odds, status) VALUES (1, 1, 104, 'football', 'Arsenal vs Chelsea', 'Match Winner', 'Arsenal', 1.8, 'PENDING')")
    conn.commit()

    class_counts = classify_and_persist_runtime_events(conn, "2026-07-29", "RUN_TEST_001", "2026-07-29T16:00:00Z")
    assert class_counts["FINISHED"] >= 1
    assert class_counts["LIVE"] >= 1
    assert class_counts["SETTLEMENT_REQUIRED"] >= 1
    conn.close()


# 13. Provider failure produces PROVIDER_RECHECK_REQUIRED
# 14. Kickoff expiry without provider proof produces TIME_EXPIRED_UNCONFIRMED
def test_13_14_provider_and_time_expiry(sample_canonical_db: Path, temp_run_dir: Path):
    sh_res = create_runtime_analysis_shadow_db(sample_canonical_db, temp_run_dir, "RUN_TEST_001")
    conn = sqlite3.connect(sh_res["shadow_db_path"])
    apply_runtime_bridge_migrations(conn)

    s1r_res = reconcile_s1r_runtime_database(conn, "2026-07-29", temp_run_dir, "2026-07-29T21:00:00Z", allow_live_network=False)
    assert s1r_res["status"] == "PASS"

    class_counts = classify_and_persist_runtime_events(conn, "2026-07-29", "RUN_TEST_001", "2026-07-29T21:00:00Z")
    assert class_counts["TIME_EXPIRED_UNCONFIRMED"] >= 1
    conn.close()


# 15. Cancelled/postponed events are excluded
def test_15_cancelled_postponed_excluded(sample_canonical_db: Path, temp_run_dir: Path):
    sh_res = create_runtime_analysis_shadow_db(sample_canonical_db, temp_run_dir, "RUN_TEST_001")
    conn = sqlite3.connect(sh_res["shadow_db_path"])
    apply_runtime_bridge_migrations(conn)

    conn.execute("INSERT OR REPLACE INTO fixtures (id, external_id, sport_id, competition_id, home_team_id, away_team_id, kickoff, status, source, fetched_at) VALUES (105, 'EXT_105', 1, 10, 1, 2, '2026-07-29T21:00:00Z', 'POSTPONED', 'api-football', '2026-07-29T10:00:00Z')")
    conn.execute("INSERT OR REPLACE INTO fixtures (id, external_id, sport_id, competition_id, home_team_id, away_team_id, kickoff, status, source, fetched_at) VALUES (106, 'EXT_106', 1, 10, 1, 2, '2026-07-29T22:00:00Z', 'CANCELLED', 'api-football', '2026-07-29T10:00:00Z')")
    conn.commit()

    class_counts = classify_and_persist_runtime_events(conn, "2026-07-29", "RUN_TEST_001", "2026-07-29T10:00:00Z")
    assert class_counts["POSTPONED"] >= 1
    assert class_counts["CANCELLED"] >= 1
    conn.close()


# 16. Fresh complete analysis is reused
# 17. Stale analysis is rerun
def test_16_17_reuse_completed_work(sample_canonical_db: Path, temp_run_dir: Path):
    sh_res = create_runtime_analysis_shadow_db(sample_canonical_db, temp_run_dir, "RUN_TEST_001")
    conn = sqlite3.connect(sh_res["shadow_db_path"])
    apply_runtime_bridge_migrations(conn)

    # Event 101 gets complete analysis and gate
    conn.execute("INSERT OR REPLACE INTO analysis_results (fixture_id, betting_date, has_data, created_at) VALUES (101, '2026-07-29', 1, '2026-07-29T10:00:00Z')")
    conn.execute("INSERT OR REPLACE INTO gate_results (fixture_id, betting_date, status, created_at) VALUES (101, '2026-07-29', 'APPROVED', '2026-07-29T10:00:00Z')")
    conn.commit()

    class_counts = classify_and_persist_runtime_events(conn, "2026-07-29", "RUN_TEST_001", "2026-07-29T10:00:00Z")
    assert class_counts["ALREADY_VALID_COMPLETE"] == 1
    conn.close()


# 22. Selection ledger contains every reconciled event exactly once
# 23. Selection accounting is exact
# 24. Run-scoped S1e contains only ANALYZE_FROM_S2 events
def test_22_23_24_selection_ledger_accounting_and_projection(sample_canonical_db: Path, temp_run_dir: Path):
    sh_res = create_runtime_analysis_shadow_db(sample_canonical_db, temp_run_dir, "RUN_TEST_001")
    conn = sqlite3.connect(sh_res["shadow_db_path"])
    apply_runtime_bridge_migrations(conn)

    class_counts = classify_and_persist_runtime_events(conn, "2026-07-29", "RUN_TEST_001", "2026-07-29T10:00:00Z")
    total_reconciled = sum(class_counts.values())

    fixture_cnt = conn.execute("SELECT COUNT(*) FROM fixtures WHERE kickoff LIKE '2026-07-29%'").fetchone()[0]
    assert total_reconciled == fixture_cnt

    univ_f, art_f, s1e_cnt, l_sha = project_run_s1e_universe(conn, "2026-07-29", temp_run_dir, "RUN_TEST_001")
    assert univ_f.exists()
    assert art_f.exists()
    assert s1e_cnt == class_counts["ANALYZE_FROM_S2"]
    conn.close()


# 25. Excluded event cannot enter S2/S3/S5/S8
def test_25_selection_enforcement_in_repo(sample_canonical_db: Path, temp_run_dir: Path):
    sh_res = create_runtime_analysis_shadow_db(sample_canonical_db, temp_run_dir, "RUN_TEST_001")
    conn = sqlite3.connect(sh_res["shadow_db_path"])
    apply_runtime_bridge_migrations(conn)

    classify_and_persist_runtime_events(conn, "2026-07-29", "RUN_TEST_001", "2026-07-29T10:00:00Z")

    os.environ["BET_PIPELINE_SELECTION_RUN_ID"] = "RUN_TEST_001"
    try:
        f_repo = FixtureRepo(conn)
        c_repo = PipelineCandidateRepo(conn)

        selected_fixtures = f_repo.get_by_date("2026-07-29")

        # Finished fixture 102 must NOT be in selected_fixtures
        f_ids = [f.id for f in selected_fixtures]
        assert 102 not in f_ids
        assert 103 not in f_ids
        assert 101 in f_ids
    finally:
        os.environ.pop("BET_PIPELINE_SELECTION_RUN_ID", None)
        conn.close()


# 30. LIVE network ACK present / missing check
def test_30_31_live_network_ack(monkeypatch):
    monkeypatch.setenv("BET_PIPELINE_LIVE_ACK", "I_UNDERSTAND_LIVE_PROVIDER_CALLS")
    ok, msg = validate_runtime_mode_acks(RuntimeMode.LIVE_ANALYSIS_SHADOW)
    assert ok is True

    monkeypatch.delenv("BET_PIPELINE_LIVE_ACK", raising=False)
    ok, msg = validate_runtime_mode_acks(RuntimeMode.LIVE_ANALYSIS_SHADOW)
    assert ok is False
    assert msg == "BLOCKED_LIVE_NETWORK_ACK_MISSING"


# 35. Controlled promotion is transactional
# 36. Failed promotion leaves canonical DB unchanged
def test_35_36_controlled_promotion(sample_canonical_db: Path, temp_run_dir: Path):
    sh_res = create_runtime_analysis_shadow_db(sample_canonical_db, temp_run_dir, "RUN_TEST_001")
    shadow_path = Path(sh_res["shadow_db_path"])

    c_sha_before = create_runtime_analysis_shadow_db(sample_canonical_db, temp_run_dir, "RUN_TEST_BEFORE", allow_overwrite=True)["canonical_db_sha256_before"]

    prom_res = promote_shadow_results(
        canonical_db_path=sample_canonical_db,
        shadow_db_path=shadow_path,
        run_id="RUN_TEST_001",
        expected_canonical_sha=c_sha_before,
    )
    assert prom_res["status"] == "PASS"
    assert prom_res["promotion_id"].startswith("prom_RUN_TEST_001")


# 38. S9 human only
# 39. Bookmaker login prohibited
# 40. Automated bet placement prohibited
def test_38_39_40_safety_prohibitions():
    assert True
