"""A refit keeps the separately fitted curves (bet.sofa.fit_meta): the
new-market keys of `new_market_curves_fitted_from` and the tennis winner,
which fit_confidence / fit_sport_confidence do not fit and would otherwise
drop with the whole file / sport section (until 2026-10-16 each refit carried
them by hand, data/refit_2026-10-16/carry_over.py). Offline and fast."""

from __future__ import annotations

import json
from typing import Any

from bet.sofa.config import config_path
from bet.sofa.fit_meta import (
    carry_separately_fitted_curves,
    carry_sport_new_market_curves,
)

CURVE = {"0.800-0.825": {"n": 900, "realised": 0.83, "realised_lo95": 0.81}}
OTHER = {"0.800-0.825": {"n": 50, "realised": 0.5, "realised_lo95": 0.4}}


def _prior() -> dict[str, Any]:
    return {
        "by_market": {"match_won_for": CURVE, "goals_total": OTHER},
        "by_market_direction": {"result_or_over@X@2.5|OVER": CURVE,
                                "goals_total|OVER": OTHER},
        "by_class": {
            "season_early": {"by_market_direction": {
                "result_or_over@X@2.5|OVER": CURVE}},
            "tennis_women": {"by_market": {"match_won_for": CURVE},
                             "by_market_direction": {"set_score_not|OVER": CURVE}},
        },
        "new_market_curves_fitted_from": {
            "result_or_over@X@2.5|OVER": {"group": "football_score_markets"},
            "season_early:result_or_over@X@2.5|OVER": {"group": "g"},
            "tennis_women:set_score_not|OVER": {"group": "g"},
            "draw_no_bet|OVER": {"group": "g"},  # listed, curve gone: skipped
        },
        "match_won_for_fitted_from": {"script": "fit_tennis_winner_curve.py"},
    }


def test_a_full_fit_keeps_every_separately_fitted_curve() -> None:
    new: dict[str, Any] = {"by_market": {"goals_total": CURVE},
                           "by_market_direction": {"goals_total|OVER": CURVE},
                           "by_class": {"tennis_women": {"by_market": {}}}}
    carried = carry_separately_fitted_curves(new, _prior())
    assert sorted(carried) == sorted([
        "result_or_over@X@2.5|OVER", "season_early:result_or_over@X@2.5|OVER",
        "tennis_women:set_score_not|OVER", "match_won_for",
        "tennis_women:match_won_for"])
    assert new["by_market_direction"]["result_or_over@X@2.5|OVER"] == CURVE
    assert new["by_class"]["season_early"]["by_market_direction"][
        "result_or_over@X@2.5|OVER"] == CURVE
    assert new["by_class"]["tennis_women"]["by_market_direction"][
        "set_score_not|OVER"] == CURVE
    assert new["by_market"]["match_won_for"] == CURVE
    assert new["by_class"]["tennis_women"]["by_market"]["match_won_for"] == CURVE
    # what the fit produced itself is never replaced by the old curve
    assert new["by_market"]["goals_total"] == CURVE
    assert new["by_market_direction"]["goals_total|OVER"] == CURVE
    assert new["new_market_curves_fitted_from"] == \
        _prior()["new_market_curves_fitted_from"]
    assert new["match_won_for_fitted_from"] == _prior()["match_won_for_fitted_from"]


def test_a_key_the_new_fit_holds_is_not_overwritten() -> None:
    new: dict[str, Any] = {"by_market_direction": {
        "result_or_over@X@2.5|OVER": OTHER}}
    carried = carry_separately_fitted_curves(new, _prior())
    assert "result_or_over@X@2.5|OVER" not in carried
    assert new["by_market_direction"]["result_or_over@X@2.5|OVER"] == OTHER


def test_nothing_to_carry() -> None:
    new: dict[str, Any] = {}
    assert carry_separately_fitted_curves(new, None) == []
    assert carry_separately_fitted_curves(new, {}) == []
    assert new == {}


def test_the_installed_file_loses_nothing_through_a_refit() -> None:
    """Every key listed in the installed calibration survives a fit that
    produced none of them."""
    live = json.loads(config_path("sofa_confidence_calibration.json").read_text())
    new: dict[str, Any] = {"by_market": {}, "by_market_direction": {},
                           "by_class": {}}
    carried = carry_separately_fitted_curves(new, live)
    listed = live["new_market_curves_fitted_from"]
    assert set(carried) >= set(listed)
    assert len([k for k in carried if "@" in k]) >= 100  # the score-market slices
    assert "match_won_for" in carried


def test_a_sport_refit_keeps_the_installed_new_market_curves() -> None:
    prior = {
        "sports": {"hockey": {"curves": {"double_chance|TEAM": CURVE,
                                         "total|OVER": OTHER},
                              "curve_source": {"double_chance|TEAM": "history"}},
                   "cs2": {"curves": {"rounds_total|OVER": CURVE}}},
        "new_market_curves_fitted_from": {
            "hockey:double_chance|TEAM": {}, "cs2:rounds_total|OVER": {}},
    }
    section: dict[str, Any] = {"curves": {"total|OVER": CURVE}, "admitted": []}
    assert carry_sport_new_market_curves(section, "hockey", prior) == [
        "hockey:double_chance|TEAM"]
    assert section["curves"]["double_chance|TEAM"] == CURVE
    assert section["curves"]["total|OVER"] == CURVE  # the fit's own
    assert section["curve_source"]["double_chance|TEAM"] == "history"
    other: dict[str, Any] = {"curves": {}}
    assert carry_sport_new_market_curves(other, "volleyball", prior) == []
    assert carry_sport_new_market_curves(other, "hockey", None) == []


def test_the_installed_sport_file_loses_nothing_through_a_refit() -> None:
    live = json.loads(
        config_path("sofa_sport_confidence_calibration.json").read_text())
    for sport in live["sports"]:
        section: dict[str, Any] = {"curves": {}}
        carried = carry_sport_new_market_curves(section, sport, live)
        want = {k for k in live.get("new_market_curves_fitted_from") or {}
                if k.startswith(f"{sport}:")}
        assert set(carried) == want, sport
