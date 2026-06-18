from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from bet.api_clients.base_client import SourceOperationResult, SourceResultStatus
from bet.api_clients.football_data_org import FootballDataOrgClient
from bet.api_clients.rate_limiter import RateLimiter
from bet.discovery.sources.football_data_org import FootballDataOrgDiscoveryAdapter
from bet.enrichment.football_service import (
    FootballDataStandingsAdapter,
    load_and_validate_config,
    require_production_route,
    select_route_provider,
)


def _config(monkeypatch) -> dict:
    monkeypatch.setenv("FOOTBALL_ENRICHMENT_MODE", "shadow")
    return copy.deepcopy(load_and_validate_config())


def _football_data_capability(config: dict, capability: str) -> dict:
    return config["provider_capability_matrix"]["providers"]["football-data"][
        "capabilities"
    ][capability][0]


class _Response:
    def __init__(self, payload: dict, status_code: int = 200):
        self.status_code = status_code
        self.headers = {"Content-Type": "application/json"}
        self.content = json.dumps(payload).encode("utf-8")
        self.text = self.content.decode("utf-8")


def test_football_data_fixtures_result_writes_evidence_bundle(monkeypatch, tmp_path):
    monkeypatch.setenv("BET_EVIDENCE_ROOT", str(tmp_path))
    monkeypatch.setattr(
        "bet.api_clients.base_client.requests.get",
        lambda *args, **kwargs: _Response(
            {
                "matches": [
                    {
                        "id": 111,
                        "utcDate": "2026-05-24T15:00:00Z",
                        "status": "SCHEDULED",
                        "competition": {"name": "Premier League", "code": "PL"},
                        "homeTeam": {"id": 1, "name": "Arsenal"},
                        "awayTeam": {"id": 2, "name": "Chelsea"},
                    }
                ]
            }
        ),
    )

    client = FootballDataOrgClient(rate_limiter=RateLimiter())
    client.api_key = "test-key"
    result = client.get_fixtures_result("2026-05-24")

    assert result.status is SourceResultStatus.SUCCESS
    assert len(result.bundle_id) == 64
    assert result.value[0].competition == "PL"
    assert result.value[0].home_team == "Arsenal"


def test_football_data_standings_result_writes_evidence_bundle(monkeypatch, tmp_path):
    monkeypatch.setenv("BET_EVIDENCE_ROOT", str(tmp_path))
    monkeypatch.setattr(
        "bet.api_clients.base_client.requests.get",
        lambda *args, **kwargs: _Response(
            {
                "standings": [
                    {
                        "stage": "REGULAR_SEASON",
                        "table": [
                            {
                                "position": 1,
                                "team": {"id": 57, "name": "Arsenal"},
                                "playedGames": 38,
                                "won": 26,
                                "draw": 8,
                                "lost": 4,
                                "points": 86,
                                "goalsFor": 79,
                                "goalsAgainst": 31,
                                "goalDifference": 48,
                                "form": "WWWWW",
                            }
                        ],
                    }
                ]
            }
        ),
    )

    client = FootballDataOrgClient(rate_limiter=RateLimiter())
    client.api_key = "test-key"
    result = client.get_standings_result("PL")

    assert result.status is SourceResultStatus.SUCCESS
    assert len(result.bundle_id) == 64
    assert result.value[0]["table"][0]["position"] == 1


def test_football_data_discovery_adapter_uses_result_bundle(monkeypatch):
    adapter = FootballDataOrgDiscoveryAdapter()
    adapter._client = MagicMock()
    adapter._client.get_fixtures_result.return_value = SourceOperationResult(
        status=SourceResultStatus.SUCCESS,
        value=[
            type(
                "Fixture",
                (),
                {
                    "fixture_id": "fd-1",
                    "competition": "PL",
                    "home_team": "Arsenal",
                    "away_team": "Chelsea",
                    "home_team_id": "1",
                    "away_team_id": "2",
                    "kickoff": "2026-05-24T15:00:00Z",
                    "status": "SCHEDULED",
                },
            )()
        ],
        bundle_id="b" * 64,
        evidence_refs=(),
    )

    events = adapter.fetch_events("2026-05-24", "football")

    assert len(events) == 1
    assert events[0].source == "football-data"
    assert events[0].raw_data["evidence_bundle_id"] == "b" * 64


def test_football_data_standings_adapter_maps_eng1_to_pl():
    client = MagicMock()
    client.get_standings_result.return_value = SourceOperationResult(
        status=SourceResultStatus.SUCCESS,
        value=[
            {
                "table": [
                    {
                        "position": 1,
                        "team": {"id": 57, "name": "Arsenal"},
                        "playedGames": 38,
                        "won": 26,
                        "draw": 8,
                        "lost": 4,
                        "points": 86,
                        "goalsFor": 79,
                        "goalsAgainst": 31,
                        "goalDifference": 48,
                        "form": "WWWWW",
                    }
                ]
            }
        ],
        bundle_id="c" * 64,
        evidence_refs=(),
    )
    adapter = FootballDataStandingsAdapter(client)

    result = adapter.fetch_capability(
        "standings_competition_context",
        1,
        datetime.now(UTC),
        competition_id=99,
        native_competition_id="eng.1",
    )

    client.get_standings_result.assert_called_once_with("PL")
    assert result.status is SourceResultStatus.SUCCESS
    assert result.value.competition_native_id == "PL"


def test_api_football_plan_restricted_current_discovery_not_selectable(monkeypatch):
    config = _config(monkeypatch)
    config["routing"]["current_discovery"] = {
        "routes": [
            {
                "provider": "api-football",
                "competition_scope": "football:*",
                "season_scope": "current",
                "mode": "shadow",
                "selectable_status": "PLAN_RESTRICTED_CURRENT",
            }
        ]
    }

    assert (
        select_route_provider(
            config,
            "current_discovery",
            "football:eng.1",
            mode="shadow",
        )
        is None
    )
    with pytest.raises(ValueError):
        require_production_route(
            config,
            "current_discovery",
            "football:eng.1",
            mode="shadow",
        )


def test_football_data_current_discovery_requires_certified_selectable(monkeypatch):
    config = _config(monkeypatch)

    assert select_route_provider(
        config,
        "current_discovery",
        "football:competition_supported",
        mode="shadow",
    ) is None

    config["routing"]["current_discovery"] = {
        "routes": [
            {
                "provider": "football-data",
                "competition_scope": "football:competition_supported",
                "season_scope": "current",
                "mode": "shadow",
                "selectable_status": "CERTIFIED_SELECTABLE",
            }
        ]
    }
    entry = _football_data_capability(config, "current_discovery")
    entry["status"] = "CERTIFIED_SELECTABLE"
    entry["selectable_as_projection"] = True
    entry["evidence_replay"] = True

    selected = select_route_provider(
        config,
        "current_discovery",
        "football:competition_supported",
        mode="shadow",
    )
    assert selected is not None
    assert selected["provider"] == "football-data"


def test_football_data_standings_requires_certified_selectable(monkeypatch):
    config = _config(monkeypatch)
    config["routing"]["standings"] = {
        "routes": [
            {
                "provider": "football-data",
                "competition_scope": "football:eng.1",
                "season_scope": "current",
                "mode": "shadow",
                "selectable_status": "NOT_TESTED",
            }
        ]
    }

    assert (
        select_route_provider(config, "standings", "football:eng.1", mode="shadow")
        is None
    )

    entry = _football_data_capability(config, "standings")
    entry["status"] = "CERTIFIED_SELECTABLE"
    entry["selectable_as_projection"] = True
    entry["evidence_replay"] = True
    config["routing"]["standings"]["routes"][0][
        "selectable_status"
    ] = "CERTIFIED_SELECTABLE"

    selected = select_route_provider(
        config,
        "standings",
        "football:eng.1",
        mode="shadow",
    )
    assert selected is not None
    assert selected["provider"] == "football-data"


def test_espn_eng1_scope_does_not_imply_football_star(monkeypatch):
    config = _config(monkeypatch)

    selected = require_production_route(
        config,
        "current_discovery",
        "football:eng.1",
        mode="shadow",
    )
    assert selected["provider"] == "espn"

    assert (
        select_route_provider(config, "current_discovery", "football:*", mode="shadow")
        is None
    )
    with pytest.raises(ValueError):
        require_production_route(
            config,
            "current_discovery",
            "football:*",
            mode="shadow",
        )


def test_understat_cannot_be_selected_outside_advanced_xg(monkeypatch):
    config = _config(monkeypatch)
    config["routing"]["current_form"] = {
        "routes": [
            {
                "provider": "understat",
                "competition_scope": "football:eng.1",
                "season_scope": "current",
                "mode": "shadow",
                "selectable_status": "CERTIFIED_SHADOW",
            }
        ]
    }

    assert (
        select_route_provider(config, "current_form", "football:eng.1", mode="shadow")
        is None
    )
    with pytest.raises(ValueError):
        require_production_route(
            config,
            "current_form",
            "football:eng.1",
            mode="shadow",
        )


@pytest.mark.parametrize("provider", ["sofascore", "flashscore", "soccerway"])
def test_browser_scrapers_cannot_enter_production_routing(monkeypatch, provider):
    config = _config(monkeypatch)
    config["routing"]["current_discovery"] = {
        "routes": [
            {
                "provider": provider,
                "competition_scope": "football:eng.1",
                "season_scope": "current",
                "mode": "shadow",
                "selectable_status": "CERTIFIED_SELECTABLE",
            }
        ]
    }
    provider_capabilities = config["provider_capability_matrix"]["providers"][provider][
        "capabilities"
    ]
    provider_capabilities.setdefault(
        "current_discovery",
        [
            {
                "status": "CERTIFIED_SELECTABLE",
                "competition_scope": "football:eng.1",
                "season_scope": "current",
                "mode": "shadow",
                "selectable_as_projection": True,
                "evidence_replay": True,
                "exact_reason": "test override",
            }
        ],
    )
    if provider_capabilities["current_discovery"]:
        provider_capabilities["current_discovery"][0]["status"] = "CERTIFIED_SELECTABLE"
        provider_capabilities["current_discovery"][0][
            "competition_scope"
        ] = "football:eng.1"
        provider_capabilities["current_discovery"][0]["season_scope"] = "current"
        provider_capabilities["current_discovery"][0]["mode"] = "shadow"
        provider_capabilities["current_discovery"][0]["selectable_as_projection"] = True
        provider_capabilities["current_discovery"][0]["evidence_replay"] = True

    assert (
        select_route_provider(
            config,
            "current_discovery",
            "football:eng.1",
            mode="shadow",
        )
        is None
    )
    with pytest.raises(ValueError):
        require_production_route(
            config,
            "current_discovery",
            "football:eng.1",
            mode="shadow",
        )


@pytest.mark.parametrize(
    "status",
    [
        "CERTIFIED_SHADOW",
        "RESEARCH_ONLY",
        "REFERENCE_ONLY",
        "SEPARATE_PIPELINE",
        "PLAN_RESTRICTED_CURRENT",
    ],
)
def test_non_selectable_statuses_fail_production_validation(monkeypatch, status):
    config = _config(monkeypatch)
    config["routing"]["current_discovery"] = {
        "routes": [
            {
                "provider": "football-data",
                "competition_scope": "football:competition_supported",
                "season_scope": "current",
                "mode": "shadow",
                "selectable_status": status,
            }
        ]
    }
    entry = _football_data_capability(config, "current_discovery")
    entry["status"] = status
    entry["selectable_as_projection"] = False
    entry["evidence_replay"] = False

    assert select_route_provider(
        config,
        "current_discovery",
        "football:competition_supported",
        mode="shadow",
    ) is None
    with pytest.raises(ValueError):
        require_production_route(
            config,
            "current_discovery",
            "football:competition_supported",
            mode="shadow",
        )
