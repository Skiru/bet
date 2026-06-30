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


def test_market_semantics_extracted_from_h2h_result():
    markets = matrix_mod.extract_markets_from_odds_api(
        {
            "home_team": "Alpha",
            "away_team": "Beta",
            "bookmakers": [
                {
                    "title": "bet365",
                    "markets": [
                        {
                            "key": "h2h",
                            "outcomes": [
                                {"name": "Alpha", "price": 1.8},
                                {"name": "Beta", "price": 2.1},
                            ],
                        }
                    ],
                }
            ],
        }
    )

    assert markets[0]["market_family"] == "RESULT"
    assert markets[0]["provider_market_key"] == "h2h"
    assert markets[0]["mapping_status"] == ""


def test_market_semantics_extracted_from_totals_with_line_direction():
    markets = matrix_mod.extract_markets_from_odds_api(
        {
            "home_team": "Alpha",
            "away_team": "Beta",
            "bookmakers": [
                {
                    "title": "bet365",
                    "markets": [
                        {
                            "key": "totals",
                            "point": 2.5,
                            "outcomes": [
                                {"name": "Over", "price": 1.91},
                                {"name": "Under", "price": 1.95},
                            ],
                        }
                    ],
                }
            ],
        }
    )

    over_market = next(item for item in markets if item["outcome"] == "Over")
    assert over_market["market_family"] == "GOALS_TOTALS"
    assert over_market["direction"] == "OVER"
    assert over_market["line"] == 2.5


def test_market_semantics_extracted_from_corners_with_line_direction():
    markets = matrix_mod._attach_market_semantics(
        [{"market": "Over 9.5", "market_type": "corners", "outcome": "Over", "point": 9.5, "best_odds": 1.9, "best_bookmaker": "bet365", "source": "odds-api"}],
        ["Alpha", "Beta"],
        "odds-api",
    )

    assert markets[0]["market_family"] == "CORNERS"
    assert markets[0]["direction"] == "OVER"
    assert markets[0]["line"] == 9.5


def test_market_semantics_extracted_from_cards_with_line_direction():
    markets = matrix_mod._attach_market_semantics(
        [{"market": "Over 4.5", "market_type": "bookings_totals", "outcome": "Over", "point": 4.5, "best_odds": 1.9, "best_bookmaker": "bet365", "source": "odds-api"}],
        ["Alpha", "Beta"],
        "odds-api",
    )

    assert markets[0]["market_family"] == "CARDS"
    assert markets[0]["direction"] == "OVER"
    assert markets[0]["line"] == 4.5


def test_market_semantics_extracted_from_shots_with_line_direction():
    markets = matrix_mod._attach_market_semantics(
        [{"market": "Over 24.5", "market_type": "match_shots", "outcome": "Over", "point": 24.5, "best_odds": 1.9, "best_bookmaker": "bet365", "source": "odds-api"}],
        ["Alpha", "Beta"],
        "odds-api",
    )

    assert markets[0]["market_family"] == "SHOTS"
    assert markets[0]["direction"] == "OVER"
    assert markets[0]["line"] == 24.5


def test_pipeline_runs_directory_exemption(monkeypatch, tmp_path):
    import os
    import sys
    # We can mock argparse sys.argv to test main()
    monkeypatch.setattr(sys, "argv", [
        "generate_market_matrix.py",
        "--date", "2026-06-30",
        "--output-dir", str(tmp_path / "reports/pipeline_runs/TODAY_LIVE/data"),
        "--json-only"
    ])
    # Mock environment variables
    monkeypatch.setenv("BET_PIPELINE_RUNTIME_MODE", "LIVE_SHADOW")
    
    # Mock the functions executed in main so it doesn't do real DB work or network calls
    monkeypatch.setattr(matrix_mod, "load_fixtures", lambda date: [{"some": "fixture"}])
    monkeypatch.setattr(matrix_mod, "generate_market_matrix", lambda **kwargs: {
        "date": "2026-06-30",
        "events": [{
            "sport": "football",
            "home_team": "Team A",
            "away_team": "Team B",
            "kickoff": "2026-06-30T15:00:00+00:00",
            "data_tier": 1
        }]
    })
    monkeypatch.setattr(matrix_mod, "write_matrix_json", lambda matrix, date: None)
    monkeypatch.setattr(matrix_mod, "persist_matrix_to_db", lambda matrix, date: None)
    
    # We expect main() to run without SystemExit(6) (the forbidden dir exit code)
    try:
        matrix_mod.main()
    except SystemExit as e:
        # If it exited with 0, that's fine. If 6, that's a failure.
        assert e.code == 0
