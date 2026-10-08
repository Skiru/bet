"""A leg of a lineless market (winner / moneyline) keys without crashing."""

from __future__ import annotations

from bet.sofa.settle import line_value
from scripts.sofa import audit_trend, run_boosts


def test_line_value_none_is_zero() -> None:
    assert line_value({"line": None}) == 0.0
    assert line_value({}) == 0.0


def test_line_value_keeps_a_real_line() -> None:
    assert line_value({"line": 2.5}) == 2.5
    assert line_value({"line": "7.5"}) == 7.5


def test_leg_keys_survive_a_winner_leg() -> None:
    leg = {"sofascore_event_id": 1, "market": "winner", "subject": None,
           "line": None, "direction": "TEAM1"}
    assert audit_trend.leg_key(leg) == (1, "winner", "", 0.0, "TEAM1")
    assert run_boosts._key(1, leg) == (1, "winner", "", 0.0, "TEAM1")
