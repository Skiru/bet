# ruff: noqa: E501
from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

from bet.api_clients.base_client import SourceOperationResult, SourceResultStatus
from bet.api_clients.football_data_org import FootballDataOrgClient
from bet.api_clients.highlightly import HighlightlyClient
from bet.api_clients.rate_limiter import RateLimiter
from bet.discovery.sources.football_data_org import FootballDataOrgDiscoveryAdapter
from bet.enrichment.football_service import (
    CANDIDATE_REGISTRY,
    FootballDataStandingsAdapter,
    get_route_candidates,
    load_and_validate_config,
    require_production_route,
    select_route_provider,
)
from bet.integration.telemetry_wrapper import TransportResult


def _config(monkeypatch) -> dict:
    monkeypatch.setenv("FOOTBALL_ENRICHMENT_MODE", "shadow")
    return copy.deepcopy(load_and_validate_config())


def _config_dir_copy(tmp_path: Path) -> Path:
    config_dir = tmp_path / "config"
    shutil.copytree(Path("config"), config_dir)
    return config_dir


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
        "production_routes": [
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
    # Ensure football-data is NOT certified at the start of this test
    entry = _football_data_capability(config, "current_discovery")
    entry["status"] = "NOT_TESTED"
    entry["selectable_as_projection"] = False
    entry["evidence_replay"] = False

    # Remove espn from routing to isolate football-data
    config["routing"]["current_discovery"]["production_routes"] = [
        r
        for r in config["routing"]["current_discovery"].get("production_routes", [])
        if r["provider"] != "espn"
    ]

    assert (
        select_route_provider(
            config,
            "current_discovery",
            "football:eng.1",
            mode="shadow",
        )
        is None
    )

    config["routing"]["current_discovery"] = {
        "production_routes": [
            {
                "provider": "football-data",
                "competition_scope": "football:eng.1",
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
        "football:eng.1",
        mode="shadow",
    )
    assert selected is not None
    assert selected["provider"] == "football-data"


def test_football_data_standings_requires_certified_selectable(monkeypatch):
    config = _config(monkeypatch)
    # Ensure football-data is NOT certified at the start of this test
    entry = _football_data_capability(config, "standings")
    entry["status"] = "NOT_TESTED"
    entry["selectable_as_projection"] = False
    entry["evidence_replay"] = False

    config["routing"]["standings"] = {
        "production_routes": [
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
    config["routing"]["standings"]["production_routes"][0]["selectable_status"] = (
        "CERTIFIED_SELECTABLE"
    )

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


def test_football_data_supported_capabilities_restricted():
    from bet.enrichment.football_service import CANDIDATE_REGISTRY

    record = CANDIDATE_REGISTRY["football-data"]
    assert "current_recent_form" not in record.supported_capabilities
    assert "h2h_head_to_head" not in record.supported_capabilities
    assert "fixture_team_statistics" not in record.supported_capabilities
    assert "advanced_xg" not in record.supported_capabilities
    assert set(record.supported_capabilities) == {
        "current_discovery",
        "standings_competition_context",
    }


def test_standings_certification_does_not_make_current_form_selectable(monkeypatch):
    config = _config(monkeypatch)
    # Remove espn from routing to isolate football-data
    config["routing"]["current_form"]["production_routes"] = [
        r
        for r in config["routing"]["current_form"].get("production_routes", [])
        if r["provider"] != "espn"
    ]
    # Certify standings for football-data
    entry = _football_data_capability(config, "standings")
    entry["status"] = "CERTIFIED_SELECTABLE"
    entry["selectable_as_projection"] = True
    entry["evidence_replay"] = True

    # But current_form is not certified
    assert (
        select_route_provider(
            config,
            "current_form",
            "football:eng.1",
            mode="shadow",
        )
        is None
    )


def test_current_discovery_certification_does_not_make_h2h_selectable(monkeypatch):
    config = _config(monkeypatch)
    # Remove espn from routing to isolate football-data
    config["routing"]["historical_form_h2h"]["production_routes"] = [
        r
        for r in config["routing"]["historical_form_h2h"].get("production_routes", [])
        if r["provider"] != "espn"
    ]
    # Certify current_discovery for football-data
    entry = _football_data_capability(config, "current_discovery")
    entry["status"] = "CERTIFIED_SELECTABLE"
    entry["selectable_as_projection"] = True
    entry["evidence_replay"] = True

    # But historical_form_h2h is not certified
    assert (
        select_route_provider(
            config,
            "historical_form_h2h",
            "football:eng.1",
            mode="shadow",
        )
        is None
    )


def test_candidate_registry_replay_metadata_cannot_make_any_capability_selectable(
    monkeypatch,
):
    config = _config(monkeypatch)
    # Ensure football-data is NOT certified at the start of this test
    entry = _football_data_capability(config, "standings")
    entry["status"] = "NOT_TESTED"
    entry["selectable_as_projection"] = False
    entry["evidence_replay"] = False

    # Set up production_routes to contain football-data
    config["routing"]["standings"]["production_routes"] = [
        {
            "provider": "football-data",
            "competition_scope": "football:eng.1",
            "season_scope": "current",
            "mode": "shadow",
            "selectable_status": "NOT_TESTED",
        }
    ]
    # Even if we mock CandidateRecord to have replay_capabilities or supported_capabilities,
    # it does not make a non-certified matrix entry selectable.
    from bet.enrichment.football_service import CANDIDATE_REGISTRY, CandidateRecord

    monkeypatch.setitem(
        CANDIDATE_REGISTRY,
        "football-data",
        CandidateRecord(
            provider_key="football-data",
            implementation_state="PRODUCTION_READY",
            credential_requirement=False,
            governance_state="QUALIFIED_SHADOW",
            provenance_family="football-data-org",
            supported_capabilities=(
                "current_recent_form",
                "h2h_head_to_head",
                "standings_competition_context",
            ),
            replay_capabilities=(
                "current_recent_form",
                "h2h_head_to_head",
                "standings_competition_context",
            ),
            live_probe_eligibility=True,
        ),
    )

    # The matrix entry for standings is still NOT_TESTED and selectable_as_projection=False
    assert (
        select_route_provider(
            config,
            "standings",
            "football:eng.1",
            mode="shadow",
        )
        is None
    )


def test_only_exact_certified_selectable_tuple_can_be_selected(monkeypatch):
    config = _config(monkeypatch)
    # Set up production_routes to contain football-data
    config["routing"]["standings"]["production_routes"] = [
        {
            "provider": "football-data",
            "competition_scope": "football:eng.1",
            "season_scope": "current",
            "mode": "shadow",
            "selectable_status": "CERTIFIED_SELECTABLE",
        }
    ]
    # Set up a matrix entry that is certified selectable but for a different scope/mode
    entry = _football_data_capability(config, "standings")
    entry["status"] = "CERTIFIED_SELECTABLE"
    entry["selectable_as_projection"] = True
    entry["evidence_replay"] = True
    entry["competition_scope"] = "football:eng.1"
    entry["season_scope"] = "current"
    entry["mode"] = "shadow"

    # Query with matching scope/mode -> should be selected
    selected = select_route_provider(
        config,
        "standings",
        "football:eng.1",
        season_scope="current",
        mode="shadow",
    )
    assert selected is not None
    assert selected["provider"] == "football-data"

    # Query with non-matching scope -> should NOT be selected
    assert (
        select_route_provider(
            config,
            "standings",
            "football:esp.1",
            season_scope="current",
            mode="shadow",
        )
        is None
    )

    # Query with non-matching season -> should NOT be selected
    assert (
        select_route_provider(
            config,
            "standings",
            "football:eng.1",
            season_scope="historical",
            mode="shadow",
        )
        is None
    )


def test_candidate_record_is_metadata_only_not_certification_truth(monkeypatch):
    config = _config(monkeypatch)
    # Remove espn from routing to isolate football-data
    config["routing"]["current_form"]["production_routes"] = [
        r
        for r in config["routing"]["current_form"].get("production_routes", [])
        if r["provider"] != "espn"
    ]
    # Even if CandidateRecord says a capability is supported, if it's not in the matrix,
    # or if the matrix entry is not certified, it cannot be selected.
    from bet.enrichment.football_service import CANDIDATE_REGISTRY, CandidateRecord

    monkeypatch.setitem(
        CANDIDATE_REGISTRY,
        "football-data",
        CandidateRecord(
            provider_key="football-data",
            implementation_state="PRODUCTION_READY",
            credential_requirement=False,
            governance_state="QUALIFIED_SHADOW",
            provenance_family="football-data-org",
            supported_capabilities=("current_recent_form",),
            replay_capabilities=("current_recent_form",),
            live_probe_eligibility=True,
        ),
    )

    # current_form is not even in the capabilities of football-data in the matrix
    assert (
        select_route_provider(
            config,
            "current_form",
            "football:eng.1",
            mode="shadow",
        )
        is None
    )


def test_candidate_route_never_selected_even_if_matrix_is_selectable(monkeypatch):
    config = _config(monkeypatch)
    # Set up a route under candidate_routes that has a certified selectable matrix entry
    config["routing"]["current_discovery"] = {
        "candidate_routes": [
            {
                "provider": "football-data",
                "competition_scope": "football:eng.1",
                "season_scope": "current",
                "mode": "shadow",
                "selectable_status": "CERTIFIED_SELECTABLE",
            }
        ]
    }
    # Make the matrix entry certified selectable
    entry = _football_data_capability(config, "current_discovery")
    entry["status"] = "CERTIFIED_SELECTABLE"
    entry["selectable_as_projection"] = True
    entry["evidence_replay"] = True

    # Since it is in candidate_routes, it must NEVER be selected as a projection (selectable_only=True)
    selected = select_route_provider(
        config,
        "current_discovery",
        "football:eng.1",
        mode="shadow",
    )
    assert selected is None

    # But if we query with selectable_only=False, we can retrieve it as a candidate
    candidates = get_route_candidates(
        config,
        "current_discovery",
        "football:eng.1",
        mode="shadow",
        selectable_only=False,
    )
    assert len(candidates) == 1
    assert candidates[0]["provider"] == "football-data"


def test_shadow_route_never_selected_even_if_matrix_is_selectable(monkeypatch):
    config = _config(monkeypatch)
    config["routing"]["current_discovery"] = {
        "shadow_routes": [
            {
                "provider": "football-data",
                "competition_scope": "football:eng.1",
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
        "football:eng.1",
        mode="shadow",
    )
    assert selected is None


def test_route_validation_allows_same_provider_when_scope_differs(tmp_path, monkeypatch):
    monkeypatch.setenv("FOOTBALL_ENRICHMENT_MODE", "shadow")
    config_dir = _config_dir_copy(tmp_path)

    config = yaml.safe_load((config_dir / "football_routing.yaml").read_text(encoding="utf-8"))
    shadow_routes = config["routing"]["detailed_metrics"]["shadow_routes"]
    assert [route["provider"] for route in shadow_routes] == ["sportdb", "sportdb"]

    validated = load_and_validate_config(config_dir)
    validated_shadow_routes = validated["routing"]["detailed_metrics"]["shadow_routes"]
    assert [route["provider"] for route in validated_shadow_routes] == ["sportdb", "sportdb"]


def test_route_validation_rejects_exact_duplicate_route_identity(tmp_path, monkeypatch):
    monkeypatch.setenv("FOOTBALL_ENRICHMENT_MODE", "shadow")
    config_dir = _config_dir_copy(tmp_path)

    routing_path = config_dir / "football_routing.yaml"
    config = yaml.safe_load(routing_path.read_text(encoding="utf-8"))
    duplicate_route = copy.deepcopy(config["routing"]["detailed_metrics"]["shadow_routes"][0])
    config["routing"]["detailed_metrics"]["shadow_routes"].append(duplicate_route)
    routing_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError, match="Duplicate route identity"):
        load_and_validate_config(config_dir)


def test_understat_cannot_be_selected_outside_advanced_xg(monkeypatch):
    config = _config(monkeypatch)
    config["routing"]["current_form"] = {
        "production_routes": [
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
        "production_routes": [
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
        provider_capabilities["current_discovery"][0]["competition_scope"] = (
            "football:eng.1"
        )
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
        "production_routes": [
            {
                "provider": "football-data",
                "competition_scope": "football:eng.1",
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


def _highlightly_capability(config: dict, capability: str, season_scope: str) -> dict:
    for entry in config["provider_capability_matrix"]["providers"]["highlightly"][
        "capabilities"
    ][capability]:
        if entry["season_scope"] == season_scope:
            return entry
    raise AssertionError(
        f"missing highlightly capability tuple for {capability}/{season_scope}"
    )


def _transport(
    payload: object, status_code: int = 200, headers: dict | None = None
) -> TransportResult:
    return TransportResult(
        success=200 <= status_code < 300,
        status_code=status_code,
        headers=headers or {"Content-Type": "application/json"},
        body=json.dumps(payload).encode("utf-8"),
    )


def test_highlightly_exact_scope_is_selectable_only_for_current_season_completed(
    monkeypatch,
):
    config = _config(monkeypatch)

    completed = require_production_route(
        config,
        "current_form",
        "football:eng.1",
        season_scope="current-season-completed",
        mode="shadow",
    )
    assert completed["provider"] == "highlightly"

    live_route = require_production_route(
        config,
        "current_form",
        "football:eng.1",
        season_scope="current",
        mode="shadow",
    )
    assert live_route["provider"] == "espn"


def test_highlightly_completed_season_proof_does_not_imply_current_live_or_football_star(
    monkeypatch,
):
    config = _config(monkeypatch)
    config["routing"]["current_form"]["production_routes"] = [
        route
        for route in config["routing"]["current_form"]["production_routes"]
        if route["provider"] == "highlightly"
    ]

    assert (
        select_route_provider(
            config,
            "current_form",
            "football:eng.1",
            season_scope="current",
            mode="shadow",
        )
        is None
    )
    assert (
        select_route_provider(
            config,
            "current_form",
            "football:*",
            season_scope="current-season-completed",
            mode="shadow",
        )
        is None
    )


def test_highlightly_capability_certification_is_capability_scoped(monkeypatch):
    config = _config(monkeypatch)
    config["routing"]["historical_form_h2h"]["production_routes"] = [
        {
            "provider": "highlightly",
            "competition_scope": "football:eng.1",
            "season_scope": "current-season-completed",
            "mode": "shadow",
            "selectable_status": "CERTIFIED_SELECTABLE",
        }
    ]
    h2h_entry = _highlightly_capability(
        config, "historical_form_h2h", "current-season-completed"
    )
    h2h_entry["status"] = "NOT_TESTED"
    h2h_entry["selectable_as_projection"] = False
    h2h_entry["evidence_replay"] = False

    assert (
        select_route_provider(
            config,
            "historical_form_h2h",
            "football:eng.1",
            season_scope="current-season-completed",
            mode="shadow",
        )
        is None
    )

    detailed_entry = _highlightly_capability(
        config, "detailed_metrics", "current-season-completed"
    )
    assert detailed_entry["status"] == "CERTIFIED_SELECTABLE"


def test_highlightly_statistics_requires_provider_native_team_ids():
    client = HighlightlyClient(rate_limiter=RateLimiter())
    result = client.get_statistics_result(
        "1028343227", home_team_id="", away_team_id="39930"
    )
    assert result.status is SourceResultStatus.AMBIGUOUS
    assert result.error_code == "provider_native_team_ids_required"


def test_highlightly_statistics_rejects_basic_match_metadata(monkeypatch, tmp_path):
    monkeypatch.setenv("BET_EVIDENCE_ROOT", str(tmp_path))
    monkeypatch.setattr(
        "bet.integration.telemetry_wrapper.wrap_request",
        lambda **kwargs: _transport(
            [
                {
                    "team": {"id": 30569, "name": "Bournemouth"},
                    "state": {"description": "Finished"},
                }
            ]
        ),
    )
    client = HighlightlyClient(rate_limiter=RateLimiter())
    client.api_key = "test-key"

    result = client.get_statistics_result(
        "1028343227",
        home_team_id="30569",
        away_team_id="39930",
    )
    assert result.status is SourceResultStatus.SCHEMA_ERROR
    assert result.error_code == "statistics_list_missing"


def test_highlightly_statistics_preserves_raw_stat_names_and_missing_red_cards(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("BET_EVIDENCE_ROOT", str(tmp_path))
    monkeypatch.setattr(
        "bet.integration.telemetry_wrapper.wrap_request",
        lambda **kwargs: _transport(
            [
                {
                    "team": {"id": 30569, "name": "Bournemouth"},
                    "statistics": [
                        {"displayName": "Expected Goals", "value": 1.79},
                        {"displayName": "Shots on target", "value": 7},
                    ],
                },
                {
                    "team": {"id": 39930, "name": "Leicester"},
                    "statistics": [
                        {"displayName": "Expected Goals", "value": 0.52},
                        {"displayName": "Yellow cards", "value": 1},
                    ],
                },
            ],
            headers={
                "Content-Type": "application/json",
                "x-ratelimit-requests-limit": "100",
                "x-ratelimit-requests-remaining": "60",
            },
        ),
    )
    client = HighlightlyClient(rate_limiter=RateLimiter())
    client.api_key = "test-key"

    result = client.get_statistics_result(
        "1028343227",
        home_team_id="30569",
        away_team_id="39930",
    )
    assert result.status is SourceResultStatus.SUCCESS
    assert result.value is not None
    assert result.value["raw_stat_field_names"] == [
        "Expected Goals",
        "Shots on target",
        "Yellow cards",
    ]
    assert result.value["missing_target_metrics"] == ["Red cards"]
    assert "red_cards" not in result.value["normalized_metric_names"]
    assert result.value["statistics"][0]["normalized_metric_name"] == "expected_goals"
    assert result.quota_metadata == {"minute_limit": 100, "minute_remaining": 60}


def test_live_env_preflight_rejects_misspelled_highlightly_alias(tmp_path):
    repo_root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env.pop("HIGHLIGHTLY_API_KEY", None)
    env.pop("RAPIDAPI_KEY", None)
    env["HIGHLIGHTY_API_KEY"] = "should-not-be-accepted"
    env["PYTHONPATH"] = "src:scripts"

    result = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "live_env_preflight.py"),
            "--provider",
            "highlightly",
            "--required",
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout.strip())
    assert payload["present"] is False
    assert payload["found_key"] == "HIGHLIGHTLY_API_KEY"


def test_sportdb_remains_strategic_p2e_and_not_selectable(monkeypatch):
    config = _config(monkeypatch)
    assert CANDIDATE_REGISTRY["sportdb"].governance_state == "STRATEGIC_P2E"
    assert (
        select_route_provider(
            config,
            "current_discovery",
            "football:eng.1",
            season_scope="current",
            mode="shadow",
        )["provider"]
        != "sportdb"
    )
