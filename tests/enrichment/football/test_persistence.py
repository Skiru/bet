# ruff: noqa: E501
import sqlite3
import pytest
from datetime import datetime, timezone
import json
import hashlib

from bet.db.schema import init_db
from bet.enrichment.football.contracts import (
    FootballFixtureIdentity,
    FootballTeamMatchFacts,
    FootballCompletedMatchFacts,
    FootballSide,
    FootballProviderStatus,
    FootballFactCompleteness,
)
from bet.enrichment.football.persistence import (
    CanonicalPersistence,
    resolve_domain_entity,
    resolve_domain_and_sports_entity,
)

@pytest.fixture
def db_conn():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    init_db(conn)
    conn.execute("""INSERT INTO sports_sync_cursor (id, provider, sport, operation, scope_key, created_at, updated_at)
                     VALUES (1, 'api-football', 'football', 'completed-fixture-history', 'scope_1', '2023', '2023')""")
    conn.execute("""INSERT INTO sports_sync_run (id, run_identity, cursor_id, provider, sport, operation, scope_key, mode, window_from, window_to, status, started_at, cursor_before_json)
                     VALUES (1, 'run_1', 1, 'api-football', 'football', 'completed-fixture-history', 'scope_1', 'bootstrap', '2023', '2023', 'RUNNING', '2023', '{}')""")
    yield conn
    conn.close()

def make_dummy_completed_facts(fix_id="123", home_score=2, away_score=1, shots_home=10, shots_away=None) -> FootballCompletedMatchFacts:
    fixture = FootballFixtureIdentity(
        provider_fixture_id=fix_id,
        provider_competition_id="39",
        competition_name="Premier League",
        country="England",
        season=2023,
        round_name="Regular Season",
        kickoff_at=datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        provider_status=FootballProviderStatus.FT,
        canonical_status="finished",
        home_provider_team_id="10",
        away_provider_team_id="20",
        home_team_name="Home Team",
        away_team_name="Away Team",
        home_score=home_score,
        away_score=away_score,
        home_penalty_score=None,
        away_penalty_score=None,
        parser_version="api-football-team-facts-v1",
        schema_version="1"
    )
    home = FootballTeamMatchFacts(
        provider_fixture_id=fix_id,
        provider_team_id="10",
        provider_opponent_team_id="20",
        side=FootballSide.HOME,
        goals=home_score,
        shots=shots_home,
        shots_on_target=5 if shots_home else None,
        possession_pct=50.0 if shots_home else None,
        fouls=10 if shots_home else None,
        yellow_cards=1 if shots_home else None,
        red_cards=0 if shots_home else None,
        offsides=2 if shots_home else None,
        corners=4 if shots_home else None,
        goalkeeper_saves=3 if shots_home else None,
        available_metrics=("corners", "fouls", "goalkeeper_saves", "offsides", "possession_pct", "red_cards", "shots", "shots_on_target", "yellow_cards") if shots_home else (),
        missing_metrics=() if shots_home else ("corners", "fouls", "goalkeeper_saves", "offsides", "possession_pct", "red_cards", "shots", "shots_on_target", "yellow_cards"),
        completeness=FootballFactCompleteness.COMPLETE if shots_home else FootballFactCompleteness.SCORE_ONLY
    )
    away = FootballTeamMatchFacts(
        provider_fixture_id=fix_id,
        provider_team_id="20",
        provider_opponent_team_id="10",
        side=FootballSide.AWAY,
        goals=away_score,
        shots=shots_away,
        shots_on_target=4 if shots_away else None,
        possession_pct=50.0 if shots_away else None,
        fouls=8 if shots_away else None,
        yellow_cards=0 if shots_away else None,
        red_cards=0 if shots_away else None,
        offsides=1 if shots_away else None,
        corners=3 if shots_away else None,
        goalkeeper_saves=4 if shots_away else None,
        available_metrics=("corners", "fouls", "goalkeeper_saves", "offsides", "possession_pct", "red_cards", "shots", "shots_on_target", "yellow_cards") if shots_away else (),
        missing_metrics=() if shots_away else ("corners", "fouls", "goalkeeper_saves", "offsides", "possession_pct", "red_cards", "shots", "shots_on_target", "yellow_cards"),
        completeness=FootballFactCompleteness.COMPLETE if shots_away else FootballFactCompleteness.SCORE_ONLY
    )
    return FootballCompletedMatchFacts(
        fixture=fixture,
        home=home,
        away=away,
        fixture_evidence_bundle_id="b_fix",
        statistics_evidence_bundle_id="b_stats" if (shots_home or shots_away) else None,
        normalization_version="2.0"
    )

def test_sports_entity_id_different_from_domain_id(db_conn):
    # Artificially insert unrelated rows so domains do not start at 1
    db_conn.execute("INSERT INTO sports (name) VALUES ('tennis')")
    db_conn.execute("INSERT INTO sports_entity (sport, entity_type, domain_table, domain_entity_id, created_at) VALUES ('tennis', 'COMPETITION', 'competitions', 999, '2023')")
    
    pers = CanonicalPersistence(db_conn)
    db_conn.execute("""INSERT INTO sports_sync_item (provider, sport, scope_key, provider_fixture_id, first_seen_at, last_checked_at, state, created_at, updated_at)
                       VALUES ('api-football', 'football', 'scope_1', '123', '2023', '2023', 'DISCOVERED', '2023', '2023')""")
                       
    facts = make_dummy_completed_facts()
    pers.persist_completed_facts(facts, "2023-01-01T12:00:00Z", 1)
    
    # sports_entity.id should be distinct from the domain IDs because of the Tennis inserts!
    comp_row = db_conn.execute("SELECT id FROM competitions WHERE name = 'Premier League'").fetchone()
    assert comp_row is not None
    comp_id = comp_row[0]
    
    # Get comp sports_entity row
    se_row = db_conn.execute("SELECT id FROM sports_entity WHERE domain_table = 'competitions' AND domain_entity_id = ?", (comp_id,)).fetchone()
    assert se_row is not None
    sports_entity_id = se_row[0]
    
    assert sports_entity_id != comp_id

def test_correct_second_ingestion_resolution(db_conn):
    pers = CanonicalPersistence(db_conn)
    db_conn.execute("""INSERT INTO sports_sync_item (provider, sport, scope_key, provider_fixture_id, first_seen_at, last_checked_at, state, created_at, updated_at)
                       VALUES ('api-football', 'football', 'scope_1', '123', '2023', '2023', 'DISCOVERED', '2023', '2023')""")
                       
    facts = make_dummy_completed_facts()
    res1 = pers.persist_completed_facts(facts, "2023-01-01T12:00:00Z", 1)
    assert res1["inserted"] == 2
    
    # Ingest same facts again
    res2 = pers.persist_completed_facts(facts, "2023-01-01T12:00:00Z", 1)
    assert res2["inserted"] == 0
    assert res2["reused"] == 2

def test_provider_mapping_conflict(db_conn):
    pers = CanonicalPersistence(db_conn)
    # Artificially insert a conflicting source reference for the same team mapping to a different team domain
    db_conn.execute("INSERT INTO sports (id, name) VALUES (1, 'football')")
    db_conn.execute("INSERT INTO teams (id, name, sport_id) VALUES (101, 'Conflict Team', 1)")
    db_conn.execute("INSERT INTO sports_entity (id, sport, entity_type, domain_table, domain_entity_id, created_at) VALUES (500, 'football', 'TEAM', 'teams', 101, '2023')")
    # Active reference for team "10" maps to sports_entity 500 (Conflict Team)
    db_conn.execute("""INSERT INTO source_entity_reference (sport, entity_type, canonical_entity_id, provider, provider_entity_id, valid_from, verification_status, verification_method)
                       VALUES ('football', 'TEAM', 500, 'api-football', '10', '2023', 'VERIFIED', 'automatic')""")
                       
    # Resolve should resolve team 10 to Conflict Team (101), NOT create a new team with name "Home Team"
    team_id, sports_entity_id = pers._resolve_or_create_team("10", "Home Team")
    assert team_id == 101
    assert sports_entity_id == 500

def test_two_observations_and_unchanged_facts_reuse_and_changed_append(db_conn):
    pers = CanonicalPersistence(db_conn)
    db_conn.execute("""INSERT INTO sports_sync_item (provider, sport, scope_key, provider_fixture_id, first_seen_at, last_checked_at, state, created_at, updated_at)
                       VALUES ('api-football', 'football', 'scope_1', '123', '2023', '2023', 'DISCOVERED', '2023', '2023')""")
                       
    facts1 = make_dummy_completed_facts()
    pers.persist_completed_facts(facts1, "2023-01-01T12:00:00Z", 1)
    
    # 2 observations should exist in total
    count_obs = db_conn.execute("SELECT COUNT(*) FROM fixture_capability_observation").fetchone()[0]
    assert count_obs == 2
    
    # Re-persist the exact same facts: should reuse (inserted=0, reused=2)
    res_reuse = pers.persist_completed_facts(facts1, "2023-01-01T12:00:00Z", 1)
    assert res_reuse["inserted"] == 0
    assert res_reuse["reused"] == 2
    
    # Change facts slightly and re-persist: should append new observations
    facts2 = make_dummy_completed_facts(home_score=3) # goals changed to 3
    res_changed = pers.persist_completed_facts(facts2, "2023-01-01T13:00:00Z", 1)
    # The home team goals changed, but the away team facts are completely identical and reused.
    assert res_changed["inserted"] == 1
    assert res_changed["reused"] == 1
    
    # Now there should be 3 observations
    count_obs2 = db_conn.execute("SELECT COUNT(*) FROM fixture_capability_observation").fetchone()[0]
    assert count_obs2 == 3

def test_64_character_logical_identity_and_projection_names(db_conn):
    pers = CanonicalPersistence(db_conn)
    db_conn.execute("""INSERT INTO sports_sync_item (provider, sport, scope_key, provider_fixture_id, first_seen_at, last_checked_at, state, created_at, updated_at)
                       VALUES ('api-football', 'football', 'scope_1', '123', '2023', '2023', 'DISCOVERED', '2023', '2023')""")
                       
    facts = make_dummy_completed_facts()
    pers.persist_completed_facts(facts, "2023-01-01T12:00:00Z", 1)
    
    row = db_conn.execute("SELECT logical_identity FROM fixture_capability_observation LIMIT 1").fetchone()
    assert row is not None
    logical_id = row[0]
    
    # Must be 64 characters lowercase hex
    assert len(logical_id) == 64
    assert logical_id.islower()
    
    # Compatibility projection column name check in match_stats
    stats = db_conn.execute("SELECT stat_key, stat_value FROM match_stats").fetchall()
    stat_keys = {s[0] for s in stats}
    # should contain "possession" and "saves", not "possession_pct" or "goalkeeper_saves"
    assert "possession" in stat_keys
    assert "saves" in stat_keys
    assert "possession_pct" not in stat_keys
    assert "goalkeeper_saves" not in stat_keys

def test_missing_metric_behavior(db_conn):
    pers = CanonicalPersistence(db_conn)
    db_conn.execute("""INSERT INTO sports_sync_item (provider, sport, scope_key, provider_fixture_id, first_seen_at, last_checked_at, state, created_at, updated_at)
                       VALUES ('api-football', 'football', 'scope_1', '123', '2023', '2023', 'DISCOVERED', '2023', '2023')""")
                       
    # We pass a fixture that only has SCORE_ONLY (shots=None for both teams)
    facts = make_dummy_completed_facts(shots_home=None, shots_away=None)
    pers.persist_completed_facts(facts, "2023-01-01T12:00:00Z", 1)
    
    # Should only persist "goals", all other optional metrics are None, so they shouldn't create match_stats rows!
    stats = db_conn.execute("SELECT stat_key FROM match_stats").fetchall()
    stat_keys = {s[0] for s in stats}
    assert stat_keys == {"goals"} # ONLY goals!

def test_no_half_fixture_after_rollback_on_injected_failure(db_conn):
    pers = CanonicalPersistence(db_conn)
    db_conn.execute("""INSERT INTO sports_sync_item (provider, sport, scope_key, provider_fixture_id, first_seen_at, last_checked_at, state, created_at, updated_at)
                       VALUES ('api-football', 'football', 'scope_1', '123', '2023', '2023', 'DISCOVERED', '2023', '2023')""")
                       
    facts = make_dummy_completed_facts()
    
    # Let's monkeypatch serialize_team_match_facts to raise an exception on the second call (away team)
    call_count = 0
    import bet.enrichment.football.persistence as f_pers
    orig_serialize = f_pers.serialize_team_match_facts
    
    def fake_serialize(tf):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise RuntimeError("Injected Failure between home and away writes!")
        return orig_serialize(tf)
        
    f_pers.serialize_team_match_facts = fake_serialize
    
    try:
        with pytest.raises(RuntimeError, match="Injected Failure"):
            pers.persist_completed_facts(facts, "2023-01-01T12:00:00Z", 1)
    finally:
        f_pers.serialize_team_match_facts = orig_serialize
        
    # After rollback, no observations should have been saved in the DB for this fixture!
    count_obs = db_conn.execute("SELECT COUNT(*) FROM fixture_capability_observation").fetchone()[0]
    assert count_obs == 0
    
    # No match_stats should have been written!
    count_stats = db_conn.execute("SELECT COUNT(*) FROM match_stats").fetchone()[0]
    assert count_stats == 0
