"""Audit 2026-10-13 B9 / C10 / C9: volleyball's set length and set markets.

The set-length table draws a set's loser points from the history; who wins each
set stays the rally simulation's, bit for bit. Both switches are off
(epochs.VB_SET_LENGTH_FROM_UTC / VB_SET_HISTORY_FROM_UTC are None: the
pre-registered threshold was not met). Evidence:
docs/sofa/evidence/volleyball_set_length_2026-10-13.md.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime

import pytest

from bet.sofa import epochs
from bet.sofa import score_model as sm
from bet.sofa import sport_confidence as scf
from bet.sofa.football_rating import RatingBook
from bet.sofa.shadow import SPORTS

VB = SPORTS["volleyball"]


def _games(n: int = 300) -> list[tuple[bool, float, list[int], list[int]]]:
    """Home wins 3-0 in 25-20 sets, the share 0.6 (favourite home)."""
    return [(False, 0.6, [25, 25, 25], [20, 20, 20]) for _ in range(n)]


def test_switches_are_off_by_default():
    assert epochs.VB_SET_LENGTH_FROM_UTC is None
    assert epochs.VB_SET_HISTORY_FROM_UTC is None
    now = datetime(2030, 1, 1, tzinfo=UTC)
    assert not epochs.vb_set_length("2030-01-01", now)
    assert not epochs.vb_set_history("2030-01-01", now)


def test_set_format_ok():
    assert sm.set_format_ok([25, 25, 25], [20, 20, 20])
    assert sm.set_format_ok([25, 23, 25, 25], [20, 25, 19, 22])
    assert not sm.set_format_ok([25, 25], [20, 20])
    assert not sm.set_format_ok([26, 25, 25], [25, 20, 20])  # 26-25 not closed


def test_table_needs_enough_sets_and_draws_the_history_loser():
    assert sm.fit_set_length(_games(10)) is None  # < 200 sets in every cell
    table = sm.fit_set_length(_games(300))
    assert table is not None
    rng = random.Random(1)
    assert table.draw(rng, False, False, True, 0.1) == 20
    # nothing for the women's cell or the deciding set
    assert table.draw(rng, True, False, True, 0.1) is None
    assert table.draw(rng, False, True, True, 0.1) is None


def test_winners_and_sets_are_bit_identical_with_the_table():
    table = sm.fit_set_length(_games(300))
    assert table is not None
    old, new = random.Random(5), random.Random(5)
    lr = random.Random("len")
    for _ in range(200):
        a = sm._volleyball(old, 24.0, 22.0)
        b = sm._volleyball(new, 24.0, 22.0, 0.0, 0.0, 0.0, table, False, lr)
        assert a.winner == b.winner
        assert [x > y for x, y in zip(a.t1_periods, a.t2_periods, strict=True)] \
            == [x > y for x, y in zip(b.t1_periods, b.t2_periods, strict=True)]


def test_no_table_is_the_old_simulation():
    m = sm.ScoreModel(VB, RatingBook(), 6.0)
    a = m.simulate([24.0], [22.0], seed=3, n=20)
    b = sm.ScoreModel(VB, RatingBook(), 6.0, set_length=None).simulate(
        [24.0], [22.0], seed=3, n=20, women=True)
    assert [g.t1_periods for g in a] == [g.t1_periods for g in b]


def test_set_markets_leave_settled_only_only_with_the_history_switch():
    base = scf.settled_only_families("volleyball")
    c9 = scf.settled_only_families("volleyball", True)
    assert c9 < base
    assert scf.SETTLED_ONLY_FAMILIES["volleyball"] == base
    assert scf.history_markets("volleyball", True)[-4:] == scf.VB_SET_MARKETS
    assert scf.history_markets("volleyball") == scf.HISTORY_MARKETS["volleyball"]
    assert scf.history_markets("hockey", True) == scf.HISTORY_MARKETS["hockey"]


def test_set_periods_only_with_the_history_switch():
    assert scf.market_periods(VB, 744) == ()
    assert scf.market_periods(VB, 744, True) == (1, 2, 3, 4, 5)
    assert scf.market_periods(VB, 230060, True) == (0,)


@pytest.mark.parametrize("women", [False, True])
def test_women_of_unknown_is_false(women):
    m = sm.ScoreModel(VB, RatingBook(), 6.0)
    assert m.women_of(1, 2) is False
    m.team_women = {1: women, 2: women}
    assert m.women_of(1, 2) is women
