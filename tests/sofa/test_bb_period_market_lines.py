"""epochs.BB_PERIOD_MARKET_LINES (study 2026-11-05): basketball's period
families (h1 / h2 / quarter total, handicap, team totals) fitted on lines
placed where the market stood - the historical game's Sofascore total and
spread divided by the period count, +-0 / 1 / 2 points
(sport_confidence.period_position_lines) - instead of the model's own
quantiles. Off (or without market lines): the rows are exactly as before."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from bet.sofa import epochs
from bet.sofa import sport_confidence as scf
from bet.sofa.market_lines import MarketLines
from tests.sofa.test_audit_2026_10_13_a7 import BASKETBALL, DAY, _history, _market

PERIOD_FAMILIES = {"h1_total", "h1_handicap", "h1_team_total", "h2_total",
                   "h2_handicap", "h2_team_total", "quarter_total",
                   "quarter_handicap", "quarter_team_total"}


def _rows(market: dict[int, MarketLines] | None, period: bool,
          max_games: int | None = 10) -> list[scf.Row]:
    return scf.walk_forward_rows(_history(), BASKETBALL, 40 * DAY, 60 * DAY, 30,
                                 max_games, "t", market_lines=market,
                                 period_market_lines=period)


def test_the_switch_is_on_from_11_06() -> None:
    assert epochs.BB_PERIOD_MARKET_LINES_FROM_UTC == datetime(2026, 11, 6, tzinfo=UTC)
    assert not epochs.bb_period_market_lines(
        "2026-11-05", datetime(2026, 11, 5, 23, tzinfo=UTC))
    assert epochs.bb_period_market_lines(
        "2026-11-06", datetime(2026, 11, 6, tzinfo=UTC))


def test_the_ladder_sits_around_the_half_point_line() -> None:
    assert scf._period_ladder(5.5) == [3.5, 4.5, 5.5, 6.5, 7.5]
    assert scf._period_ladder(5.0) == [2.5, 3.5, 4.5, 5.5, 6.5, 7.5]
    assert scf._period_ladder(-3.25) == [-5.5, -4.5, -3.5, -2.5, -1.5, -0.5]


def test_period_lines_divide_the_game_lines() -> None:
    ml = MarketLines(1, (220.5,), (-6.5,))
    q_total = scf.period_position_lines(BASKETBALL, 788, ml)
    # 220.5 / 4 = 55.125 -> 54.5 / 55.5 +- 2, in each of the four quarters
    assert {ln.period for ln in q_total} == {1, 2, 3, 4}
    assert sorted({ln.line for ln in q_total}) == [52.5, 53.5, 54.5, 55.5, 56.5, 57.5]
    assert {ln.side for ln in q_total} == {"OVER", "UNDER"}
    h1_hcp = scf.period_position_lines(BASKETBALL, 773, ml)
    assert {ln.period for ln in h1_hcp} == {0}
    assert sorted({ln.line for ln in h1_hcp}) == [-5.5, -4.5, -3.5, -2.5, -1.5, -0.5]
    # the home side's quarter points: (220.5 + 6.5) / 2 / 4 = 28.375
    q_t1 = scf.period_position_lines(BASKETBALL, 200802, ml)
    assert {ln.subject for ln in q_t1} == {"T1"}
    assert sorted({ln.line for ln in q_t1}) == [25.5, 26.5, 27.5, 28.5, 29.5, 30.5]
    # a game with no spread (or no total) gives none; a full-game market none
    no_spread = MarketLines(1, (220.5,), ())
    assert scf.period_position_lines(BASKETBALL, 788, no_spread) == []
    assert scf.period_position_lines(BASKETBALL, 753, ml) == []


def test_off_the_rows_are_identical() -> None:
    assert _rows(_market(), False) == _rows(_market(), False)
    a = scf.walk_forward_rows(_history(), BASKETBALL, 40 * DAY, 60 * DAY, 30,
                              10, "t", market_lines=_market())
    assert a == _rows(_market(), False) and a
    # without market lines the flag changes nothing either
    assert _rows(None, True) == _rows(None, False)


def test_on_only_the_period_families_move() -> None:
    off = _rows(_market(), False)
    on = _rows(_market(), True)
    assert ([r for r in off if r["family"] not in PERIOD_FAMILIES]
            == [r for r in on if r["family"] not in PERIOD_FAMILIES])
    moved = [r for r in on if r["family"] in PERIOD_FAMILIES]
    assert moved and all(r["line_source"] == "market" for r in moved)
    # (150.5, -2.5): a quarter total ~37.6, a half total ~75.3
    assert ({r["line"] for r in moved if r["family"] == "quarter_total"}
            == {35.5, 36.5, 37.5, 38.5, 39.5, 40.5})
    assert ({r["line"] for r in moved if r["family"] == "h1_total"}
            == {72.5, 73.5, 74.5, 75.5, 76.5, 77.5})
    quarters = {r["period"] for r in moved if r["family"] == "quarter_total"}
    assert quarters == {1, 2, 3, 4}
    # every window game with market lines is scored, as the full-game families
    assert ({r["game"] for r in moved if r["family"] == "quarter_total"}
            == {f"h:{eid}" for eid in _market()})


@pytest.mark.parametrize("sport", ["hockey", "volleyball"])
def test_no_other_sport_has_period_market_lines(sport: str) -> None:
    assert sport not in scf.PERIOD_MARKET_LINE_MARKETS
