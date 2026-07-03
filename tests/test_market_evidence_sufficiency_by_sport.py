from __future__ import annotations

from bet.pipeline.market_evidence_sufficiency import evaluate_evidence_sufficiency


def test_tennis_match_winner_evidence_sufficiency() -> None:
    event = {
        "sport": "tennis",
        "home_team": "Alcaraz",
        "away_team": "Djokovic",
        "competition": "Wimbledon",
    }
    row = {
        "row_id": "row_1",
        "market_family": "result",
    }
    pack = {
        "player_ranking": "Top 10",
        "recent_form": "Excellent",
        "surface": "Grass",
    }
    grade, blockers = evaluate_evidence_sufficiency("tennis", "result", event, row, pack)
    assert grade == "HIGH"
    assert not blockers


def test_tennis_handicap_requires_line() -> None:
    event = {
        "sport": "tennis",
        "home_team": "Alcaraz",
        "away_team": "Djokovic",
        "competition": "Wimbledon",
    }
    row = {
        "row_id": "row_1",
        "market_family": "game_handicap",
        "line": "UNKNOWN",
    }
    grade, blockers = evaluate_evidence_sufficiency("tennis", "game_handicap", event, row)
    assert grade == "UNKNOWN"
    assert "LINE_SEMANTICS_MISSING" in blockers
