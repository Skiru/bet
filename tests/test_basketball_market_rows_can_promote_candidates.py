from __future__ import annotations

from bet.pipeline.market_family_quality import build_market_reference, normalize_market_family


def test_basketball_market_rows_can_promote_candidates() -> None:
    event = {
        "sport": "basketball",
        "home_team": "Warriors",
        "away_team": "Nets",
    }
    row = {
        "market_type": "spread",
        "selection": "away",
        "line": 4.5,
        "row_id": "row_basketball_1",
    }
    family = normalize_market_family("basketball", row)
    assert family == "spread"
    
    ref = build_market_reference(event, row)
    assert ref is not None
    assert ref.market_family == "spread"
    assert ref.line == 4.5
