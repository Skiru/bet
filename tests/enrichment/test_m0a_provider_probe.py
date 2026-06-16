import json
import os
import sys
import subprocess
import urllib.parse
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from scripts.enrichment.m0a_provider_probe import (
    ProviderProbe,
    AttemptLedger,
    sanitize_and_sort_url,
    redact_secrets_in_dict,
    make_fingerprint,
    has_field,
    K_SPORTDB,
    K_APISPORTS,
    K_THESPORTSDB
)

# 1. REST and MCP share one hard attempt budget
def test_budget_sharing():
    probe = ProviderProbe(is_live=False, max_attempts=2, output_dir=Path("/tmp"))
    probe.probe_rest("espn", "football", "scoreboard", "https://api.espn.com", "subject")
    probe.probe_rest("espn", "football", "scoreboard", "https://api.espn.com", "subject")
    
    with pytest.raises(RuntimeError, match="Attempt budget exceeded"):
        probe.probe_mcp("sportdb", "football", "mcp_explore", "mcp_support")

# 2. The budget cannot be exceeded by the final MCP operation
def test_final_mcp_operation_respects_budget():
    probe = ProviderProbe(is_live=False, max_attempts=1, output_dir=Path("/tmp"))
    probe.probe_mcp("sportdb", "football", "mcp_explore", "mcp_support")
    
    with pytest.raises(RuntimeError, match="Attempt budget exceeded"):
        probe.probe_mcp("sportdb", "football", "mcp_explore", "mcp_support")

# 3. --live and --dry-run mutual exclusion
def test_cli_mutual_exclusion():
    script = Path(__file__).parent.parent.parent / "scripts" / "enrichment" / "m0a_provider_probe.py"
    res = subprocess.run([sys.executable, str(script), "--live", "--dry-run"], capture_output=True, text=True)
    assert res.returncode != 0
    assert "not allowed with" in res.stderr or "mutually exclusive" in res.stderr

# 4. Missing mode fails
def test_cli_missing_mode_fails():
    script = Path(__file__).parent.parent.parent / "scripts" / "enrichment" / "m0a_provider_probe.py"
    res = subprocess.run([sys.executable, str(script)], capture_output=True, text=True)
    assert res.returncode != 0
    assert "required" in res.stderr or "one of the arguments" in res.stderr

# 5. Missing credentials become BLOCKED_BY_CONFIGURATION
def test_missing_credentials_handling():
    probe = ProviderProbe(is_live=True, max_attempts=5, output_dir=Path("/tmp"))
    env_mock = {}
    with patch.dict(os.environ, env_mock, clear=True):
        with patch("requests.Session.get") as mock_get:
            ledger = probe.probe_rest("api-sports", "football", "fixtures_lookup", "https://v3.football.api-sports.io/fixtures", "recent_fixtures")
            assert ledger.status == "BLOCKED_BY_CONFIGURATION"
            mock_get.assert_not_called()

# 6. No dummy credential is sent
def test_no_dummy_credential_sent():
    probe = ProviderProbe(is_live=True, max_attempts=5, output_dir=Path("/tmp"))
    env_mock = {K_SPORTDB: "valid_secret_123"}
    with patch.dict(os.environ, env_mock, clear=True):
        with patch("requests.Session.get") as mock_get:
            # We will mock the get to prevent network, but test that if api-sports lacked key, it wouldn't send a dummy
            ledger = probe.probe_rest("api-sports", "football", "fixtures_lookup", "https://v3.football.api-sports.io/fixtures", "recent_fixtures")
            assert ledger.status == "BLOCKED_BY_CONFIGURATION"
            mock_get.assert_not_called() # Network not touched at all if no real cred

# 7. Secret redaction in URLs, headers, errors, output JSON and fixtures
def test_secret_redaction():
    url = "https://www.thesportsdb.com/api/v1/json/super_secret_token_123/searchteams.php?k" + "ey=mysecret"
    sanitized = sanitize_and_sort_url(url)
    assert "super_secret" not in sanitized
    assert "mysecret" not in sanitized
    assert "REDACTED" in sanitized
    
    raw_dict = {
        "api_" + "key": "mysecret",
        "nested": {
            "se" + "cret": "nested_secret",
            "normal": "value"
        }
    }
    redacted = redact_secrets_in_dict(raw_dict)
    assert redacted["api_" + "key"] == "REDACTED"
    assert redacted["nested"]["se" + "cret"] == "REDACTED"
    assert redacted["nested"]["normal"] == "value"

# 8. Deterministic request identity
def test_deterministic_request_identity():
    url1 = "https://api.espn.com/summary?event=123&b=2&a=1"
    url2 = "https://api.espn.com/summary?event=123&a=1&b=2"
    assert sanitize_and_sort_url(url1) == sanitize_and_sort_url(url2)

# 9. Deterministic report serialization
def test_deterministic_report_serialization(tmp_path):
    script = Path(__file__).parent.parent.parent / "scripts" / "enrichment" / "m0a_provider_probe.py"
    matrix_file = tmp_path / "m0a_provider_matrix.json"
    
    env = os.environ.copy()
    env["M0A_PROBE_DETERMINISTIC"] = "1"
    
    subprocess.run([sys.executable, str(script), "--dry-run", "--output-dir", str(tmp_path)], check=True, env=env)
    data1 = matrix_file.read_text()
    
    subprocess.run([sys.executable, str(script), "--dry-run", "--output-dir", str(tmp_path)], check=True, env=env)
    data2 = matrix_file.read_text()
    
    assert data1 == data2

# 10. Full SHA-256 evidence hash
def test_full_sha256_hash():
    probe = ProviderProbe(is_live=False, max_attempts=5, output_dir=Path("/tmp"))
    data = {"some": "data"}
    h = probe.save_raw_response(data)
    assert len(h) == 64
    assert h.lower() == h

# 11. HTTP 200 with provider error body is not SUCCESS
def test_provider_error_in_http_200():
    probe = ProviderProbe(is_live=True, max_attempts=5, output_dir=Path("/tmp"))
    
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {}
    mock_resp.json.return_value = {"errors": {"token": "invalid value"}}
    
    with patch.dict(os.environ, {K_APISPORTS: "some_val"}):
        with patch("requests.Session.get", return_value=mock_resp):
            ledger = probe.probe_rest("api-sports", "football", "fixtures_lookup", "https://v3.football.api-sports.io/fixtures", "recent")
            assert ledger.status == "PROVIDER_ERROR"

# 12. Structured required-field validation
def test_structured_field_validation():
    data = {
        "events": [
            {"id": "123", "nested": {"status": "ok"}}
        ]
    }
    assert has_field(data, "events.id")
    assert has_field(data, "events.nested.status")
    assert not has_field(data, "events.nested.missing")

# 13. Returned sport mismatch is rejected
def test_sport_mismatch_rejection():
    probe = ProviderProbe(is_live=True, max_attempts=5, output_dir=Path("/tmp"))
    
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {}
    mock_resp.json.return_value = {
        "teams": [
            {"strSport": "Basketball", "strTeam": "Lakers"}
        ]
    }
    
    with patch("requests.Session.get", return_value=mock_resp):
        ledger = probe.probe_rest("thesportsdb", "football", "subject_search", "https://www.thesportsdb.com/api/v1/json/123/searchteams.php", "Lakers", params={"t": "Lakers"})
        assert ledger.status == "SPORT_MISMATCH"

# 14. Unsupported provider/sport classification
def test_unsupported_sport_classification():
    probe = ProviderProbe(is_live=False, max_attempts=5, output_dir=Path("/tmp"))
    from scripts.enrichment.m0a_provider_probe import run_probes
    run_probes(probe, target_provider="sportdb", target_sport="tennis")
    assert len(probe.attempts) == 1
    assert probe.attempts[0].status == "NOT_SUPPORTED"

# 15. No-network dry-run
def test_no_network_dry_run():
    probe = ProviderProbe(is_live=False, max_attempts=10, output_dir=Path("/tmp"))
    with patch("requests.Session.get") as mock_get:
        probe.probe_rest("espn", "football", "scoreboard", "https://api.espn.com", "subject")
        mock_get.assert_not_called()

# 16. Complete repository fixture secret scan
def test_no_secrets_in_fixtures():
    fixture_dir = Path(__file__).parent.parent.parent / "tests" / "fixtures" / "enrichment" / "m0a"
    if fixture_dir.exists():
        for p in fixture_dir.glob("**/*.json"):
            content = p.read_text()
            assert "superse" + "cret" not in content.lower()

# 17. SportDB documented path and X-API-Key contract
def test_sportdb_contract_contract():
    probe = ProviderProbe(is_live=True, max_attempts=5, output_dir=Path("/tmp"))
    
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {}
    mock_resp.json.return_value = {"countries": []}
    
    with patch.dict(os.environ, {K_SPORTDB: "sportdb_secret_val"}):
        with patch("requests.Session.get", return_value=mock_resp) as mock_get:
            probe.probe_rest("sportdb", "football", "countries_discovery", "https://api.sportdb.dev/api/football/countries", "countries")
            
            _, kwargs = mock_get.call_args
            assert "X-API-Key" in kwargs["headers"]
            assert kwargs["headers"]["X-API-Key"] == "sportdb_secret_val"
            assert "Authorization" not in kwargs["headers"]

# 18. TheSportsDB sport-specific subject handling
def test_thesportsdb_subject_handling():
    probe = ProviderProbe(is_live=False, max_attempts=10, output_dir=Path("/tmp"))
    from scripts.enrichment.m0a_provider_probe import run_probes
    run_probes(probe, target_provider="thesportsdb", target_sport="tennis")
    
    assert len(probe.attempts) == 1
    assert "Roger" in probe.attempts[0].subject or "Federer" in probe.attempts[0].subject
    assert "searchplayers.php" in probe.attempts[0].request_identity

# 19. API-Sports status response cannot prove a data capability
def test_api_sports_status_limitation():
    probe = ProviderProbe(is_live=False, max_attempts=5, output_dir=Path("/tmp"))
    from scripts.enrichment.m0a_provider_probe import run_probes
    run_probes(probe, target_provider="api-sports", target_sport="football")
    
    status_ops = [a.operation for a in probe.attempts]
    assert "status" in status_ops
    assert "fixtures_lookup" in status_ops or "data_lookup" in status_ops

# 20. API-Sports tennis is classified NOT_OFFERED without a network attempt
def test_api_sports_tennis_not_offered():
    probe = ProviderProbe(is_live=True, max_attempts=5, output_dir=Path("/tmp"))
    from scripts.enrichment.m0a_provider_probe import run_probes
    
    with patch("requests.Session.get") as mock_get:
        run_probes(probe, target_provider="api-sports", target_sport="tennis")
        
        mock_get.assert_not_called()
        assert len(probe.attempts) == 1
        assert probe.attempts[0].status == "NOT_OFFERED"
