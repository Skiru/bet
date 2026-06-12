from __future__ import annotations

import asyncio
import json

import pytest

from bet.api_clients.api_football import APIFixture, APIMatchStats
from bet.api_clients.espn import ESPNClient
from bet.api_clients.rate_limiter import RateLimiter
from bet.db.models import Fixture
from bet.db.repositories import CompetitionRepo, FixtureRepo, SportRepo, TeamRepo
from bet.integration.telemetry_wrapper import TransportResult
from bet.stats.enrichment import enrich_fixtures


@pytest.fixture
def isolated_cache_dir(tmp_path, monkeypatch):
    from bet.api_clients import base_client

    cache_dir = tmp_path / "stats_cache"
    monkeypatch.setattr(base_client, "CACHE_DIR", cache_dir)
    return cache_dir


def _transport_result(payload: str | bytes, status_code: int = 200) -> TransportResult:
    body = payload.encode("utf-8") if isinstance(payload, str) else payload
    return TransportResult(
        success=200 <= status_code < 300,
        status_code=status_code,
        headers={"Content-Type": "application/json"},
        body=body,
    )


def test_get_fixtures_replays_audited_path_without_fabricating_identity(
    monkeypatch, isolated_cache_dir,
):
    from bet.integration import telemetry_wrapper

    payload = {
        "events": [
            {
                "id": "760415",
                "date": "2026-06-11T19:00Z",
                "status": {"type": {"name": "STATUS_SCHEDULED"}},
                "competitions": [
                    {
                        "league": {"name": "FIFA World Cup"},
                        "competitors": [
                            {
                                "id": "mex",
                                "homeAway": "home",
                                "team": {"id": "mex", "displayName": "Mexico"},
                            },
                            {
                                "id": "rsa",
                                "homeAway": "away",
                                "team": {"id": "rsa", "displayName": "South Africa"},
                            },
                        ],
                    }
                ],
            },
            {
                "date": "2026-06-11T21:00Z",
                "competitions": [
                    {
                        "league": {"name": "FIFA World Cup"},
                        "competitors": [
                            {
                                "id": "can",
                                "homeAway": "home",
                                "team": {"id": "can", "displayName": "Canada"},
                            },
                            {
                                "id": "bih",
                                "homeAway": "away",
                                "team": {"id": "bih", "displayName": "Bosnia-Herzegovina"},
                            },
                        ],
                    }
                ],
            },
        ]
    }

    monkeypatch.setattr(
        telemetry_wrapper,
        "wrap_request",
        lambda **_: _transport_result(json.dumps(payload)),
    )

    client = ESPNClient(
        sport="football", league="fifa.world", rate_limiter=RateLimiter()
    )
    fixtures = client.get_fixtures("2026-06-11")

    assert len(fixtures) == 1
    assert fixtures[0].external_id == "760415"
    assert fixtures[0].competition_name == "FIFA World Cup"
    assert fixtures[0].home_team_name == "Mexico"
    assert fixtures[0].away_team_name == "South Africa"
    assert fixtures[0].home_participant_id == "mex"
    assert fixtures[0].away_participant_id == "rsa"


@pytest.mark.parametrize(
    ("transport", "expected"),
    [
        (_transport_result(json.dumps({"events": []})), []),
        (_transport_result("{malformed"), []),
        (_transport_result(json.dumps({"error": "upstream"}), status_code=503), []),
    ],
)
def test_get_fixtures_handles_empty_malformed_and_http_error(
    monkeypatch, isolated_cache_dir, transport, expected,
):
    from bet.integration import telemetry_wrapper

    monkeypatch.setattr(telemetry_wrapper, "wrap_request", lambda **_: transport)

    client = ESPNClient(
        sport="football", league="fifa.world", rate_limiter=RateLimiter()
    )
    assert client.get_fixtures("2026-06-11") == expected


def test_get_fixture_stats_skips_missing_values_without_coercing_to_zero(
    monkeypatch, isolated_cache_dir,
):
    from bet.integration import telemetry_wrapper

    payload = {
        "boxscore": {
            "teams": [
                {
                    "homeAway": "home",
                    "team": {"id": "mex", "displayName": "Mexico"},
                    "statistics": [
                        {"name": "wonCorners", "displayValue": ""},
                        {"name": "foulsCommitted", "displayValue": "10"},
                    ],
                },
                {
                    "homeAway": "away",
                    "team": {"id": "rsa", "displayName": "South Africa"},
                    "statistics": [
                        {"name": "wonCorners", "displayValue": "4"},
                        {"name": "foulsCommitted", "displayValue": "11"},
                    ],
                },
            ]
        },
        "header": {
            "competitions": [
                {
                    "competitors": [
                        {"homeAway": "home", "score": "1"},
                        {"homeAway": "away", "score": "0"},
                    ]
                }
            ]
        },
    }

    monkeypatch.setattr(
        telemetry_wrapper,
        "wrap_request",
        lambda **_: _transport_result(json.dumps(payload)),
    )

    client = ESPNClient(
        sport="football", league="fifa.world", rate_limiter=RateLimiter()
    )
    stats = client.get_fixture_stats("760415")

    assert len(stats) == 1
    assert stats[0].stats["corners"] == {"away": 4.0}
    assert stats[0].stats["fouls"] == {"home": 10.0, "away": 11.0}
    assert stats[0].stats["goals"] == {"home": 1.0, "away": 0.0}
    assert stats[0].home_participant_id == "mex"
    assert stats[0].away_participant_id == "rsa"


def test_resolve_team_id_fails_closed_on_ambiguous_contains_match(
    monkeypatch, isolated_cache_dir,
):
    client = ESPNClient(sport="football", league="eng.1", rate_limiter=RateLimiter())
    monkeypatch.setattr(
        client,
        "_request",
        lambda endpoint, params=None, cost=0: {
            "sports": [
                {
                    "leagues": [
                        {
                            "teams": [
                                {
                                    "team": {
                                        "id": "1",
                                        "displayName": "Manchester United",
                                        "shortDisplayName": "Man United",
                                        "abbreviation": "MUN",
                                        "location": "Manchester",
                                    }
                                },
                                {
                                    "team": {
                                        "id": "2",
                                        "displayName": "Newcastle United",
                                        "shortDisplayName": "Newcastle",
                                        "abbreviation": "NEW",
                                        "location": "Newcastle",
                                    }
                                },
                            ]
                        }
                    ]
                }
            ]
        },
    )

    assert client.resolve_team_id("United") is None


def test_get_team_last_fixtures_applies_cutoff_and_event_exclusion(
    monkeypatch, isolated_cache_dir,
):
    def make_event(event_id: str, date: str, home_id: str, away_id: str):
        return {
            "id": event_id,
            "date": date,
            "status": {"type": {"state": "post", "name": "STATUS_FINAL"}},
            "competitions": [
                {
                    "competitors": [
                        {
                            "id": home_id,
                            "homeAway": "home",
                            "score": "1",
                            "team": {"id": home_id, "displayName": "Crystal Palace"},
                        },
                        {
                            "id": away_id,
                            "homeAway": "away",
                            "score": "0",
                            "team": {"id": away_id, "displayName": "Arsenal"},
                        },
                    ]
                }
            ],
        }

    payload = {
        "events": [
            make_event("740947", "2026-05-10T13:00Z", "384", "362"),
            make_event("740968", "2026-05-24T15:00Z", "384", "359"),
            make_event("same-start", "2026-05-24T15:00Z", "384", "337"),
            make_event("after-target", "2026-05-25T15:00Z", "384", "364"),
            make_event("", "2026-05-08T15:00Z", "384", "363"),
            make_event("bad-date", "not-a-date", "384", "367"),
        ]
    }

    client = ESPNClient(sport="football", league="eng.1", rate_limiter=RateLimiter())
    monkeypatch.setattr(client, "_request", lambda endpoint, params=None, cost=0: payload)

    fixtures = client.get_team_last_fixtures(
        "384",
        last_n=10,
        analysis_cutoff_at="2026-05-24T15:00:00Z",
        exclude_event_ids={"740968"},
    )

    assert [fixture["id"] for fixture in fixtures] == ["740947"]
    assert fixtures[0]["home_participant_id"] == "384"
    assert fixtures[0]["away_participant_id"] == "362"


def test_enrich_fixtures_espn_fallback_is_idempotent_and_preserves_missing_values(
    db_with_sports, monkeypatch, isolated_cache_dir,
):
    football = SportRepo(db_with_sports).get_by_name("football")
    team_repo = TeamRepo(db_with_sports)
    fixture_repo = FixtureRepo(db_with_sports)
    competition_repo = CompetitionRepo(db_with_sports)

    crystal_palace = team_repo.find_or_create(
        "Crystal Palace", football.id, aliases=["Crystal Palace FC", "CPFC"]
    )
    arsenal = team_repo.find_or_create(
        "Arsenal", football.id, aliases=["Arsenal FC", "AFC"]
    )
    competition_id = competition_repo.find_or_create(
        "Premier League", football.id, season="2026"
    )
    fixture = Fixture(
        id=None,
        sport_id=football.id,
        competition_id=competition_id,
        home_team_id=crystal_palace.id,
        away_team_id=arsenal.id,
        kickoff="2026-05-24T15:00:00+00:00",
        status="scheduled",
        external_id="740968",
        source="espn-football",
    )
    fixture.id = fixture_repo.upsert(fixture)
    db_with_sports.commit()

    monkeypatch.setattr(
        ESPNClient,
        "get_fixtures",
        lambda self, date: [
            APIFixture(
                external_id="740968",
                source="espn-football",
                sport="football",
                competition_name="English Premier League",
                home_team_name="Crystal Palace FC",
                away_team_name="Arsenal FC",
                kickoff="2026-05-24T15:00:00Z",
                status="STATUS_SCHEDULED",
                home_participant_id="384",
                away_participant_id="359",
            )
        ],
    )

    calls: list[tuple[str, str, tuple[str, ...]]] = []

    def fake_last_fixtures(
        self, team_id, last_n=10, analysis_cutoff_at=None, exclude_event_ids=None
    ):
        excluded = tuple(sorted(exclude_event_ids or set()))
        calls.append((str(team_id), str(analysis_cutoff_at), excluded))
        # Respect exclude_event_ids - don't return target events
        # Use "740968" as target event ID to match fixture.external_id
        if str(team_id) == "384":
            fixtures = [
                {"id": "740968", "date": "2026-05-24T15:00:00Z"},  # target
                {"id": "cp-valid", "date": "2026-05-17T14:00:00Z"},
            ]
        else:
            fixtures = [
                {"id": "740968", "date": "2026-05-24T15:00:00Z"},  # target
                {"id": "ars-valid", "date": "2026-05-10T15:30:00Z"},
            ]
        # Filter out excluded events
        return [f for f in fixtures if f["id"] not in (exclude_event_ids or set())]

    monkeypatch.setattr(ESPNClient, "get_team_last_fixtures", fake_last_fixtures)

    def fake_get_fixture_stats(self, fixture_id: str):
        if fixture_id == "740968":
            raise AssertionError("target event must be excluded from recent form")
        if fixture_id == "cp-valid":
            return [
                APIMatchStats(
                    external_id="cp-valid",
                    source="espn-football",
                    sport="football",
                    home_team_name="Alias Home",
                    away_team_name="Alias Away",
                    stats={
                        "corners": {"home": 6.0, "away": 1.0},
                        "fouls": {"home": 7.0, "away": 12.0},
                    },
                    home_participant_id="384",
                    away_participant_id="700",
                )
            ]
        if fixture_id == "ars-valid":
            return [
                APIMatchStats(
                    external_id="ars-valid",
                    source="espn-football",
                    sport="football",
                    home_team_name="Alias Home",
                    away_team_name="Alias Away",
                    stats={
                        "corners": {"home": 9.0, "away": 2.0},
                        "fouls": {"home": 8.0, "away": 11.0},
                    },
                    home_participant_id="800",
                    away_participant_id="359",
                )
            ]
        return [
            APIMatchStats(
                external_id="ambiguous",
                source="espn-football",
                sport="football",
                home_team_name="Wrong Name",
                away_team_name="Wrong Other",
                stats={
                    "corners": {"home": 7.0, "away": 5.0},
                    "fouls": {"home": 8.0, "away": 9.0},
                },
                home_participant_id="000",
                away_participant_id="000",
            )
        ]

    monkeypatch.setattr(ESPNClient, "get_fixture_stats", fake_get_fixture_stats)

    result = asyncio.run(enrich_fixtures([fixture], db_with_sports, max_age_hours=0))
    assert result["fetched"] == 2
    assert result["failed"] == 0
    assert sorted(calls) == [
        ("359", "2026-05-24T15:00:00Z", ("740968",)),
        ("384", "2026-05-24T15:00:00Z", ("740968",)),
    ]

    palace_corners = db_with_sports.execute(
        "SELECT l10_values, source FROM team_form "
        "WHERE team_id = ? AND stat_key = 'corners'",
        (crystal_palace.id,),
    ).fetchone()
    arsenal_corners = db_with_sports.execute(
        "SELECT l10_values FROM team_form WHERE team_id = ? AND stat_key = 'corners'",
        (arsenal.id,),
    ).fetchone()
    assert json.loads(palace_corners[0]) == [6.0]
    assert json.loads(arsenal_corners[0]) == [2.0]
    assert palace_corners[1] == "espn-football"

    logical_count_1 = db_with_sports.execute(
        "SELECT COUNT(*) FROM team_form WHERE team_id IN (?, ?)",
        (crystal_palace.id, arsenal.id),
    ).fetchone()[0]

    result_2 = asyncio.run(enrich_fixtures([fixture], db_with_sports, max_age_hours=0))
    logical_count_2 = db_with_sports.execute(
        "SELECT COUNT(*) FROM team_form WHERE team_id IN (?, ?)",
        (crystal_palace.id, arsenal.id),
    ).fetchone()[0]

    assert result_2["fetched"] == 2
    assert logical_count_2 == logical_count_1


def test_enrich_fixtures_espn_skips_neither_side_and_both_side_matches(
    db_with_sports, monkeypatch, isolated_cache_dir,
):
    football = SportRepo(db_with_sports).get_by_name("football")
    team_repo = TeamRepo(db_with_sports)
    fixture_repo = FixtureRepo(db_with_sports)
    competition_repo = CompetitionRepo(db_with_sports)

    crystal_palace = team_repo.find_or_create("Crystal Palace", football.id)
    arsenal = team_repo.find_or_create("Arsenal", football.id)
    competition_id = competition_repo.find_or_create(
        "Premier League", football.id, season="2026"
    )
    fixture = Fixture(
        id=None,
        sport_id=football.id,
        competition_id=competition_id,
        home_team_id=crystal_palace.id,
        away_team_id=arsenal.id,
        kickoff="2026-05-24T15:00:00+00:00",
        status="scheduled",
        external_id="740968",
        source="espn-football",
    )
    fixture.id = fixture_repo.upsert(fixture)
    db_with_sports.commit()

    monkeypatch.setattr(
        ESPNClient,
        "get_fixtures",
        lambda self, date: [
            APIFixture(
                external_id="740968",
                source="espn-football",
                sport="football",
                competition_name="English Premier League",
                home_team_name="Crystal Palace",
                away_team_name="Arsenal",
                kickoff="2026-05-24T15:00:00Z",
                status="STATUS_SCHEDULED",
                home_participant_id="384",
                away_participant_id="359",
            )
        ],
    )
    monkeypatch.setattr(
        ESPNClient,
        "get_team_last_fixtures",
        lambda self, team_id, last_n=10, analysis_cutoff_at=None, exclude_event_ids=None: [
            {"id": f"{team_id}-bad"}
        ],
    )

    def fake_bad_stats(self, fixture_id: str):
        requested = fixture_id.split("-")[0]
        if requested == "384":
            return [
                APIMatchStats(
                    external_id=fixture_id,
                    source="espn-football",
                    sport="football",
                    home_team_name="Wrong Home",
                    away_team_name="Wrong Away",
                    stats={"corners": {"home": 5.0, "away": 1.0}},
                    home_participant_id="000",
                    away_participant_id="111",
                )
            ]
        return [
            APIMatchStats(
                external_id=fixture_id,
                source="espn-football",
                sport="football",
                home_team_name="Wrong Home",
                away_team_name="Wrong Away",
                stats={"corners": {"home": 4.0, "away": 2.0}},
                home_participant_id="359",
                away_participant_id="359",
            )
        ]

    monkeypatch.setattr(ESPNClient, "get_fixture_stats", fake_bad_stats)

    # Mock API-Sports client to also fail (no data returned)
    from bet.api_clients import api_football

    def fake_api_sports_resolve(self, team_name):
        return None  # No team ID resolved

    monkeypatch.setattr(
        api_football.APIFootballClient, "resolve_team_id", fake_api_sports_resolve
    )

    result = asyncio.run(enrich_fixtures([fixture], db_with_sports, max_age_hours=0))
    count = db_with_sports.execute("SELECT COUNT(*) FROM team_form").fetchone()[0]

    assert result["fetched"] == 0
    assert result["failed"] == 2
    assert count == 0


def test_enrich_fixtures_persists_source_event_ids_and_evidence_hash(
    db_with_sports, monkeypatch, isolated_cache_dir,
):
    """REM-001B: Verify source_event_ids and evidence_hash are persisted."""
    football = SportRepo(db_with_sports).get_by_name("football")
    team_repo = TeamRepo(db_with_sports)
    fixture_repo = FixtureRepo(db_with_sports)
    competition_repo = CompetitionRepo(db_with_sports)

    crystal_palace = team_repo.find_or_create("Crystal Palace", football.id)
    arsenal = team_repo.find_or_create("Arsenal", football.id)
    competition_id = competition_repo.find_or_create(
        "Premier League", football.id, season="2026"
    )
    fixture = Fixture(
        id=None,
        sport_id=football.id,
        competition_id=competition_id,
        home_team_id=crystal_palace.id,
        away_team_id=arsenal.id,
        kickoff="2026-05-24T15:00:00+00:00",
        status="scheduled",
        external_id="740968",
        source="espn-football",
    )
    fixture.id = fixture_repo.upsert(fixture)
    db_with_sports.commit()

    monkeypatch.setattr(
        ESPNClient,
        "get_fixtures",
        lambda self, date: [
            APIFixture(
                external_id="740968",
                source="espn-football",
                sport="football",
                competition_name="English Premier League",
                home_team_name="Crystal Palace",
                away_team_name="Arsenal",
                kickoff="2026-05-24T15:00:00Z",
                status="STATUS_SCHEDULED",
                home_participant_id="384",
                away_participant_id="359",
            )
        ],
    )

    def fake_last_fixtures_with_ids(
        self, team_id, last_n=10, analysis_cutoff_at=None, exclude_event_ids=None
    ):
        # Return fixtures with IDs for evidence tracking
        return [
            {"id": "event-001", "date": "2026-05-17T15:00:00Z"},
            {"id": "event-002", "date": "2026-05-10T15:00:00Z"},
        ]

    monkeypatch.setattr(ESPNClient, "get_team_last_fixtures", fake_last_fixtures_with_ids)

    def fake_stats_with_ids(self, fixture_id: str):
        return [
            APIMatchStats(
                external_id=fixture_id,
                source="espn-football",
                sport="football",
                home_team_name="Home",
                away_team_name="Away",
                stats={"corners": {"home": 5.0, "away": 3.0}},
                home_participant_id="384",
                away_participant_id="359",
            )
        ]

    monkeypatch.setattr(ESPNClient, "get_fixture_stats", fake_stats_with_ids)

    # Mock API-Sports to not interfere
    from bet.api_clients import api_football

    monkeypatch.setattr(
        api_football.APIFootballClient, "resolve_team_id", lambda self, name: None
    )

    result = asyncio.run(enrich_fixtures([fixture], db_with_sports, max_age_hours=0))

    assert result["fetched"] == 2

    # Verify source_event_ids and evidence_hash are persisted
    row = db_with_sports.execute(
        "SELECT source_event_ids, evidence_hash FROM team_form "
        "WHERE team_id = ? AND stat_key = 'corners'",
        (crystal_palace.id,),
    ).fetchone()

    assert row is not None
    source_event_ids = json.loads(row[0])
    evidence_hash = row[1]

    # Verify source event IDs are tracked
    assert len(source_event_ids) == 2
    assert "event-001" in source_event_ids
    assert "event-002" in source_event_ids

    # Verify evidence hash is computed (non-empty)
    assert len(evidence_hash) == 16
    assert evidence_hash != ""

    # Verify hash is deterministic (same inputs = same hash)
    import hashlib
    expected_data = json.dumps(sorted(["event-001", "event-002"]), sort_keys=True)
    expected_hash = hashlib.sha256(expected_data.encode()).hexdigest()[:16]
    assert evidence_hash == expected_hash
