from __future__ import annotations

from bet.pipeline.sport_promotion_obligations import audit_sport_promotion_obligations


def test_football_is_promotable_by_default() -> None:
    result = audit_sport_promotion_obligations(
        events_by_sport={"football": 1},
        market_rows_by_sport={"football": 10},
        candidates_by_sport={"football": 1},
        quote_cards_by_sport={"football": 1},
    )
    assert result.ok
    assert result.status == "PASS"


def test_tennis_minimum_obligations() -> None:
    # If tennis market_rows >= 100 and Wimbledon market_rows >= 50, but candidates are below minimum of 10
    result = audit_sport_promotion_obligations(
        events_by_sport={"tennis": 1, "football": 1},
        market_rows_by_sport={"tennis": 101, "football": 10},
        candidates_by_sport={"tennis": 5, "football": 10},
        quote_cards_by_sport={"tennis": 5, "football": 10},
        wimbledon_market_rows=55,
    )
    assert not result.ok
    assert result.status == "BLOCK"
    assert "tennis has 101 market rows" in result.errors[0]
