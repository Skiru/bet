from __future__ import annotations

from bet.pipeline.market_family_quality import build_market_reference, normalize_market_family


def test_hockey_market_rows_can_promote_candidates() -> None:
    event = {
        "sport": "hockey",
        "home_team": "Canada",
        "away_team": "USA",
    }
    row = {
        "market_type": "h2h",
        "selection": "home",
        "row_id": "row_hockey_1",
    }
    family = normalize_market_family("hockey", row)
    assert family == "result"
    
    ref = build_market_reference(event, row)
    assert ref is not None
    assert ref.market_family == "result"
    assert ref.human_searchable_market_name == "Moneyline - Canada"
