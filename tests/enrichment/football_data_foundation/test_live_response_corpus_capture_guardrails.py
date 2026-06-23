import ast
import json
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
            pytest.fail(f"Failed to parse JSON file {p}: {e}")
