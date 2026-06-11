"""Tests for market matrix sport normalization and persistence helpers."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import generate_market_matrix as matrix_mod


def test_sport_aliases_are_canonicalized():
    assert matrix_mod.canonicalize_sport_name("Counter-Strike 2") == "cs2"
    assert matrix_mod.canonicalize_sport_name("Dota 2") == "dota2"
    assert matrix_mod.canonicalize_sport_name("Volleyball") == "volleyball"


def test_odds_keys_map_esports_to_supported_sports():
    assert matrix_mod._sport_from_odds_key("esports_counterstrike", "") == "cs2"
    assert matrix_mod._sport_from_odds_key("", "Esports World Cup - Dota 2") == "dota2"
    assert matrix_mod._sport_from_odds_key("esports_valorant", "") == "valorant"


def test_generate_market_matrix_keeps_noncanonical_esports_fixture(monkeypatch):
    monkeypatch.setattr(matrix_mod, "load_fixtures", lambda date: [{
        "sport": "Counter-Strike 2",
        "home_team": "Team A",
        "away_team": "Team B",
        "competition": "Intel Extreme Masters Cologne",
        "kickoff": "2099-01-01T18:00:00+00:00",
        "source": "seed",
    }])
    monkeypatch.setattr(matrix_mod, "load_espn_odds_snapshot", lambda date: {})
    monkeypatch.setattr(matrix_mod, "load_odds_api_snapshot", lambda date: {})
    monkeypatch.setattr(matrix_mod, "load_scan_summary", lambda date: {})
    monkeypatch.setattr(matrix_mod, "load_multi_source_odds", lambda: {})
    monkeypatch.setattr(matrix_mod, "load_picks_suggested", lambda: {})
    monkeypatch.setattr(matrix_mod, "load_analysis_pool", lambda date: {})
    monkeypatch.setattr(matrix_mod, "try_safety_analysis", lambda sport, home, away, competition: None)

    matrix = matrix_mod.generate_market_matrix("2099-01-01")

    assert matrix["total_events_in_matrix"] == 1
    assert matrix["events"][0]["sport"] == "cs2"
    assert matrix["sport_breakdown"] == {"cs2": 1}
