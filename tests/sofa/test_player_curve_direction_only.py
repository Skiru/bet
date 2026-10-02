"""A football player prop reads its own direction's curve or nothing
(2026-10-02): the combined market curve is mostly the UNDER rows the cache
replay prices, while Superbet quotes these OVER only."""

from bet.sofa.confidence import PLAYER_PROP_MARKETS, Calibration, direction_key

M = "player_shots_on_target_for"


def _cal() -> Calibration:
    combined = {"0.700-0.750": {"realised_lo95": 0.704, "n": 4000}}
    over = {"0.600-0.700": {"realised_lo95": 0.58, "n": 900}}
    pool = {"0.700-0.750": {"realised_lo95": 0.72, "n": 90000}}
    return Calibration(
        pooled=pool,
        by_market={M: combined, "corners_total": combined},
        pooled_by_sport={"football": pool},
        by_market_direction={direction_key(M, "OVER"): over,
                             direction_key("corners_total", "OVER"): over},
    )


def test_a_player_over_leg_never_reads_the_combined_curve() -> None:
    cal = _cal()
    assert cal.realised(M, 0.72, "football", "OVER") is None
    assert cal.realised(M, 0.65, "football", "OVER") == (
        0.58, f"market:{direction_key(M, 'OVER')}", 900)
    assert cal.realised(M, 0.72, "football", None) is None  # no direction at all


def test_a_team_market_still_falls_back_to_its_combined_curve() -> None:
    cal = _cal()
    hit = cal.realised("corners_total", 0.72, "football", "OVER")
    assert hit == (0.704, "market:corners_total", 4000)


def test_the_rule_covers_every_player_prop() -> None:
    assert M in PLAYER_PROP_MARKETS and len(PLAYER_PROP_MARKETS) == 7
