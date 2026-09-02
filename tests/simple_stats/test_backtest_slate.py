"""backtest_slate.py's own arithmetic, which nothing else checks.

The script is what tells this pipeline whether a change helped, so its two
non-obvious pieces are worth the same care as the code they judge:

* ``_score_actuals`` derives goals from the fixture row, because ``/stats/``
  does not carry them. Half-time splits and per-side goals both come out of
  the same two numbers, and getting the 2H arithmetic backwards would settle
  every ``goals_2h_*`` row against the wrong figure while looking plausible.
* ``_team_subject`` reads ``CouponSingle.subject`` as a team *only* when the
  market says it is one. The artifact's ``subject`` is
  ``player_name or team_name``, so reading it the other way round settles a
  player's shots against his team's.

Loaded the way test_diff_stats_sheet.py loads its script, since neither lives
on the import path.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def bt():
    path = ROOT / "scripts" / "simple" / "backtest_slate.py"
    spec = importlib.util.spec_from_file_location("_backtest_slate", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- goals off the fixture row ---------------------------------------------


def test_a_full_time_score_gives_the_total_and_each_side(bt):
    out = bt._score_actuals({"score": {"home": 2, "away": 1}})
    assert out["goals_total"] == 3.0
    assert out["__home_goals"] == 2.0
    assert out["__away_goals"] == 1.0
    # No half-time score, so nothing about the halves is invented.
    assert "goals_1h_total" not in out
    assert "goals_2h_total" not in out


def test_the_second_half_is_the_difference_and_not_the_half_time_score(bt):
    """The arithmetic that would be plausible and wrong. 3-1 at full time from
    1-1 at the break is two second-half goals, not two first-half ones."""
    out = bt._score_actuals({"score": {"home": 3, "away": 1, "home_ht": 1, "away_ht": 1}})
    assert out["goals_1h_total"] == 2.0
    assert out["goals_2h_total"] == 2.0
    assert out["goals_1h_total"] + out["goals_2h_total"] == out["goals_total"]


def test_a_goalless_draw_is_a_score_and_not_a_missing_one(bt):
    out = bt._score_actuals({"score": {"home": 0, "away": 0, "home_ht": 0, "away_ht": 0}})
    assert out["goals_total"] == 0.0
    assert out["goals_1h_total"] == 0.0
    assert out["goals_2h_total"] == 0.0


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"score": {}},
        {"score": {"home": 1}},
        {"score": {"away": 1}},
        {"score": {"home": None, "away": None}},
    ],
)
def test_an_unreported_score_yields_nothing(bt, payload):
    """Not zeroes. A fixture with no published score must leave every goals row
    ``NO_DATA``, and a 0-0 default would score every OVER as a loss."""
    assert bt._score_actuals(payload) == {}


def test_a_half_time_score_without_a_full_time_one_is_ignored(bt):
    """The 2H figure needs both, and a first half alone is not a result."""
    assert bt._score_actuals({"score": {"home_ht": 1, "away_ht": 0}}) == {}


# --- whose subject ---------------------------------------------------------


class _Single:
    def __init__(self, market, subject):
        self.market, self.subject = market, subject


@pytest.mark.parametrize(
    "market,expected",
    [
        ("corners_for", "Sheffield United"),
        ("shots_on_target_for", "Sheffield United"),
        ("goals_1h_for", "Sheffield United"),
        # A person, so not a team subject however the name reads.
        ("player_total_shots", None),
        ("player_cards", None),
        # A match total names nobody.
        ("corners_total", None),
        ("goals_total", None),
        ("total_games", None),
    ],
)
def test_only_a_for_market_names_a_team(bt, market, expected):
    assert bt._team_subject(_Single(market, "Sheffield United")) == expected


def test_a_player_market_is_checked_before_the_for_suffix(bt):
    """Order matters and the test says so: no player market ends in ``_for``
    today, but ``player_goals_for`` would read as both, and settling it as a
    team row is the failure this ordering prevents."""
    assert bt._team_subject(_Single("player_goals_for", "Somebody")) is None
