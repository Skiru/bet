from __future__ import annotations

from bet.pipeline.multisport_market_promotion import map_multisport_market, normalize_selection_name


def test_tennis_h2h_mapping() -> None:
    event = {
        "sport": "tennis",
        "home_team": "Roger Federer",
        "away_team": "Rafael Nadal",
        "canonical_event_name": "Federer vs Nadal"
    }
    row = {
        "market_type": "h2h",
        "selection": "home",
        "row_id": "row_1",
    }
    mapped = map_multisport_market("tennis", row, event)
    assert mapped is not None
    assert mapped["market_family"] == "result"
    assert mapped["human_searchable_market_name"] == "Match winner - Roger Federer"
    assert mapped["line_semantics"] == "LINE_FREE"
    assert mapped["line_free_market_type"] == "MATCH_WINNER"


def test_basketball_spread_mapping() -> None:
    event = {
        "sport": "basketball",
        "home_team": "Lakers",
        "away_team": "Celtics",
    }
    row = {
        "market_type": "spread",
        "selection": "home",
        "line": -5.5,
        "row_id": "row_2",
    }
    mapped = map_multisport_market("basketball", row, event)
    assert mapped is not None
    assert mapped["market_family"] == "spread"
    assert "Spread - Lakers -5.5" in mapped["human_searchable_market_name"]
    assert mapped["line_semantics"] == "NUMERIC_LINE_REQUIRED"
