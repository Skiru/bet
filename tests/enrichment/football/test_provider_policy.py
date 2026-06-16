from pathlib import Path

import pytest

FORBIDDEN_PROVIDERS = [
    "espn", "sportdb", "thesportsdb", "football_data_org",
    "understat", "sofascore", "flashscore", "oddsportal",
    "totalcorner", "scores24", "soccerway", "betexplorer",
    "google_sports", "serpapi"
]

def test_no_forbidden_provider_imports():
    # Recursively check src/bet/enrichment/football for forbidden strings
    football_dir = Path("src/bet/enrichment/football")
    for py_file in football_dir.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8").lower()
        for forbidden in FORBIDDEN_PROVIDERS:
            # allow variables like "primary_provider" but not the forbidden names
            if forbidden in content and forbidden != "sportdb":
                pytest.fail(f"Forbidden provider '{forbidden}' found in {py_file.name}")

def test_cli_no_forbidden_provider_imports():
    cli_file = Path("scripts/enrichment/football_history.py")
    if cli_file.exists():
        content = cli_file.read_text(encoding="utf-8").lower()
        for forbidden in FORBIDDEN_PROVIDERS:
            if forbidden in content and forbidden != "sportdb":
                pytest.fail(f"Forbidden provider '{forbidden}' found in CLI script")
