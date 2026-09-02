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


# --- the full-time gate ------------------------------------------------------
#
# ``/events/{id}/stats/`` answers for a match in play exactly as it answers for
# a finished one, so a partial count is indistinguishable from a full-time one
# once it leaves the fetch. On 2026-09-02 that settled eleven coupon rows
# against ~70-minute counts and cached the snapshots, and the run reported hit
# 36.4% against a claimed 56.3% -- entirely an artifact of the clock.


@pytest.mark.parametrize(
    "status",
    ["finished", "FINISHED", " finished ", "ft", "AET", "after_penalties", "awarded"],
)
def test_a_full_time_status_settles(bt, status):
    finished, seen = bt._is_finished({"event": {"match_status": status}})
    assert finished is True
    assert seen == status


@pytest.mark.parametrize(
    "status", ["2nd_half", "1st_half", "halftime", "notstarted", "postponed", "cancelled"]
)
def test_a_match_still_in_play_or_never_played_does_not_settle(bt, status):
    finished, seen = bt._is_finished({"event": {"match_status": status}})
    assert finished is False
    assert seen == status


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"event": {}},
        {"event": {"match_status": None}},
        {"event": {"match_status": ""}},
        # Not a dict where one is expected: still refused, never assumed final.
        {"event": "finished"},
    ],
)
def test_an_absent_status_fails_closed(bt, payload):
    """A missing marker is *not* full-time. Failing open here is what poisons
    the on-disk cache, and the cache outlives the run that wrote it."""
    assert bt._is_finished(payload)[0] is False


def test_the_unwrapped_shape_is_accepted_like_the_score_reader(bt):
    """``_score_actuals`` accepts the fixture row either wrapped in ``event``
    or bare; the status gate reads the same payload and must agree."""
    assert bt._is_finished({"match_status": "finished"})[0] is True
    assert bt._is_finished({"match_status": "2nd_half"})[0] is False


# --- slip legs ---------------------------------------------------------------
#
# 32 of the 47 predictions in the 2026-09-02 coupon were Bet Builder legs and
# none had ever been settled, so the drafter's claims had never been checked.


class _Leg:
    def __init__(self, market, line, direction, team_name=None, player_name=None):
        self.market = market
        self.line = line
        self.direction = direction
        self.team_name = team_name
        self.player_name = player_name
        self.tier = "LEAN"
        self.p_low = 0.7
        self.superbet_price = 1.05
        self.market_verdict = None


class _Draft:
    def __init__(self, legs):
        self.legs = legs


class _Slip:
    def __init__(self, event_id, legs, match="Home v Away", rank=1):
        self.event_id = event_id
        self.match = match
        self.rank = rank
        self.draft = _Draft(legs)


class _Coupons:
    def __init__(self, slips):
        self.slips = slips


class _Event:
    def __init__(self, event_id, home, away):
        self.event_id = event_id
        self.home_team = home
        self.away_team = away


class _Events:
    def __init__(self, events):
        self.events = events


@pytest.fixture
def one_fixture():
    return _Events([_Event("e1", "Burnley", "Middlesbrough")])


ACTUALS = {
    "e1": {
        "total": {"goals_total": 3.0, "corners_total": 9.0},
        "home": {"goals_for": 1.0},
        "away": {"goals_for": 2.0},
    }
}


def test_every_leg_of_every_slip_gets_a_record(bt, one_fixture):
    slips = [
        _Slip("e1", [_Leg("goals_total", 2.5, "OVER"), _Leg("corners_total", 9.5, "UNDER")]),
        _Slip("e1", [_Leg("goals_total", 3.5, "OVER")], rank=2),
    ]
    out = bt.settle_slip_legs(_Coupons(slips), one_fixture, ACTUALS)
    assert [r["outcome"] for r in out] == ["WON", "WON", "LOST"]
    # Regroupable: a slip pays nothing unless every leg lands, so the caller
    # must be able to reassemble the slips from the flat record list.
    assert {r["slip_rank"] for r in out} == {1, 2}


def test_a_whole_number_line_pushes_rather_than_losing(bt, one_fixture):
    out = bt.settle_slip_legs(
        _Coupons([_Slip("e1", [_Leg("corners_total", 9.0, "UNDER")])]), one_fixture, ACTUALS
    )
    assert out[0]["outcome"] == "PUSH"


def test_a_team_leg_settles_against_its_own_side(bt, one_fixture):
    legs = [
        _Leg("goals_for", 1.5, "UNDER", team_name="Burnley"),
        _Leg("goals_for", 1.5, "UNDER", team_name="Middlesbrough"),
    ]
    out = bt.settle_slip_legs(_Coupons([_Slip("e1", legs)]), one_fixture, ACTUALS)
    # Burnley scored 1, Middlesbrough 2: the same leg on the two sides must
    # not settle against the same number.
    assert [r["outcome"] for r in out] == ["WON", "LOST"]
    assert [r["actual"] for r in out] == [1.0, 2.0]


def test_a_player_leg_is_not_settled_against_his_team(bt, one_fixture):
    """``/stats/`` carries no player family, so a player leg has no actual.
    Scoring it against the team's figure would look exactly like evidence."""
    leg = _Leg("player_total_shots", 0.5, "OVER", player_name="Zeki Amdouni")
    out = bt.settle_slip_legs(_Coupons([_Slip("e1", [leg])]), one_fixture, ACTUALS)
    assert out[0]["outcome"] == "NO_DATA"
    assert out[0]["subject"] == "Zeki Amdouni"


def test_a_fixture_without_actuals_yields_no_data_and_not_a_loss(bt):
    slips = [_Slip("missing", [_Leg("goals_total", 2.5, "OVER")])]
    out = bt.settle_slip_legs(_Coupons(slips), _Events([]), {})
    assert out[0]["outcome"] == "NO_DATA"
    assert out[0]["actual"] is None
