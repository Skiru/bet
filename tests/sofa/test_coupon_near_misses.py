"""The "closest refused" section of the coupon report (F52).

A coupon that lists only what it took cannot answer the question the operator
asks the morning after: why was *that* row not on it. On 2026-09-18 the answer
for eight short-priced legs was buried in 9,462 sheet rows, every one of them
saying the same two words — BELOW_BAR — whether it had missed by 0.1% or could
not have qualified at any sample size.
"""

from datetime import UTC, datetime

from bet.sofa.contracts import Coupon, SheetRow
from bet.sofa.coupon import CouponResult
from scripts.sofa.run_coupon import _near_miss_section


def _row(**over):
    base = dict(
        sofascore_event_id=1,
        sport="football",
        market="corners_total",
        subject="",
        line=9.5,
        direction="OVER",
        sample_size=10,
        sample_mean=10.0,
        sample_sd=2.0,
        centre=10.0,
        p_central=0.6,
        market_p=0.55,
        ladder_centre=9.4,
        ladder_sigma=0.3,
        p_bar=0.58,
        bar_reason="none",
        required_odds=1.90,
        offered_odds=1.88,
        edge=0.05,
        surplus=-0.02,
        verdict="BELOW_BAR",
        notes=[],
    )
    base.update(over)
    return SheetRow(**base)


def _result():
    return CouponResult(
        coupon=Coupon(
            created_at_utc=datetime(2026, 9, 18, 18, 35, tzinfo=UTC), singles=[]
        ),
        dropped=[],
    )


def test_a_row_that_missed_narrowly_is_listed():
    out = "\n".join(_near_miss_section(_result(), [_row()]))
    assert "Najbliżej poprzeczki" in out
    assert "corners_total" in out
    assert "-0.020" in out


def test_an_unreachable_row_is_not_listed_as_a_near_miss():
    """It did not come close; it could not have. Listing it would be the same
    conflation the section exists to undo."""
    row = _row(
        offered_odds=1.07,
        required_odds=1.25,
        surplus=-0.18,
        notes=["UNREACHABLE_BAR: no sample could clear this price"],
    )
    assert _near_miss_section(_result(), [row]) == []


def test_only_below_bar_rows_appear():
    for verdict in ("VALUE", "LEAN", "NO_PRICE"):
        assert _near_miss_section(_result(), [_row(verdict=verdict)]) == []


def test_ranking_is_relative_so_a_long_shot_does_not_win_on_scale():
    """Absolute surplus carries a 1/p term; ranking on it makes this a
    long-shot list, which is the defect the coupon's own sort already fixed."""
    short = _row(
        sofascore_event_id=1, required_odds=1.50, offered_odds=1.47, surplus=-0.03
    )
    longshot = _row(
        sofascore_event_id=2, required_odds=12.00, offered_odds=11.90, surplus=-0.10
    )
    out = "\n".join(_near_miss_section(_result(), [longshot, short]))
    # -0.03/1.50 = -0.020 beats -0.10/12.00 = -0.008? No: -0.008 > -0.020.
    # The long shot is genuinely closer *relatively*, and must be shown first.
    assert out.index("| 2 |") < out.index("| 1 |")

    # Now make the short row relatively closer and the order must flip.
    short_closer = _row(
        sofascore_event_id=1, required_odds=1.50, offered_odds=1.499, surplus=-0.001
    )
    out = "\n".join(_near_miss_section(_result(), [longshot, short_closer]))
    assert out.index("| 1 |") < out.index("| 2 |")


def test_a_row_already_on_the_coupon_is_not_repeated():
    from bet.sofa.contracts import CouponRow

    taken = CouponRow(
        sofascore_event_id=1,
        match_name="Home - Away",
        kickoff_utc=datetime(2026, 9, 18, 19, 0, tzinfo=UTC),
        sport="football",
        market="corners_total",
        subject="",
        line=9.5,
        direction="OVER",
        sample_size=10,
        centre=10.0,
        p_central=0.6,
        market_p=0.55,
        p_bar=0.58,
        offered_odds=1.88,
        required_odds=1.90,
        edge=0.05,
        surplus=-0.02,
    )
    result = CouponResult(
        coupon=Coupon(
            created_at_utc=datetime(2026, 9, 18, 18, 35, tzinfo=UTC), singles=[taken]
        ),
        dropped=[],
    )
    assert _near_miss_section(result, [_row()]) == []


def test_each_sport_gets_its_own_table():
    out = "\n".join(
        _near_miss_section(
            _result(),
            [_row(), _row(sofascore_event_id=2, sport="tennis", market="games_total")],
        )
    )
    assert "### football" in out
    assert "### tennis" in out


def test_a_row_with_no_price_cannot_be_a_near_miss():
    assert _near_miss_section(_result(), [_row(offered_odds=None)]) == []
    assert _near_miss_section(_result(), [_row(surplus=None)]) == []


def test_nothing_is_emitted_when_there_is_nothing_to_say():
    assert _near_miss_section(_result(), []) == []
