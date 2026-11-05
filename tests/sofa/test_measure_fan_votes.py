"""scripts/sofa/measure_fan_votes.py - fan votes beside the de-vigged price."""

import numpy as np
import pytest

from scripts.sofa.measure_fan_votes import (
    _money,
    bh,
    candidate_bets,
    fit_logistic,
    football_event,
    outcomes,
    parse_votes,
    vote_shares,
)

KO = "2026-11-03T18:00:00Z"


def _rung(market, subject, over, under, at="2026-11-03T08:00:00Z"):
    return {"market": market, "subject": subject, "line": 0.5,
            "over_odds": over, "under_odds": under, "fetched_at_utc": at}


def test_votes_payload_parsed_and_tennis_draw_is_none():
    got = parse_votes({"vote": {"vote1": 8196, "vote2": 1083, "voteX": None}})
    assert got == {"status": "OK", "vote1": 8196, "voteX": None, "vote2": 1083}
    assert parse_votes(None) == {"status": "NOT_FOUND"}
    assert parse_votes({"other": 1}) == {"status": "NO_VOTE"}


def test_football_three_way_from_1_2_and_the_dc12_other_side():
    rungs = [_rung("result_1x2", "1", 2.0, 1.8),
             _rung("result_1x2", "2", 3.6, 1.28),
             _rung("double_chance", "12", 1.30, 3.4),
             _rung("draw_no_bet", "1", 1.5, 2.5)]
    got = football_event(rungs, KO)
    assert got is not None
    assert got["o_D"] == 3.4
    assert got["p_H"] + got["p_D"] + got["p_A"] == pytest.approx(1.0)
    assert got["p_H"] > got["p_A"]
    assert got["o_dnb_H"] == 1.5 and got["o_dnb_A"] == 2.5


def test_a_price_fetched_after_the_start_is_not_used():
    late = "2026-11-03T18:05:00Z"
    rungs = [_rung("result_1x2", "1", 2.0, 1.8, late),
             _rung("result_1x2", "2", 3.6, 1.28),
             _rung("double_chance", "12", 1.30, 3.4)]
    assert football_event(rungs, KO) is None


def test_draw_is_both_sides_lost():
    rows = [{"sofascore_event_id": 1, "market": "result_1x2", "subject": "1",
             "direction": "OVER", "outcome": "LOSS"},
            {"sofascore_event_id": 1, "market": "result_1x2", "subject": "2",
             "direction": "OVER", "outcome": "LOSS"},
            {"sofascore_event_id": 2, "market": "result_1x2", "subject": "2",
             "direction": "OVER", "outcome": "WIN"}]
    got = outcomes(rows)
    assert got[("football", 1)] == "D"
    assert got[("football", 2)] == "A"


def test_few_votes_are_out_and_shares_are_smoothed():
    few = {"sport": "football", "vote1": 5, "voteX": 2, "vote2": 3}
    assert vote_shares(few) is None
    sh = vote_shares({"sport": "tennis", "vote1": 30, "voteX": None, "vote2": 10})
    assert sh == {"H": 31 / 42, "A": 11 / 42}


def test_dnb_draw_is_a_refund_and_tax_applies_to_the_return():
    ev = {"sport": "football", "outcome": "D", "p_H": 0.5, "p_D": 0.25, "p_A": 0.25,
          "o_dnb_H": 1.4, "o_dnb_A": 2.9, "share": {"H": 0.6, "D": 0.2, "A": 0.2}}
    bets = candidate_bets(ev, "dnb")
    assert [b[3] for b in bets] == [-1.0, -1.0]
    m = _money([(0, 2.0, 0.5, 1.0), (1, 2.0, 0.5, 0.0), (2, 2.0, 0.5, -1.0)])
    assert m["roi_pre"] == pytest.approx(0.0)
    assert m["roi_post"] == pytest.approx((0.88 * 2.0 - 1 - 1) / 3)
    assert m["realised_minus_fair"] == pytest.approx(0.0)


def test_benjamini_hochberg():
    assert bh([0.001, 0.02, 0.04, 0.5]) == [True, True, False, False]
    assert bh([0.2, 0.3]) == [False, False]


def test_logistic_recovers_a_known_slope():
    rng = np.random.default_rng(1)
    x = rng.normal(size=5000)
    y = (rng.random(5000) < 1 / (1 + np.exp(-(0.3 + 1.5 * x)))).astype(float)
    w = fit_logistic(x[:, None], y)
    assert w[0] == pytest.approx(0.3, abs=0.12)
    assert w[1] == pytest.approx(1.5, abs=0.15)
