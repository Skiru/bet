from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from bet.enrichment.football_data_foundation.kernel.contracts import FactType, ProofLevel
from bet.enrichment.football_data_foundation.kernel.errors import (
    CredentialsMissingError,
    ProviderCapabilityError,
)
from bet.enrichment.football_data_foundation.provider_clients.current_live import (
    APIFootballDeferredClient,
    FootballDataOrgLiveClient,
    HighlightlyLiveClient,
    SportDBLiveClient,
    TheSportsDBMetadataClient,
)
from bet.enrichment.football_data_foundation.transport.http_json import MockHttpJsonTransport

FIXTURES_DIR = (
    Path(__file__).parent.parent.parent
    / "fixtures"
    / "enrichment"
    / "football_data_foundation"
    / "pass2"
)


def test_sportdb_client(monkeypatch) -> None:
    monkeypatch.delenv("SPORTDB_API_KEY", raising=False)
    client = SportDBLiveClient()
    with pytest.raises(CredentialsMissingError):
        client.fetch_match_stats("sdb-1")

    monkeypatch.setenv("SPORTDB_API_KEY", "test-key-123")
    
    fixture_path = FIXTURES_DIR / "providers" / "sportdb_stats.json"
    mock_body = json.loads(fixture_path.read_text(encoding="utf-8"))
    
    transport = MockHttpJsonTransport({"sportdb.dev": mock_body})
    client = SportDBLiveClient(transport=transport)
    
    batch = client.fetch_match_stats("sdb-1")
    
    assert len(transport.calls) == 1
    assert transport.calls[0]["headers"]["X-API-Key"] == "test-key-123"
    
    assert len(batch.claims) == 1
    claim = batch.claims[0]
    assert claim.proof_level == ProofLevel.REAL_LIVE_API_PROOF
    assert claim.fact_type == FactType.MATCH_STATISTIC
    assert claim.selectable_for_production is False
    assert batch.to_public_dict()["selectable_for_production"] is False
    assert claim.claim_value["status"] == "LIVE"
    assert claim.claim_value["score_home"] == 1


def test_football_data_org_client(monkeypatch) -> None:
    monkeypatch.delenv("FOOTBALL_DATA_API_KEY", raising=False)
    client = FootballDataOrgLiveClient()
    with pytest.raises(CredentialsMissingError):
        client.fetch_competition_standings("PL")

    monkeypatch.setenv("FOOTBALL_DATA_API_KEY", "test-auth-token")
    fixture_path = FIXTURES_DIR / "providers" / "football_data_standings.json"
    mock_body = json.loads(fixture_path.read_text(encoding="utf-8"))
    
    transport = MockHttpJsonTransport({"football-data.org": mock_body})
    client = FootballDataOrgLiveClient(transport=transport)
    
    batch = client.fetch_competition_standings("PL")
    
    assert len(transport.calls) == 1
    assert transport.calls[0]["headers"]["X-Auth-Token"] == "test-auth-token"
    
    assert len(batch.claims) == 1
    claim = batch.claims[0]
    assert claim.proof_level == ProofLevel.REAL_LIVE_API_PROOF
    assert claim.fact_type == FactType.STANDINGS
    assert claim.selectable_for_production is False
    assert "xg" not in claim.claim_value
    assert "shots" not in claim.claim_value


def test_highlightly_client(monkeypatch) -> None:
    monkeypatch.delenv("HIGHLIGHTLY_API_KEY", raising=False)
    client = HighlightlyLiveClient()
    with pytest.raises(CredentialsMissingError):
        client.fetch_match_statistics("h-1")

    monkeypatch.setenv("HIGHLIGHTLY_API_KEY", "test-hl-key")
    fixture_path = FIXTURES_DIR / "providers" / "highlightly_stats.json"
    mock_body = json.loads(fixture_path.read_text(encoding="utf-8"))
    
    transport = MockHttpJsonTransport({"highlightly.com": mock_body})
    client = HighlightlyLiveClient(transport=transport)
    
    batch = client.fetch_match_statistics("h-1")
    
    assert len(transport.calls) == 1
    assert transport.calls[0]["headers"]["Authorization"] == "Bearer test-hl-key"
    
    assert len(batch.claims) == 1
    claim = batch.claims[0]
    assert claim.claim_value["stat_count"] == 3
    assert claim.claim_value["has_odds_reference"] is True
    assert claim.claim_value["has_player_data_context"] is True


def test_deferred_and_metadata_clients() -> None:
    client_deferred = APIFootballDeferredClient()
    with pytest.raises(ProviderCapabilityError):
        client_deferred.fetch_match_stats("api-1")
        
    client_metadata = TheSportsDBMetadataClient()
    with pytest.raises(ProviderCapabilityError):
        client_metadata.fetch_metadata()

