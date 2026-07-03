from __future__ import annotations

from bet.pipeline.market_family_quality import build_market_reference, normalize_market_family


def test_volleyball_market_rows_can_promote_candidates() -> None:
    event = {
        "sport": "volleyball",
        "home_team": "Poland",
        "away_team": "Italy",
    }
    row = {
        "market_type": "h2h",
        "selection": "home",
        "row_id": "row_volleyball_1",
    }
    family = normalize_market_family("volleyball", row)
    assert family == "result"
    
    ref = build_market_reference(event, row)
    assert ref is not None
    assert ref.market_family == "result"
    assert ref.human_searchable_market_name == "Match winner - Poland"
