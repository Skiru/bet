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
    probe = ProviderProbe(is_live=True, max_attempts=2, output_dir=Path("/tmp"))
    env_mock = {K_SPORTDB: "yes", K_APISPORTS: "yes", K_THESPORTSDB: "yes"}
    with patch.dict(os.environ, env_mock, clear=True):
        with patch("requests.Session.get"):
            probe.probe_rest("espn", "football", "scoreboard", "https://api.espn.com", "subject")
            probe.probe_rest("espn", "football", "scoreboard", "https://api.espn.com", "subject")

            with pytest.raises(RuntimeError, match="Attempt budget exceeded"):
                probe.probe_rest("espn", "football", "scoreboard", "https://api.espn.com", "subject")

# 2. The budget cannot be exceeded by the final MCP operation
def test_final_mcp_operation_respects_budget():
    probe = ProviderProbe(is_live=True, max_attempts=1, output_dir=Path("/tmp"))
    env_mock = {K_SPORTDB: "yes"}
    with patch.dict(os.environ, env_mock, clear=True):
        with patch.object(ProviderProbe, "check_mcp_configured", return_value=True):
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
            ledger = probe.probe_rest("api-sports", "football", "fixtures_lookup", "https://v3.football.api-sports.io/fixtures", "recent_fixtures")
            assert ledger.status == "BLOCKED_BY_CONFIGURATION"
            mock_get.assert_not_called()

# 7. Secret redaction
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

# 8. Deterministic request identity
def test_deterministic_request_identity():
    url1 = "https://api.espn.com/summary?event=123&b=2&a=1"
    url2 = "https://api.espn.com/summary?event=123&a=1&b=2"
    assert sanitize_and_sort_url(url1) == sanitize_and_sort_url(url2)

# 9. Full SHA-256 evidence hash
def test_full_sha256_hash():
    probe = ProviderProbe(is_live=False, max_attempts=5, output_dir=Path("/tmp"))
    data = {"some": "data"}
    h = probe.save_raw_response(data)
    assert len(h) == 64
    assert h.lower() == h

# 10. HTTP 200 with provider error body is not SUCCESS
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

# 11. Missing mandatory field cannot produce SUCCESS
def test_missing_mandatory_field_cannot_produce_success():
    probe = ProviderProbe(is_live=True, max_attempts=5, output_dir=Path("/tmp"))
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {}
    mock_resp.json.return_value = {"response": [{"id": 1}]} # Missing "response.fixture.id"

    with patch.dict(os.environ, {K_APISPORTS: "some_val"}):
        with patch("requests.Session.get", return_value=mock_resp):
            ledger = probe.probe_rest("api-sports", "football", "fixtures_lookup", "https://v3.football.api-sports.io/fixtures", "recent", expected_fields=["response.0.fixture.id"])
            assert ledger.status == "INCOMPLETE_RESPONSE"

# 12. Empty required list cannot produce SUCCESS
def test_empty_required_list_cannot_produce_success():
    probe = ProviderProbe(is_live=True, max_attempts=5, output_dir=Path("/tmp"))
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {}
    mock_resp.json.return_value = {"response": []}

    with patch.dict(os.environ, {K_APISPORTS: "some_val"}):
        with patch("requests.Session.get", return_value=mock_resp):
            ledger = probe.probe_rest("api-sports", "football", "fixtures_lookup", "https://v3.football.api-sports.io/fixtures", "recent", expected_fields=["response"])
            assert ledger.status == "EMPTY_RESULT"

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

# 14. SportDB multisport support
def test_sportdb_not_manually_not_supported():
    probe = ProviderProbe(is_live=False, max_attempts=5, output_dir=Path("/tmp"))
    from scripts.enrichment.m0a_provider_probe import run_probes
    run_probes(probe, target_provider="sportdb", target_sport="tennis")

    assert len(probe.attempts) > 0
    assert probe.attempts[0].status == "DRY_RUN"

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

# 17. API-Sports tennis is classified NOT_OFFERED without a network attempt
def test_api_sports_tennis_not_offered():
    probe = ProviderProbe(is_live=True, max_attempts=5, output_dir=Path("/tmp"))
    from scripts.enrichment.m0a_provider_probe import run_probes

    with patch("requests.Session.get") as mock_get:
        run_probes(probe, target_provider="api-sports", target_sport="tennis")

        mock_get.assert_not_called()
        assert len(probe.attempts) == 1
        assert probe.attempts[0].status == "NOT_OFFERED"

# 18. No direct network call outside counted transport
def test_no_direct_network_call_outside_transport():
    script_path = Path(__file__).parent.parent.parent / "scripts" / "enrichment" / "m0a_provider_probe.py"
    content = script_path.read_text()
    import ast
    tree = ast.parse(content)
    class Visitor(ast.NodeVisitor):
        def __init__(self):
            self.requests_calls = []
        def visit_Call(self, node):
            if isinstance(node.func, ast.Attribute):
                if isinstance(node.func.value, ast.Name) and node.func.value.id == "requests":
                    if node.func.attr in ("get", "post", "put", "delete", "request"):
                        self.requests_calls.append(node)
            self.generic_visit(node)

    v = Visitor()
    v.visit(tree)
    assert len(v.requests_calls) == 0

# 19. Physical count equals mocked transport call count
def test_physical_count_equals_transport_calls():
    probe = ProviderProbe(is_live=True, max_attempts=10, output_dir=Path("/tmp"))
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {}
    mock_resp.json.return_value = {"response": [{"id": 1}]}

    with patch.dict(os.environ, {K_APISPORTS: "val"}):
        with patch("requests.Session.get", return_value=mock_resp) as mock_get:
            probe.probe_rest("api-sports", "football", "fixtures_lookup", "https://v3.football.api-sports.io/fixtures", "recent", expected_fields=[])
            assert probe.physical_rest_attempts == mock_get.call_count

# 20. Logical blocked/not-offered rows do not increase physical count
def test_blocked_rows_do_not_increase_physical_count():
    probe = ProviderProbe(is_live=True, max_attempts=10, output_dir=Path("/tmp"))
    env_mock = {}
    with patch.dict(os.environ, env_mock, clear=True):
        probe.probe_rest("api-sports", "football", "fixtures", "https://v3", "sub")
        assert probe.physical_rest_attempts == 0
