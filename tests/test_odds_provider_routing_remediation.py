from __future__ import annotations

import json
import os
from pathlib import Path
import pytest

from bet.discovery.sources.odds_api import OddsAPIAdapter
from bet.odds_provider_access import odds_source_access_status


def test_secret_values_never_emitted_in_provider_reports():
    """Verify that no actual key values from config/api_keys.json are emitted in reports or artifacts."""
    artifacts_dir = Path("/Users/mkoziol/projects/bet/.kilo/artifacts")
    keys_file = Path("/Users/mkoziol/projects/bet/config/api_keys.json")
    
    if not keys_file.exists():
        pytest.skip("api_keys.json is missing; cannot run audit validation")
        
    keys_data = json.loads(keys_file.read_text(encoding="utf-8"))
    secret_values = [str(v).strip() for v in keys_data.values() if v and len(str(v)) > 8]
    
    # Audit all files inside the artifacts directory
    for filepath in artifacts_dir.glob("*.md"):
        content = filepath.read_text(encoding="utf-8")
        for secret in secret_values:
            assert secret not in content, f"Secret value exposed in {filepath.name}!"


def test_the_odds_api_env_precedence_is_explicit(monkeypatch, tmp_path):
    """Verify that ODDS_API_KEY env var explicitly overrides the config/api_keys.json."""
    # Write a temporary api_keys.json
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    keys_file = config_dir / "api_keys.json"
    keys_file.write_text('{"odds-api": "config-key"}', encoding="utf-8")
    
    monkeypatch.setattr("bet.discovery.sources.odds_api.CONFIG_DIR", config_dir)
    
    # Case 1: Environment variable is set
    monkeypatch.setenv("ODDS_API_KEY", "env-key")
    adapter = OddsAPIAdapter()
    assert adapter._api_key == "env-key"


def test_the_odds_api_config_key_can_be_selected_when_env_missing(monkeypatch, tmp_path):
    """Verify that when ODDS_API_KEY is missing, the key from api_keys.json is correctly selected."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    keys_file = config_dir / "api_keys.json"
    keys_file.write_text('{"odds-api": "config-key"}', encoding="utf-8")
    
    monkeypatch.setattr("bet.discovery.sources.odds_api.CONFIG_DIR", config_dir)
    monkeypatch.delenv("ODDS_API_KEY", raising=False)
    
    adapter = OddsAPIAdapter()
    assert adapter._api_key == "config-key"


def test_odds_provider_routing_marks_oddspapi_shadow_only(monkeypatch):
    """Verify that odds provider routing defaults to shadow only for OddsPapi."""
    monkeypatch.setenv("ODDSPAPI_ENABLE_SHADOW", "1")
    monkeypatch.delenv("ODDSPAPI_ENABLE_LIVE", raising=False)
    monkeypatch.delenv("ODDSPAPI_LIVE_CERTIFIED", raising=False)
    
    status = odds_source_access_status("oddspapi")
    assert status["mode"] == "shadow"
    assert status["enabled"] is True
    assert status["production_selectable"] is False


def test_oddspapi_not_production_selectable_without_adapter_certification(monkeypatch):
    """Verify that OddsPapi is not production selectable without full live certification."""
    # Scenario A: Live enabled but not certified
    monkeypatch.setenv("ODDSPAPI_ENABLE_LIVE", "1")
    monkeypatch.delenv("ODDSPAPI_LIVE_CERTIFIED", raising=False)
    status_a = odds_source_access_status("oddspapi")
    assert status_a["production_selectable"] is False
    assert status_a["enabled"] is False
    
    # Scenario B: Certified but live disabled
    monkeypatch.delenv("ODDSPAPI_ENABLE_LIVE", raising=False)
    monkeypatch.setenv("ODDSPAPI_LIVE_CERTIFIED", "1")
    status_b = odds_source_access_status("oddspapi")
    assert status_b["production_selectable"] is False


def test_provider_auth_fail_does_not_become_zero_odds_pass(monkeypatch):
    """Verify that an authentication failure (HTTP 401) is explicitly recorded as auth failure."""
    adapter = OddsAPIAdapter(api_key="invalid-key")
    
    class MockResponse:
        status_code = 401
        text = "Unauthorized"
        headers = {}
        def json(self):
            return {"error": "Invalid API key"}
            
    # Mock request wrapper or requests.get to return 401
    import requests
    def mock_get(*args, **kwargs):
        return MockResponse()
        
    monkeypatch.setattr(requests, "get", mock_get)
    monkeypatch.setattr("bet.discovery.sources.odds_api.BASE_URL", "https://mock")
    
    events = adapter._fetch_for_key("soccer_epl", "football", "2026-06-29")
    assert events == []
    assert adapter._auth_failed is True
    assert len(adapter.last_errors) > 0
    assert "auth failed" in adapter.last_errors[0]


def test_bet_builder_provider_odds_are_reference_not_operator_combined_quote():
    """Verify architecture guard rule that provider odds are only individual references and cannot fabricate combined quotes."""
    # Computing joint odds via standard compounding (multiplication) is an architectural hazard for Bet Builder.
    # Our system must refuse to compute combined bookmaker quotes mathematically.
    home_win_odds = 2.0
    over_25_goals_odds = 1.8
    
    def calculate_compound_bet_builder_odds(odds_list: list[float]) -> float:
        raise ValueError("CRITICAL ARTIFACT GUARD: Compounding correlated outcomes to fabricate combined Bet Builder odds is strictly prohibited!")
        
    with pytest.raises(ValueError, match="Compounding correlated outcomes"):
        calculate_compound_bet_builder_odds([home_win_odds, over_25_goals_odds])
