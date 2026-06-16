import json
import sqlite3
from datetime import UTC, datetime

import pytest

from bet.db.schema import init_db
from bet.enrichment.football.repository import FootballHistoryRepository


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    # create sports and teams
    conn.execute("INSERT INTO sports (id, name, tier) VALUES (1, 'football', 1)")
    conn.execute("INSERT INTO teams (id, name, sport_id) VALUES (1, 'Home', 1)")
    conn.execute("INSERT INTO teams (id, name, sport_id) VALUES (2, 'Away', 1)")
    conn.execute("INSERT INTO teams (id, name, sport_id) VALUES (3, 'Other', 1)")
    yield conn
    conn.close()

def test_point_in_time_filtering(db):
    # target fixture
    db.execute("INSERT INTO fixtures (id, sport_id, home_team_id, away_team_id, kickoff, status, fetched_at) VALUES (100, 1, 1, 2, '2023-05-01T12:00:00Z', 'scheduled', '2023-05-01T00:00:00Z')")

    # finished fixture before cutoff
    db.execute("INSERT INTO fixtures (id, sport_id, home_team_id, away_team_id, kickoff, status, fetched_at) VALUES (101, 1, 1, 3, '2023-04-01T12:00:00Z', 'finished', '2023-04-01T00:00:00Z')")

    payload = {
        "fixture": {"home_provider_team_id": "P1", "away_provider_team_id": "P3"},
        "home": {"goals": 2}, "away": {"goals": 1}
    }

    # valid observation
    db.execute(
        "INSERT INTO fixture_capability_observation (canonical_fixture_id, team_id, capability, source, status, observed_at, valid_at, logical_identity, payload_json, native_team_id, native_fixture_id, request_identity) VALUES (101, 1, 'TEAM_MATCH_FACTS', 'api-football', 'SUCCESS', '2023-04-02T12:00:00Z', '2023-04-01T12:00:00Z', 'log1', ?, 'P1', 'F101', 'req')",
        (json.dumps(payload),)
    )

    # observation after cutoff
    db.execute(
        "INSERT INTO fixture_capability_observation (canonical_fixture_id, team_id, capability, source, status, observed_at, valid_at, logical_identity, payload_json, native_team_id, native_fixture_id, request_identity) VALUES (101, 1, 'TEAM_MATCH_FACTS', 'api-football', 'SUCCESS', '2023-05-02T12:00:00Z', '2023-04-01T12:00:00Z', 'log2', ?, 'P1', 'F101', 'req2')",
        (json.dumps(payload),)
    )

    repo = FootballHistoryRepository(db)
    cutoff = datetime(2023, 5, 1, tzinfo=UTC)

    samples_by_team = repo.get_eligible_observations_by_team(100, cutoff, ["goals"], ["SUCCESS"])

    assert len(samples_by_team[1]) == 1
    sample = samples_by_team[1][0]
    assert sample.observation_logical_identity == "log1"
    assert sample.value == 2.0
