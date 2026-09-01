"""docs/PLAN_BOGATE_STATYSTYKI.md 3bis.1: BET_MARKETS_PROFILE=legacy|v2.

Unit-level coverage of bet.stats.market_ranking's profile switch itself,
separate from tests/simple_stats/test_diff_stats_sheet.py's end-to-end
replay of the frozen fixture under each profile.
"""
from __future__ import annotations

import os

import pytest

from bet.stats import market_ranking


@pytest.fixture(autouse=True)
def _clear_markets_profile_env():
    os.environ.pop("BET_MARKETS_PROFILE", None)
    yield
    os.environ.pop("BET_MARKETS_PROFILE", None)


def test_default_profile_is_v2():
    assert "BET_MARKETS_PROFILE" not in os.environ
    assert market_ranking.markets_profile() == "v2"


def test_legacy_is_case_insensitive():
    os.environ["BET_MARKETS_PROFILE"] = "LEGACY"
    assert market_ranking.markets_profile() == "legacy"


def test_an_unrecognized_value_fails_safe_onto_v2():
    """A typo in the env var must not silently roll the market grid back --
    only the exact spelling "legacy" may do that."""
    os.environ["BET_MARKETS_PROFILE"] = "legac"
    assert market_ranking.markets_profile() == "v2"


def test_standard_market_lines_v2_is_the_module_level_dict():
    os.environ["BET_MARKETS_PROFILE"] = "v2"
    lines = market_ranking.standard_market_lines()
    assert lines is market_ranking.STANDARD_MARKET_LINES


def test_standard_market_lines_legacy_drops_the_planned_football_markets():
    os.environ["BET_MARKETS_PROFILE"] = "legacy"
    football = market_ranking.standard_market_lines()["football"]
    legacy_names = {m["market"] for m in football}
    assert legacy_names == {
        "Corners Total", "Cards Total", "Fouls Total", "Shots on Target",
        "Goals Total", "Team Corners", "Team Fouls", "Team Cards",
        "Team Shots on Target", "Team Shots",
    }
    # every market added by a later phase is absent
    for added in ("Shots Total", "Goals 1H Total", "Goals 2H Total",
                  "Total Offsides", "Total Red Cards", "Team Goals", "Team Offsides"):
        assert added not in legacy_names


def test_standard_market_lines_legacy_uses_the_pre_widening_grid():
    os.environ["BET_MARKETS_PROFILE"] = "legacy"
    football = market_ranking.standard_market_lines()["football"]
    by_name = {m["market"]: m for m in football}
    assert by_name["Corners Total"]["lines"] == [8.5, 9.5, 10.5, 11.5]
    assert by_name["Goals Total"]["lines"] == [1.5, 2.5, 3.5]
    assert by_name["Team Corners"]["lines"] == [3.5, 4.5, 5.5]
    assert by_name["Team Shots on Target"]["lines"] == [2.5, 3.5, 4.5, 5.5]


def test_standard_market_lines_legacy_leaves_other_sports_untouched():
    """3bis.5: every phase's line change touched only the football key."""
    os.environ["BET_MARKETS_PROFILE"] = "legacy"
    legacy = market_ranking.standard_market_lines()
    other_sports = (
        "basketball", "tennis", "volleyball", "hockey", "cs2", "dota2", "valorant",
    )
    for sport in other_sports:
        assert legacy[sport] == market_ranking.STANDARD_MARKET_LINES[sport]


def test_player_prop_lines_legacy_narrows_shots_on_target():
    os.environ["BET_MARKETS_PROFILE"] = "legacy"
    by_name = {m["market"]: m for m in market_ranking.player_prop_lines()["football"]}
    assert by_name["Player Shots on Target"]["lines"] == [0.5, 1.5]

    os.environ["BET_MARKETS_PROFILE"] = "v2"
    by_name = {m["market"]: m for m in market_ranking.player_prop_lines()["football"]}
    assert by_name["Player Shots on Target"]["lines"] == [0.5, 1.5, 2.5]
