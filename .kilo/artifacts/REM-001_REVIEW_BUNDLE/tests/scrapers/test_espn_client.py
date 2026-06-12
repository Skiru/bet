from __future__ import annotations

import asyncio
import json

import pytest

from bet.api_clients.api_football import APIMatchStats
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
                            {"homeAway": "home", "team": {"displayName": "Mexico"}},
                            {
                                "homeAway": "away",
                                "team": {"displayName": "South Africa"},
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
                            {"homeAway": "home", "team": {"displayName": "Canada"}},
                            {
                                "homeAway": "away",
                                "team": {"displayName": "Bosnia-Herzegovina"},
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
                    "team": {"displayName": "Mexico"},
                    "statistics": [
                        {"name": "wonCorners", "displayValue": ""},
                        {"name": "foulsCommitted", "displayValue": "10"},
                    ],
                },
                {
                    "homeAway": "away",
                    "team": {"displayName": "South Africa"},
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


def test_enrich_fixtures_espn_fallback_is_idempotent_and_preserves_missing_values(
    db_with_sports, monkeypatch,
):
    football = SportRepo(db_with_sports).get_by_name("football")
    team_repo = TeamRepo(db_with_sports)
    fixture_repo = FixtureRepo(db_with_sports)
    competition_repo = CompetitionRepo(db_with_sports)

    mexico = team_repo.find_or_create("Mexico", football.id)
    south_africa = team_repo.find_or_create("South Africa", football.id)
    competition_id = competition_repo.find_or_create(
        "World Cup", football.id, season="2026"
    )
    fixture = Fixture(
        id=None,
        sport_id=football.id,
        competition_id=competition_id,
        home_team_id=mexico.id,
        away_team_id=south_africa.id,
        kickoff="2026-06-11T19:00:00",
        status="scheduled",
        source="seed",
    )
    fixture.id = fixture_repo.upsert(fixture)
    db_with_sports.commit()

    monkeypatch.setattr(
        ESPNClient, "resolve_team_id", lambda self, team_name: team_name.lower()
    )
    monkeypatch.setattr(
        ESPNClient,
        "get_team_last_fixtures",
        lambda self, team_id, last_n=10: [{"id": "m1"}, {"id": "m2"}, {"id": "m3"}],
    )

    def fake_get_fixture_stats(self, fixture_id: str):
        if fixture_id == "m1":
            return []
        if fixture_id == "m2":
            return [
                APIMatchStats(
                    external_id="m2",
                    source="espn-football",
                    sport="football",
                    home_team_name="Mexico",
                    away_team_name="South Africa",
                    stats={
                        "corners": {"away": 3.0},
                        "fouls": {"home": 10.0, "away": 9.0},
                    },
                )
            ]
        return [
            APIMatchStats(
                external_id="m3",
                source="espn-football",
                sport="football",
                home_team_name="Mexico",
                away_team_name="South Africa",
                stats={
                    "corners": {"home": 7.0, "away": 5.0},
                    "fouls": {"home": 8.0, "away": 12.0},
                },
            )
        ]

    monkeypatch.setattr(ESPNClient, "get_fixture_stats", fake_get_fixture_stats)

    result = asyncio.run(enrich_fixtures([fixture], db_with_sports, max_age_hours=0))
    assert result["fetched"] == 2
    assert result["failed"] == 0

    mexico_corners = db_with_sports.execute(
        "SELECT l10_values, source FROM team_form "
        "WHERE team_id = ? AND stat_key = 'corners'",
        (mexico.id,),
    ).fetchone()
    assert json.loads(mexico_corners[0]) == [7.0]
    assert mexico_corners[1] == "espn-football"

    logical_count_1 = db_with_sports.execute(
        "SELECT COUNT(*) FROM team_form WHERE team_id IN (?, ?)",
        (mexico.id, south_africa.id),
    ).fetchone()[0]

    result_2 = asyncio.run(enrich_fixtures([fixture], db_with_sports, max_age_hours=0))
    logical_count_2 = db_with_sports.execute(
        "SELECT COUNT(*) FROM team_form WHERE team_id IN (?, ?)",
        (mexico.id, south_africa.id),
    ).fetchone()[0]

    assert result_2["fetched"] == 2
    assert logical_count_2 == logical_count_1
