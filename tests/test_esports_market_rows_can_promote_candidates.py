from __future__ import annotations

from bet.pipeline.market_family_quality import build_market_reference, normalize_market_family


def test_esports_market_rows_can_promote_candidates() -> None:
    event = {
        "sport": "cs2",
        "home_team": "FaZe",
        "away_team": "NaVi",
    }
    row = {
        "market_type": "h2h",
        "selection": "home",
        "row_id": "row_esports_1",
    }
    ref = build_market_reference(event, row)
    assert ref is not None
    assert ref.market_family == "result"
    assert ref.line_free_market_type == "MATCH_WINNER"
