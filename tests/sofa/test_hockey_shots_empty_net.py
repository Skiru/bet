"""Audit 2026-10-13 B8: hockey shots x conversion and the fitted empty net.
Offline; the switches are off unless the evidence doc says otherwise."""

from __future__ import annotations

from bet.sofa import epochs
from bet.sofa import score_model as sm
from bet.sofa.football_rating import FootballResult
from bet.sofa.shadow import SPORTS


def _stats(h: float, a: float) -> dict[str, object]:
    return {"statistics": [{"period": "ALL", "groups": [{"statisticsItems": [
        {"key": "Shots", "homeValue": h, "awayValue": a}]}]}]}


def test_shot_values_and_overtime_scaling() -> None:
    v = sm.hockey_shot_values(_stats(30, 25), 3, 2, overtime=False)
    assert v is not None
    assert v[sm.HK_SHOTS] == (30.0, 25.0)
    assert v[sm.HK_CONV] == (3 / 30, 2 / 25)
    ot = sm.hockey_shot_values(_stats(32.5, 26.0), 3, 2, overtime=True)
    assert ot is not None
    assert abs(ot[sm.HK_SHOTS][0] - 30.0) < 1e-9


def test_shot_values_refuse_implausible_or_missing() -> None:
    assert sm.hockey_shot_values(_stats(3, 25), 1, 2, False) is None
    assert sm.hockey_shot_values(_stats(30, 90), 1, 2, False) is None
    assert sm.hockey_shot_values({"statistics": []}, 1, 2, False) is None
    assert sm.hockey_shot_values(None, 1, 2, False) is None


def test_attach_keeps_goals_and_is_noop_without_box() -> None:
    reg = sm.REG_METRIC["hockey"]
    r = FootballResult(event_id=1, ts=0, competition_id=1, home_id=1, away_id=2,
                       values={reg: (3.0, 2.0)})
    assert sm.attach_hockey_shots(r, None, False) is r
    got = sm.attach_hockey_shots(r, _stats(30, 25), False)
    assert got.values[reg] == (3.0, 2.0)
    assert sm.HK_SHOTS in got.values and sm.HK_CONV in got.values


def test_empty_net_params_off_is_identity_and_on_sets_by_lead() -> None:
    base = sm.SimParams()
    assert sm.empty_net_params(base, "hockey", False) is base
    assert sm.empty_net_params(base, "basketball", True) is base
    p = sm.empty_net_params(None, "hockey", True)
    assert p is not None
    e1, e2, t = sm.HK_EMPTY_NET
    assert (p.hk_late_lead, p.hk_late_lead2) == (e1, e2)
    assert (p.hk_late_trail, p.hk_late_trail2) == (t, t)


def test_switches_are_pure_functions_of_the_epoch() -> None:
    old_s, old_e = epochs.HK_SHOTS_FROM_UTC, epochs.HK_EMPTY_NET_FROM_UTC
    try:
        epochs.HK_SHOTS_FROM_UTC = None
        epochs.HK_EMPTY_NET_FROM_UTC = None
        assert epochs.hk_shots("2026-12-01") is None
        assert epochs.hk_empty_net("2026-12-01") is False
    finally:
        epochs.HK_SHOTS_FROM_UTC, epochs.HK_EMPTY_NET_FROM_UTC = old_s, old_e


def test_shots_off_model_has_no_shots_centre() -> None:
    model = sm.build_model([], SPORTS["hockey"], 0)
    assert model.shots is None
    assert model.shots_expected(1, 1, 2) is None
