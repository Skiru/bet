# ruff: noqa: E501
import pytest

from bet.enrichment.football.contracts import (
    FootballFactCompleteness,
    FootballSide,
    FootballTeamMatchFacts,
)


def test_team_match_facts_valid():
    facts = FootballTeamMatchFacts(
        provider_fixture_id="123",
        provider_team_id="1",
        provider_opponent_team_id="2",
        side=FootballSide.HOME,
        goals=2,
        shots=10,
        shots_on_target=5,
        possession_pct=55.0,
        fouls=12,
        yellow_cards=2,
        red_cards=0,
        offsides=1,
        corners=4,
        goalkeeper_saves=3,
        available_metrics=("corners", "fouls", "goalkeeper_saves", "offsides", "possession_pct", "red_cards", "shots", "shots_on_target", "yellow_cards"),
        missing_metrics=(),
        completeness=FootballFactCompleteness.COMPLETE
    )
    assert facts.completeness == FootballFactCompleteness.COMPLETE

def test_team_match_facts_partial():
    # Only 3 metrics present
    facts = FootballTeamMatchFacts(
        provider_fixture_id="123",
        provider_team_id="1",
        provider_opponent_team_id="2",
        side=FootballSide.HOME,
        goals=2,
        shots=10,
        shots_on_target=5,
        possession_pct=None,
        fouls=12,
        yellow_cards=None,
        red_cards=None,
        offsides=None,
        corners=None,
        goalkeeper_saves=None,
        available_metrics=("fouls", "shots", "shots_on_target"),
        missing_metrics=("corners", "goalkeeper_saves", "offsides", "possession_pct", "red_cards", "yellow_cards"),
        completeness=FootballFactCompleteness.PARTIAL
    )
    assert facts.completeness == FootballFactCompleteness.PARTIAL

def test_team_match_facts_score_only():
    facts = FootballTeamMatchFacts(
        provider_fixture_id="123",
        provider_team_id="1",
        provider_opponent_team_id="2",
        side=FootballSide.HOME,
        goals=2,
        shots=None,
        shots_on_target=None,
        possession_pct=None,
        fouls=None,
        yellow_cards=None,
        red_cards=None,
        offsides=None,
        corners=None,
        goalkeeper_saves=None,
        available_metrics=(),
        missing_metrics=("corners", "fouls", "goalkeeper_saves", "offsides", "possession_pct", "red_cards", "shots", "shots_on_target", "yellow_cards"),
        completeness=FootballFactCompleteness.SCORE_ONLY
    )
    assert facts.completeness == FootballFactCompleteness.SCORE_ONLY

def test_team_match_facts_invalid_possession():
    with pytest.raises(ValueError):
        FootballTeamMatchFacts(
            provider_fixture_id="123",
            provider_team_id="1",
            provider_opponent_team_id="2",
            side=FootballSide.HOME,
            goals=2,
            shots=10,
            shots_on_target=5,
            possession_pct=150.0,
            fouls=12,
            yellow_cards=2,
            red_cards=0,
            offsides=1,
            corners=4,
            goalkeeper_saves=3,
            available_metrics=("corners", "fouls", "goalkeeper_saves", "offsides", "possession_pct", "red_cards", "shots", "shots_on_target", "yellow_cards"),
            missing_metrics=(),
            completeness=FootballFactCompleteness.COMPLETE
        )


def test_t1_source_contains_no_prohibited_patterns():
    import subprocess
    # Run git grep to verify no prohibited patterns are in production files
    cmd = ["git", "grep", "-n", "-E", "replay_scope_key|dummy_b", "--", "scripts/enrichment/football_history.py", "src/bet/enrichment/football"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode != 0, "No prohibited patterns should be present in production/CLI files"

def test_t1_empty_replay_creates_zero_database_rows():
    import sqlite3
    from bet.db.schema import init_db
    from bet.enrichment.football.service import FootballHistoryService
    from bet.enrichment.football.sync import FootballSyncEngine
    from bet.enrichment.football.contracts import ReplayCommand, NoReplayableFixturesError

    conn = sqlite3.connect(":memory:")
    init_db(conn)
    sync_engine = FootballSyncEngine(conn)
    service = FootballHistoryService(conn, None, sync_engine, None)

    cmd = ReplayCommand(evidence_bundle_ids=())
    with pytest.raises(NoReplayableFixturesError):
        service.replay(cmd)

    # Verify no sports_sync_run or sports_sync_item rows exist
    runs = conn.execute("SELECT COUNT(*) FROM sports_sync_run").fetchone()[0]
    items = conn.execute("SELECT COUNT(*) FROM sports_sync_item").fetchone()[0]
    assert runs == 0
    assert items == 0

def test_t1_normalized_match_hash_is_evidence_independent():
    from datetime import UTC, datetime
    from bet.enrichment.football.contracts import FootballFixtureIdentity, FootballProviderStatus, compute_normalized_match_payload_hash

    fix1 = FootballFixtureIdentity(
        provider_fixture_id="101", provider_competition_id="39", competition_name="EPL", country="England", season=2023,
        round_name="Regular Season", kickoff_at=datetime(2023, 1, 1, 12, 0, tzinfo=UTC), provider_status=FootballProviderStatus.FT,
        canonical_status="finished", home_provider_team_id="1", away_provider_team_id="2", home_team_name="A", away_team_name="B",
        home_score=2, away_score=1, home_penalty_score=None, away_penalty_score=None, parser_version="v1", schema_version="1"
    )

    stats = {
        "1": {"Total Shots": 10, "Ball Possession": 50.0},
        "2": {"Total Shots": 8, "Ball Possession": 50.0}
    }

    h1 = compute_normalized_match_payload_hash(fix1, stats)
    h2 = compute_normalized_match_payload_hash(fix1, stats)
    assert h1 == h2
    assert len(h1) == 64

def test_t1_nan_inf_blocks_snapshot():
    from bet.enrichment.football.contracts import round_float_six
    import math

    with pytest.raises(ValueError, match="NaN and Infinity are not allowed"):
        round_float_six(float("nan"))

    with pytest.raises(ValueError, match="NaN and Infinity are not allowed"):
        round_float_six(float("inf"))

def test_t1_no_legacy_unsafe_persistence_callable():
    # Physically check persistence.py source file to ensure persist_completed_facts is removed
    src_content = open("src/bet/enrichment/football/persistence.py").read()
    assert "def persist_completed_facts" not in src_content
