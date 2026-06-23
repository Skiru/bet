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
