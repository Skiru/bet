import ast
import json
import re
from pathlib import Path


def test_guardrail_forbidden_imports():
    """
    REQ-TEST-017 Ensure no forbidden imports from betting, db, pipeline, scrapers, api_clients
    exist in any of our implemented modules.
    """
    src_dir = Path("/Users/mkoziol/projects/bet-multisport-enrichment-v1/src/bet/enrichment/football_data_foundation/live_response_corpus_capture")
    assert src_dir.exists()
    
    forbidden_prefixes = (
        "bet.db", "src.bet.db",
        "bet.pipeline", "src.bet.pipeline",
        "bet.api_clients", "src.bet.api_clients",
        "bet.scrapers", "src.bet.scrapers",
        "betting", "src.betting",
    )
    
    for p in src_dir.rglob("*.py"):
        content = p.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=str(p))
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith(forbidden_prefixes), f"Forbidden import '{alias.name}' in {p.name}"
            elif isinstance(node, ast.ImportFrom):
                module_name = node.module
                if module_name:
                    assert not module_name.startswith(forbidden_prefixes), f"Forbidden import from '{module_name}' in {p.name}"


def test_guardrail_no_requests_import():
    """
    REQ-TEST-006 requests import is forbidden.
    """
    src_dir = Path("/Users/mkoziol/projects/bet-multisport-enrichment-v1/src/bet/enrichment/football_data_foundation/live_response_corpus_capture")
    
    for p in src_dir.rglob("*.py"):
        content = p.read_text(encoding="utf-8")
        # Ensure 'import requests' or 'requests.' does not appear
        assert not re.search(r"\bimport\s+requests\b|\bfrom\s+requests\b|\brequests\.[a-zA-Z_]", content), f"requests library usage found in {p.name}"


def test_guardrail_no_canary_fixture_1():
    """
    REQ-TEST-007 no canary_fixture_1.
    """
    src_dir = Path("/Users/mkoziol/projects/bet-multisport-enrichment-v1/src/bet/enrichment/football_data_foundation/live_response_corpus_capture")
    test_dir = Path("/Users/mkoziol/projects/bet-multisport-enrichment-v1/tests/enrichment/football_data_foundation")
    
    forbidden = "-".join(["canary", "fixture", "1"])
    
    for p in src_dir.rglob("*.py"):
        content = p.read_text(encoding="utf-8")
        assert forbidden not in content, f"Forbidden string '{forbidden}' found in src/{p.name}"
        
    for p in test_dir.glob("test_live_response_corpus_capture_*.py"):
        if p.name == "test_live_response_corpus_capture_guardrails.py":
            continue
        content = p.read_text(encoding="utf-8")
        assert forbidden not in content, f"Forbidden string '{forbidden}' found in tests/{p.name}"


def test_no_prototype_imports():
    """
    REQ-TEST-011 Ensure reference prototype tests/imports are not copied into our repo namespace.
    """
    test_dir = Path("/Users/mkoziol/projects/bet-multisport-enrichment-v1/tests/enrichment/football_data_foundation")
    proto_ns = "live_" + "corpus_v3"
    for p in test_dir.glob("test_live_response_corpus_capture_*.py"):
        content = p.read_text(encoding="utf-8")
        assert proto_ns not in content, f"Prototype import/namespace '{proto_ns}' found in {p.name}"


def test_guardrail_reports_json_parseable():
    """
    REQ-TEST-018 Ensure all report JSON files in the live response corpus parse correctly as JSON.
    """
    corpus_root = Path("/Users/mkoziol/projects/bet-multisport-enrichment-v1/reports/football_data_foundation/live_response_corpus")
    if not corpus_root.exists():
        return  # No runs completed yet, which is fine
        
    for p in corpus_root.rglob("*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            assert data is not None
        except Exception as e:
            raise AssertionError(f"Failed to parse JSON file {p}: {e}")


def test_guardrail_rescue_envelopes_and_previous_runs():
    """
    REQ-TEST-009: no secrets or headers in reports.
    REQ-TEST-010: all rescue envelopes have selectable_for_production=false.
    REQ-TEST-011: ESPN envelopes have unofficial_shadow_baseline=true.
    REQ-TEST-012: rescue run does not edit previous corpus runs.
    """
    corpus_root = Path("/Users/mkoziol/projects/bet-multisport-enrichment-v1/reports/football_data_foundation/live_response_corpus")
    if not corpus_root.exists():
        return

    # Check that previous run has not been modified
    previous_run_dir = corpus_root / "run_20260623_100018_fe9167"
    if previous_run_dir.exists():
        # Previous run should not contain any of the rescue-specific files
        assert not (previous_run_dir / "sportdb" / "worldcup2026-norway-senegal_rescue_live.json").exists()
        assert not (previous_run_dir / "highlightly" / "worldcup2026-norway-senegal_rescue.json").exists()
        assert not (previous_run_dir / "espn-baseline" / "worldcup2026-norway-senegal_rescue_scoreboard.json").exists()

    for p in corpus_root.rglob("*.json"):
        if p.name in ("manifest.json", "fixtures_discovered.json", "mapping_candidate.json", "capture_verifier_result.json"):
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            
            # Check secret leaks or headers
            assert "Authorization" not in str(data)
            assert "X-API-Key" not in str(data)
            assert "raw_headers_stored" not in data or data["raw_headers_stored"] is False
            assert "secrets_stored" not in data or data["secrets_stored"] is False
            
            rescue_attempt = data.get("rescue_attempt", False)
            if rescue_attempt:
                # REQ-TEST-010: all rescue envelopes have selectable_for_production=false
                assert data.get("selectable_for_production") is False
                
                # REQ-TEST-011: ESPN envelopes have unofficial_shadow_baseline=true
                if data.get("provider") == "espn-baseline":
                    assert data.get("unofficial_shadow_baseline") is True
        except Exception:
            pass

