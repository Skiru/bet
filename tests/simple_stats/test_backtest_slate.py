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
    def __init__(self, market, line, direction, team_name=None, player_name=None,
                 player_id=None):
        self.market = market
        self.line = line
        self.direction = direction
        self.team_name = team_name
        self.player_name = player_name
        self.player_id = player_id
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


# --------------------------------------------------------------------------
# 2026-09-06: three defects in the *instrument*, found while using it.
#
# None of them changed a coupon. All three changed what the coupon was measured
# against, which is worse: a wrong number that looks like evidence outranks a
# missing one.


def test_the_replay_defaults_to_the_bar_the_pipeline_actually_ships(bt):
    """``--bar-basis`` defaulted to p_low; ``build_coupons`` ships p_central.

    The bar is ``(1/p) x margin`` and ``p_low`` sits 16-22 points under
    ``p_central``, so the default replay arm demanded roughly 1.4x the price
    the live file does. It did not merely shift the numbers -- it emptied the
    group the coupon is built around. Replaying 2026-09-05 at a 400-single
    budget returned **1** VALUE row; the same sheet, offer and vetoes at the
    shipped basis return 7 at a budget of 15.

    Pinned against ``build_coupons``'s own signature default rather than
    against the string, so the two cannot drift apart again silently.
    """
    import inspect

    from bet.simple_stats.coupons import build_coupons

    shipped = inspect.signature(build_coupons).parameters["bar_basis"].default
    for fn in (bt.coupons_from_sheet, bt.rebuilt_coupons, bt.recorded_sheet_coupons):
        assert inspect.signature(fn).parameters["bar_basis"].default == shipped


def test_recorded_sheet_alone_does_not_silently_run_every_other_arm():
    """``--recorded-sheet`` was not counted as a choice.

    ``both = not (args.recorded or args.rebuilt)`` left ``--recorded-sheet``
    out, so asking for the controlled arm on its own quietly ran all three --
    including ``--rebuilt``, whose dossier load is the expensive one and, on
    2026-08-29, aborted the whole invocation with 824 validation errors.
    """
    source = (
        ROOT / "scripts" / "simple" / "backtest_slate.py"
    ).read_text(encoding="utf-8")
    assert "args.recorded or args.rebuilt or args.recorded_sheet" in source


def _observation(provider: str, value: float) -> dict:
    return {
        "provider": provider,
        "match_id": f"m-{provider}-{value}",
        "match_date": "2026-08-01T00:00:00+00:00",
        "opponent": "Someone",
        "value": value,
        "observed_at": "2026-08-29T00:00:00+00:00",
    }


def test_a_retired_provider_does_not_make_a_frozen_dossier_unreplayable(tmp_path):
    """Taking bzzoiro-tennis out of ``PROVIDER_NAMES`` broke ``runs/2026-08-29``.

    ``load_market_context`` was hardened against exactly this on 2026-09-02 and
    the dossier artifact one step upstream was not, so the slate simply dropped
    out of every replay -- reported as one "unavailable" line on stderr among a
    thousand coverage gaps. The retired provider's observations must be
    dropped, not accepted: reusing them is what the retirement was for.
    """
    import json as _json

    from bet.simple_stats.artifact_io import load_event_dossiers

    payload = {
        "run_id": "RID-1",
        "date": "2026-08-29",
        "generated_at": "2026-08-29T00:00:00+00:00",
        "dossiers": [
            {
                "event_id": "evt-1",
                "sport": "tennis",
                "readiness": "READY",
                "team_a_name": "A",
                "team_b_name": "B",
                "metrics": {
                    "aces_total": {
                        "canonical_name": "aces_total",
                        "team_a_l10": [
                            _observation("tennis-abstract", 5.0),
                            _observation("bzzoiro-tennis", 99.0),
                        ],
                    },
                    "double_faults_total": {
                        "canonical_name": "double_faults_total",
                        "team_a_l10": [_observation("bzzoiro-tennis", 3.0)],
                    },
                },
            }
        ],
    }
    path = tmp_path / "dossiers.json"
    path.write_text(_json.dumps(payload), encoding="utf-8")

    dossiers, retired = load_event_dossiers(path)
    assert retired == ["bzzoiro-tennis"]
    metrics = dossiers.dossiers[0].metrics
    # The surviving provider's reading is still evidence.
    assert [o.value for o in metrics["aces_total"].team_a_l10] == [5.0]
    # A metric left with nothing is not a sample and is removed outright.
    assert "double_faults_total" not in metrics


# --------------------------------------------------------------------------
# 2026-09-06: the Bet Builder was graded by its legs and staked as a slip.


def _slip_coupons(*leg_specs):
    """A CouponSet with one slip whose legs are ``(market, line, direction)``."""
    from bet.simple_stats.bet_builder_draft import BetBuilderDraft, BetBuilderLeg
    from bet.simple_stats.coupons import CouponSet, CouponSlip

    legs = [
        BetBuilderLeg(
            event_id="evt-1", market=m, line=ln, direction=d, tier="LEAN",
            p_low=0.6, p_central=0.8, hit_rate=0.8, sample_size=10,
            fair_odds=1.67, min_acceptable_odds=1.38,
        )
        for m, ln, d in leg_specs
    ]
    draft = BetBuilderDraft(
        event_id="evt-1", legs=legs, combined_price=None,
        joint_probability=0.64, correlation_lambda=1.006,
        min_acceptable_combined_odds=1.72, legs_priced_separately=2.79,
        correlation_risk="HIGH", correlation_note="n/a", excluded={},
    )
    return CouponSet(
        run_id="RID-1", date="2026-09-06",
        generated_at="2026-09-06T00:00:00+00:00", singles=[],
        slips=[CouponSlip(
            rank=1, event_id="evt-1", match="A – B", competition="PL",
            kickoff="2026-09-06T20:00:00+00:00", draft=draft,
            weakest_leg_p_low=0.6,
        )],
        combined_price=None, rows_considered=0, events_considered=1,
    )


def _slip_events():
    from bet.simple_stats.contracts import EventListV1, EventRecord

    return EventListV1(
        run_id="RID-1", date="2026-09-06",
        generated_at="2026-09-06T00:00:00+00:00",
        events=[EventRecord(
            event_id="evt-1", sport="football", competition="PL",
            home_team="A", away_team="B",
            start_time="2026-09-06T20:00:00+00:00",
            identity_confidence="CONFIRMED", status="ACTIVE",
        )],
    )


_SLIP_ACTUALS = {"evt-1": {
    "home": {}, "away": {},
    "total": {"corners_total": 11.0, "fouls_total": 24.0, "shots_total": 22.0},
}}


def test_a_slip_pays_nothing_unless_every_leg_lands(bt):
    """The whole point. 87.6% of legs landed and 67.8% of slips did; only the
    second number is the thing being staked, and nothing had ever computed it."""
    coupons = _slip_coupons(
        ("corners_total", 9.5, "OVER"),    # 11 > 9.5  -> WON
        ("fouls_total", 26.5, "UNDER"),    # 24 < 26.5 -> WON
    )
    [record] = bt.settle_slips(coupons, _slip_events(), _SLIP_ACTUALS)
    assert record["outcome"] == "WON"
    assert record["legs"] == 2 and record["legs_won"] == 2

    coupons = _slip_coupons(
        ("corners_total", 9.5, "OVER"),    # WON
        ("fouls_total", 20.5, "UNDER"),    # 24 > 20.5 -> LOST
    )
    [record] = bt.settle_slips(coupons, _slip_events(), _SLIP_ACTUALS)
    assert record["outcome"] == "LOST"
    # One leg landing is exactly the case the leg-level number flatters.
    assert record["legs_won"] == 1


def test_one_unsettleable_leg_makes_the_whole_slip_unknown(bt):
    """Grading the legs that did settle would score a three-leg slip as a two."""
    coupons = _slip_coupons(
        ("corners_total", 9.5, "OVER"),
        ("offsides_total", 3.5, "UNDER"),   # not in the actuals at all
    )
    [record] = bt.settle_slips(coupons, _slip_events(), _SLIP_ACTUALS)
    assert record["outcome"] == "NO_DATA"


def test_the_slip_summary_reports_the_price_the_bet_would_have_needed(bt):
    """``fair_combined_odds`` is 1/realised -- computed from what happened, not
    from the legs. Measured over the archive: 1.48 for the drafter's usual
    four-leg shape, against a 1.72 the file was asking for."""
    records = [
        {"outcome": "WON", "claimed": 0.64}, {"outcome": "WON", "claimed": 0.64},
        {"outcome": "LOST", "claimed": 0.64}, {"outcome": "WON", "claimed": 0.64},
        {"outcome": "NO_DATA", "claimed": None},
    ]
    summary = bt.summarise_slips("t", records)
    assert summary["settled"] == 4 and summary["won"] == 3
    assert summary["hit"] == pytest.approx(0.75)
    assert summary["fair_combined_odds"] == pytest.approx(1 / 0.75)
    # A slip drafted before ``joint_probability`` existed still settles and is
    # simply absent from the calibration line.
    assert summary["claimed_n"] == 4
