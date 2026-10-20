"""Football card points by half, red cards / penalties by side and half,
both teams red - behind epochs.FOOTBALL_CARD_HALVES_FROM_UTC (None).
Offline and fast.

Evidence: docs/sofa/evidence/football_card_halves_2026-10-21.md. The Superbet
shapes are the real ones (runs/sofa/2026-10-19/unmapped_prices: "1. połowa -
liczba kartek" "poniżej 1.5" sbv "1.5"; "1. połowa - Cagliari liczba kartek";
"1.połowa - liczba czerwonych kartek" "Powyżej 0.5"; "Liczba czerwonych
kartek Getafe"; "1.połowa - <T> - liczba przyznanych rzutów karnych"; "1.
połowa - najwięcej kartek" 1 / 2 / remis; "1. połowa - liczba kartek -
handicap" "Getafe (-0.5)"; "Obie drużyny otrzymają czerwoną kartkę" Tak /
Nie).
"""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from typing import Any

import pytest

from bet.sofa import epochs
from bet.sofa import football_card_halves as fch
from bet.sofa import football_rating as fr
from bet.sofa.contracts import FixtureOffer, GapReason, PricedRung
from bet.sofa.coupon_results import EVENT_MARKETS
from bet.sofa.metrics import (
    CARD_INCIDENT_SCOPES,
    FOOTBALL_METRICS,
    calculate_cards_points,
    calculate_cards_points_by_half,
    extract_metric,
)
from bet.sofa.offer import classify_odd, day_flags
from bet.sofa.superbet_names import _football_tennis
from bet.sofa.tennis_winner import RATING_ONLY_MARKETS
from scripts.sofa.run_settle import _settle_derived
from scripts.sofa.run_sheet import card_half_rows

NAMES = ("Getafe", "Rayo Vallecano")
SUB = {"incidentType": "substitution", "incidentClass": "regular", "time": 60,
       "isHome": True}
YC0 = {"yellowCards": (0.0, 0.0)}


def _card(t: int, cls: str, home: bool, pid: int = 1, **kw: Any) -> dict[str, Any]:
    return {"incidentType": "card", "incidentClass": cls, "time": t,
            "isHome": home, "player": {"id": pid}, **kw}


def _goal(t: int, hs: int, as_: int, home: bool, cls: str = "regular"
          ) -> dict[str, Any]:
    return {"incidentType": "goal", "incidentClass": cls, "time": t,
            "homeScore": hs, "awayScore": as_, "isHome": home}


def _event(h: tuple[int, int], a: tuple[int, int], code: int = 100
           ) -> dict[str, Any]:
    return {
        "status": {"type": "finished", "description": "Ended", "code": code},
        "homeTeam": {"name": NAMES[0]}, "awayTeam": {"name": NAMES[1]},
        "homeScore": {"current": h[0] + h[1], "period1": h[0], "period2": h[1],
                      "normaltime": h[0] + h[1]},
        "awayScore": {"current": a[0] + a[1], "period1": a[0], "period2": a[1],
                      "normaltime": a[0] + a[1]},
    }


# --- grading: the half rule -----------------------------------------------------


def test_a_two_yellow_dismissal_splits_by_when_each_card_was_shown() -> None:
    # Sofascore writes the first yellow and then one yellowRed (event
    # 11173568: Botnari 39' yellow, 52' yellowRed): 1 in the first half, the
    # remainder up to 3 (2) in the second - the full match pays 3.
    inc = {"incidents": [_card(39, "yellow", True, pid=7),
                         _card(52, "yellowRed", True, pid=7),
                         _card(20, "yellow", False, pid=8), SUB]}
    halves = calculate_cards_points_by_half(inc)
    assert halves == ((1.0, 1.0), (2.0, 0.0))
    whole = calculate_cards_points(inc)
    assert not isinstance(whole, GapReason)
    assert sum(halves[0]) + sum(halves[1]) == sum(whole) == 4.0


def test_first_half_added_time_is_the_first_half_and_46_the_second() -> None:
    inc = {"incidents": [_card(45, "yellow", True, addedTime=3),
                         _card(46, "red", False, pid=2),
                         _card(90, "yellow", True, pid=3, addedTime=5), SUB]}
    assert calculate_cards_points_by_half(inc) == ((1.0, 0.0), (1.0, 2.0))


def test_staff_rescinded_dropped_and_untimed_player_card_refused() -> None:
    staff = {"incidentType": "card", "incidentClass": "yellow", "time": -5,
             "isHome": True, "manager": {"id": 9}}
    base = [_card(10, "yellow", True), SUB, staff,
            _card(30, "red", False, pid=2, rescinded=True)]
    assert calculate_cards_points_by_half({"incidents": base}) == (
        (1.0, 0.0), (0.0, 0.0))
    untimed = base + [_card(-5, "yellow", False, pid=5)]
    assert calculate_cards_points_by_half({"incidents": untimed}) == (
        GapReason.CARD_HALF_UNKNOWN)


def test_no_card_is_a_zero_only_when_the_statistic_says_so() -> None:
    inc = {"incidents": [SUB]}
    assert calculate_cards_points_by_half(inc, YC0) == ((0.0, 0.0), (0.0, 0.0))
    assert calculate_cards_points_by_half(inc, {"yellowCards": (2.0, 1.0)}) == (
        GapReason.STAT_KEY_ABSENT)
    assert calculate_cards_points_by_half(None) == GapReason.NO_INCIDENTS


EV = _event((0, 1), (1, 0))
INC = {"incidents": [
    _goal(70, 1, 1, True), _goal(12, 0, 1, False, cls="penalty"),
    _card(40, "red", True, pid=1), _card(80, "red", False, pid=2),
    _card(30, "yellow", False, pid=3),
    {"incidentType": "inGamePenalty", "incidentClass": "missed", "time": 85,
     "isHome": True},
    SUB]}


@pytest.mark.parametrize("metric,is_home,value", [
    ("cards_points_1h_total", True, 3.0),
    ("cards_points_1h_for", True, 2.0),
    ("cards_points_1h_for", False, 1.0),
    ("cards_points_2h_total", True, 2.0),
    ("cards_points_2h_for", False, 2.0),
    ("red_cards_for", True, 1.0),
    ("red_cards_1h_total", True, 1.0),
    ("red_cards_1h_for", False, 0.0),
    ("penalties_for", True, 1.0),
    ("penalties_for", False, 1.0),
    ("penalties_1h_total", True, 1.0),
    ("penalties_1h_for", True, 0.0),
    ("both_red_cards", True, 1.0),
])
def test_settle_grades_every_scope_through_extract_metric(
    metric: str, is_home: bool, value: float
) -> None:
    assert extract_metric(metric, "football", {}, INC, EV, is_home,
                          settling=True) == value


def test_scopes_refuse_extra_time_partial_feeds_and_stay_out_of_the_metrics(
) -> None:
    assert not set(CARD_INCIDENT_SCOPES) & set(FOOTBALL_METRICS)
    et = _event((0, 1), (1, 0), code=110)
    et["homeScore"]["extra1"] = 0
    assert extract_metric("cards_points_1h_total", "football", {}, INC, et, True,
                          settling=False) == GapReason.EVENT_NOT_FINISHED
    partial = {"incidents": [_goal(70, 1, 1, True), _goal(12, 0, 1, False)]}
    assert extract_metric("red_cards_for", "football", {}, partial, EV, True,
                          settling=True) == GapReason.INCIDENTS_PARTIAL_FEED
    # not a football metric anywhere else
    assert extract_metric("red_cards_for", "tennis", {}, INC, EV, True) == (
        GapReason.STAT_KEY_ABSENT)


def test_most_and_handicap_of_a_half_settle_through_the_derived_path() -> None:
    fixture = {"home_name": "Getafe", "away_name": "Rayo Vallecano"}
    row = {"market": fch.MOST_1H, "subject": "1", "line": 0.0, "direction": "OVER"}
    assert _settle_derived(row, "football", {}, INC, EV, fixture) == (1.0, "WIN")
    row = {"market": fch.MOST_2H, "subject": "__draw__", "line": 0.0,
           "direction": "OVER"}
    assert _settle_derived(row, "football", {}, INC, EV, fixture) == (-2.0, "LOSS")
    row = {"market": fch.HCP_2H, "subject": "Rayo Vallecano", "line": -0.5,
           "direction": "OVER"}
    assert _settle_derived(row, "football", {}, INC, EV, fixture) == (2.0, "WIN")


# --- OFFER ------------------------------------------------------------------------


@pytest.mark.parametrize("market,selection,sbv,want", [
    ("1. połowa - liczba kartek", "poniżej 1.5", "1.5",
     (fch.CARDS_1H_TOTAL, "", 1.5, "UNDER")),
    ("2. połowa - liczba kartek", "powyżej 2.5", "2.5",
     (fch.CARDS_2H_TOTAL, "", 2.5, "OVER")),
    ("1. połowa - Getafe liczba kartek", "powyżej 0.5", "0.5",
     (fch.CARDS_1H_FOR, "Getafe", 0.5, "OVER")),
    ("2. połowa - Rayo Vallecano liczba kartek", "poniżej 1.5", "1.5",
     (fch.CARDS_2H_FOR, "Rayo Vallecano", 1.5, "UNDER")),
    ("1. połowa - najwięcej kartek", "remis", None,
     (fch.MOST_1H, "__draw__", 0.0, "OVER")),
    ("2. połowa - najwięcej kartek", "2", None, (fch.MOST_2H, "2", 0.0, "OVER")),
    ("1. połowa - liczba kartek - handicap", "Getafe (-0.5)", "-0.5",
     (fch.HCP_1H, "Getafe", -0.5, "OVER")),
    ("1. połowa - liczba kartek - handicap", "Rayo Vallecano (0.5)", "-0.5",
     (fch.HCP_1H, "Rayo Vallecano", 0.5, "OVER")),
    ("Liczba czerwonych kartek Getafe", "Poniżej 1.5", "1.5",
     (fch.RED_FOR, "Getafe", 1.5, "UNDER")),
    ("1.połowa - liczba czerwonych kartek", "Powyżej 0.5", "0.5",
     (fch.RED_1H_TOTAL, "", 0.5, "OVER")),
    ("1.połowa - liczba czerwonych kartek Rayo Vallecano", "Poniżej 0.5", "0.5",
     (fch.RED_1H_FOR, "Rayo Vallecano", 0.5, "UNDER")),
    ("Getafe - liczba przyznanych rzutów karnych", "poniżej 0.5", "0.5",
     (fch.PEN_FOR, "Getafe", 0.5, "UNDER")),
    ("1.połowa - liczba przyznanych rzutów karnych", "powyżej 0.5", "0.5",
     (fch.PEN_1H_TOTAL, "", 0.5, "OVER")),
    ("1.połowa - Getafe - liczba przyznanych rzutów karnych", "poniżej 0.5", "0.5",
     (fch.PEN_1H_FOR, "Getafe", 0.5, "UNDER")),
    ("Obie drużyny otrzymają czerwoną kartkę", "Tak", None,
     (fch.BOTH_RED, "", 0.5, "OVER")),
    ("Obie drużyny otrzymają czerwoną kartkę", "Nie", None,
     (fch.BOTH_RED, "", 0.5, "UNDER")),
])
def test_classify_reads_the_superbet_shapes(
    market: str, selection: str, sbv: str | None, want: tuple[str, str, float, str]
) -> None:
    assert fch.classify_card_half(market, selection, sbv, NAMES) == want


@pytest.mark.parametrize("market,selection,sbv", [
    ("1. połowa - Real Madryt liczba kartek", "powyżej 0.5", "0.5"),  # no side
    ("1. połowa - liczba kartek", "poniżej 1.5", "2.5"),  # line disagrees
    ("1. połowa - liczba kartek", "poniżej 1", "1"),  # not a half line
    ("Liczba kartek", "poniżej 4.5", "4.5"),  # the full match: mapped elsewhere
    ("Liczba czerwonych kartek", "Poniżej 0.5", "0.5"),  # the 10-14 market
    ("1. połowa - liczba kartek - handicap", "Getafe (-1.5)", "-1.5"),
    ("Getafe - liczba kartek; Obie drużyny strzelą", "Tak", None),
    ("1. połowa - najwięcej kartek", "Getafe", None),
])
def test_classify_refuses_what_it_does_not_know(
    market: str, selection: str, sbv: str | None
) -> None:
    assert fch.classify_card_half(market, selection, sbv, NAMES) is None


def test_classify_odd_reads_them_only_when_the_switch_asks() -> None:
    item = {"marketName": "1. połowa - liczba kartek", "name": "poniżej 1.5",
            "specialBetValue": "1.5", "price": 1.4}
    assert classify_odd(item, (), False, NAMES) == (None, "1. połowa - liczba kartek")
    on = classify_odd(item, (), False, NAMES, False, False, False, False, False, True)
    assert on == ((fch.CARDS_1H_TOTAL, "", 1.5, "UNDER"), None)
    # the half "najwięcej kartek" stays unmapped with the switch off (the
    # half metric is not in FOOTBALL_METRICS, so the derived mapper refuses)
    most = {"marketName": "1. połowa - najwięcej kartek", "name": "1",
            "specialBetValue": None, "price": 2.1}
    assert classify_odd(most, (), False, NAMES)[0] is None


def test_the_switch_is_off_and_rides_on_the_day_and_the_clock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert epochs.FOOTBALL_CARD_HALVES_FROM_UTC is None
    assert not epochs.football_card_halves("2026-10-21")
    assert day_flags("2026-10-21")["football_card_halves"] is False
    on = datetime(2026, 10, 21, tzinfo=UTC)
    monkeypatch.setattr(epochs, "FOOTBALL_CARD_HALVES_FROM_UTC", on)
    assert epochs.football_card_halves("2026-10-21", on)
    assert not epochs.football_card_halves("2026-10-20", on)
    assert not epochs.football_card_halves("2026-10-21", datetime(
        2026, 10, 20, 23, tzinfo=UTC))


def test_registered_rating_only_and_counts_not_events() -> None:
    assert fch.MARKETS <= RATING_ONLY_MARKETS
    assert fch.BOTH_RED in EVENT_MARKETS
    assert not (fch.MARKETS - {fch.BOTH_RED}) & EVENT_MARKETS


# --- the price --------------------------------------------------------------------


def test_nb_pmf_is_a_distribution_with_its_mean() -> None:
    for mean, r in ((1.4, 1e6), (2.9, 12.0), (0.0, 12.0)):
        pmf = fch.half_count_pmf(mean, r)
        assert math.isclose(sum(pmf), 1.0, abs_tol=1e-9)
        assert math.isclose(sum(k * p for k, p in enumerate(pmf)), mean, abs_tol=1e-6)
    pois = fch.nb_pmf(1.5, 1e6, 3)
    assert math.isclose(pois[0], math.exp(-1.5), rel_tol=1e-5)


def test_card_half_p_is_consistent_across_markets() -> None:
    cen, share = (2.4, 2.0), 0.35
    a, b = fch.half_side_pmfs(*cen, share, 1)
    p_tot = fch.card_half_p(fch.CARDS_1H_TOTAL, None, "", 0.5, cen, share)
    assert p_tot is not None and math.isclose(p_tot, 1 - a[0] * b[0])
    p_side = fch.card_half_p(fch.CARDS_1H_FOR, "side_b", "x", 0.5, cen, share)
    assert p_side is not None and math.isclose(p_side, 1 - b[0])
    most = [fch.card_half_p(fch.MOST_1H, None, s, 0.0, cen, share)
            for s in ("1", "2", "__draw__")]
    assert all(m is not None for m in most)
    assert math.isclose(sum(m for m in most if m is not None), 1.0)
    # handicap -0.5 of a side = it shows more; +0.5 = not fewer
    h_minus = fch.card_half_p(fch.HCP_1H, "side_a", "x", -0.5, cen, share)
    h_plus = fch.card_half_p(fch.HCP_1H, "side_b", "x", 0.5, cen, share)
    assert h_minus is not None and h_plus is not None
    assert math.isclose(h_minus, most[0] or 0.0)
    assert math.isclose(h_minus + h_plus, 1.0)
    # unmeasured lines are not priced
    assert fch.card_half_p(fch.CARDS_1H_TOTAL, None, "", 4.5, cen, share) is None
    assert fch.card_half_p(fch.CARDS_1H_FOR, "side_a", "x", 2.5, cen, share) is None
    assert fch.card_half_p(fch.MOST_1H, None, "Getafe", 0.0, cen, share) is None


def _rates() -> fch.CardHalfRates:
    rates = fch.CardHalfRates()
    for i in range(fch.MIN_GENDER_MATCHES):
        rates.add_cards(2, False, ((1.0, 0.0), (1.0, 2.0)))  # share 1/4
        rates.add_events(2, False, (1 if i % 10 == 0 else 0, 0), (0, 0),
                         (0, 0), (0, 0))
    for _ in range(10):
        rates.add_cards(1, False, ((1.0, 1.0), (1.0, 1.0)))  # share 1/2
        rates.add_events(1, False, (1, 1), (1, 0), (1, 0), (0, 0))
    return rates


def test_rates_shrink_the_competition_toward_the_gender() -> None:
    rates = _rates()
    g = (fch.MIN_GENDER_MATCHES * 0.25 * 4 + 10 * 2) / (
        fch.MIN_GENDER_MATCHES * 4 + 10 * 4)
    s1 = rates.half_share(1, 1)
    assert s1 is not None
    assert math.isclose(s1, (10 * 0.5 + fch.SHARE_M * g) / (10 + fch.SHARE_M))
    s2 = rates.half_share(1, 2)
    assert s2 is not None and math.isclose(s1 + s2, 1.0)
    assert rates.half_share(99, 1) == pytest.approx(g)
    p = rates.p_over(fch.RED_FOR, 1, 0.5)
    assert p is not None and 0 < p < 1
    assert rates.p_over(fch.RED_FOR, 1, 2.5) is None
    assert rates.p_over(fch.BOTH_RED, 1, 0.5) is not None
    assert rates.n_comp(fch.RED_FOR, 1, 0.5) == 20  # two sides a match
    thin = fch.CardHalfRates()
    thin.add_cards(1, True, ((1.0, 0.0), (1.0, 0.0)))
    assert thin.half_share(1, 1) is None


def _forecast() -> fr.FootballForecast:
    history = []
    t = 0
    for i in range(fr.MIN_LEAGUE_MATCHES + 10):
        history.append(fr.FootballResult(
            i * 2, t, 2, 1, 100 + i,
            {"goals_for": (2.0, 1.0), "cards_points_for": (2.0, 3.0)}))
        history.append(fr.FootballResult(
            i * 2 + 1, t + 1, 2, 200 + i, 2,
            {"goals_for": (1.0, 1.0), "cards_points_for": (2.0, 2.0)}))
        t += 86400
    return fr.FootballForecast(fr.replay(history, cut_ts=10**9), 2, 1, 2,
                               rated_scope=fr.RATED_SCOPE_MARKETS)


def _fixture() -> Any:
    from tests.sofa.test_player_markets import _fixture as base

    return base().model_copy(update={"home_name": "Getafe",
                                     "away_name": "Rayo Vallecano",
                                     "competition_id": 2})


def _rung(market: str, subject: str, line: float, over: float | None,
          under: float | None) -> PricedRung:
    return PricedRung(market=market, subject=subject, line=line, over_odds=over,
                      under_odds=under,
                      fetched_at_utc=datetime(2026, 9, 22, tzinfo=UTC))


def test_card_half_rows_carry_the_model_p_and_no_price() -> None:
    fc, rates = _forecast(), _rates()
    rows, skipped = card_half_rows(
        _fixture(), _rung(fch.CARDS_1H_FOR, "Getafe", 0.5, 1.4, 2.7), fc, rates,
        {}, True)
    assert not skipped and [r.direction for r in rows] == ["OVER", "UNDER"]
    ca = fc.centre("cards_points_for", "side_a")
    share = rates.half_share(2, 1)
    assert ca is not None and share is not None
    a = fch.half_count_pmf(ca[0] * share, fch.HALF_NB_R[1])
    assert rows[0].p_central == pytest.approx(round(1 - a[0], 4))
    assert rows[0].incident_rule == epochs.FOOTBALL_CARD_HALVES
    assert rows[0].sample_size == 0
    assert any("UNFITTED_CONSTANTS" in n for n in rows[0].notes)
    most, _ = card_half_rows(
        _fixture(), _rung(fch.MOST_2H, "__draw__", 0.0, 4.5, None), fc, rates, {},
        True)
    assert [r.direction for r in most] == ["OVER"]
    ev, _ = card_half_rows(
        _fixture(), _rung(fch.RED_FOR, "Rayo Vallecano", 0.5, 6.0, 1.1), fc, rates,
        {}, True)
    assert len(ev) == 2 and ev[1].p_central == pytest.approx(
        round(1 - (rates.p_over(fch.RED_FOR, 2, 0.5) or 0), 4))
    none, why = card_half_rows(
        _fixture(), _rung(fch.CARDS_1H_FOR, "Real Madryt", 0.5, 1.4, 2.7), fc,
        rates, {}, True)
    assert not none and why[0][1] == GapReason.NO_MATCHING_EVENT
    unrated, why = card_half_rows(
        _fixture(), _rung(fch.CARDS_1H_TOTAL, "", 1.5, 1.8, 1.9), None, rates, {},
        True)
    assert not unrated and why[0][1] == GapReason.NOT_RATED


def test_derived_pass_leaves_a_rating_only_half_most_alone() -> None:
    from bet.sofa.contracts import FixtureSamples
    from bet.sofa.derived import price_derived_rungs

    offer = FixtureOffer(sofascore_event_id=1, status="PRICED",
                         unmapped_markets=[],
                         rungs=[_rung(fch.MOST_1H, "1", 0.0, 2.2, None)])
    samples = FixtureSamples(sofascore_event_id=1, readiness="READY", gaps=[],
                             metrics={})
    rows, skipped = price_derived_rungs(_fixture(), samples, offer, {}, [], 5,
                                        3.0, 1.0, [])
    assert rows == [] and skipped == []


def test_superbet_names_name_every_new_leg() -> None:
    sides = NAMES
    legs = [
        ({"market": fch.CARDS_1H_TOTAL, "direction": "UNDER", "line": 1.5},
         ("1. połowa - liczba kartek", "poniżej 1.5")),
        ({"market": fch.CARDS_2H_FOR, "subject": "getafe", "direction": "OVER",
          "line": 0.5}, ("2. połowa - Getafe liczba kartek", "powyżej 0.5")),
        ({"market": fch.RED_FOR, "subject": "rayo vallecano", "direction": "UNDER",
          "line": 0.5}, ("Liczba czerwonych kartek Rayo Vallecano", "poniżej 0.5")),
        ({"market": fch.PEN_1H_FOR, "subject": "getafe", "direction": "UNDER",
          "line": 0.5}, ("1.połowa - Getafe - liczba przyznanych rzutów karnych",
                         "poniżej 0.5")),
        ({"market": fch.MOST_1H, "subject": "__draw__", "direction": "OVER",
          "line": 0.0}, ("1. połowa - najwięcej kartek", "remis")),
        ({"market": fch.HCP_2H, "subject": "getafe", "direction": "OVER",
          "line": -0.5}, ("2. połowa - liczba kartek - handicap", "Getafe (-0.5)")),
        ({"market": fch.BOTH_RED, "subject": "", "direction": "UNDER", "line": 0.5},
         ("Obie drużyny otrzymają czerwoną kartkę", "Nie")),
    ]
    for leg, want in legs:
        assert _football_tennis(leg, sides) == want


def test_rates_from_a_history_match_read_the_same_reader() -> None:
    rates = fch.CardHalfRates()
    fch.add_match(rates, 3, False, INC, (1.0, 1.0), (3.0, 3.0))
    assert rates.share_comp[3].half1 == 3.0 and rates.share_comp[3].whole == 5.0
    assert rates.event_comp[(fch.BOTH_RED, 0.5, 3)].k == 1
    # a json round trip changes nothing (load_rates reads the cached text)
    rates2 = fch.CardHalfRates()
    fch.add_match(rates2, 3, False, json.loads(json.dumps(INC)), (1.0, 1.0),
                  (3.0, 3.0))
    assert rates2 == rates


def test_the_curve_replay_prices_with_sheets_estimator() -> None:
    from scripts.sofa.fit_incident_set_curves import card_half_keys, replay_card_halves
    from scripts.sofa.measure_football_card_halves import CardRec

    history, records = [], {}
    for i in range(fch.MIN_GENDER_MATCHES + 40):
        home, away = (1, 2) if i % 2 else (2, 1)
        history.append(fr.FootballResult(
            i, i * 86400, 5, home, away,
            {"goals_for": (1.0, 1.0), "cards_points_for": (2.0, 3.0)}))
        records[i] = CardRec(((1.0, 1.0), (1.0, 2.0)), None, 0, 0, 0, 0, 0, 5, True,
                             (0, 1), (0, 0), (1, 0), (0, 0))
    rows = replay_card_halves(history, records, 0, 10**10)
    keys = {r["key"] for r in rows}
    assert keys <= set(card_half_keys())
    assert "cards_points_1h_total|UNDER" in keys and "red_cards_for|UNDER" in keys
    # only earlier days in the rates: a card half is priced once the gender
    # holds MIN_GENDER_MATCHES matches, a side's event once it holds as many
    # side-matches (two a match)
    day = 86400
    assert min(r["ts"] for r in rows if r["market"].startswith("cards_points")) == (
        fch.MIN_GENDER_MATCHES * day)
    assert min(r["ts"] for r in rows if r["market"] == fch.RED_FOR) == (
        fch.MIN_GENDER_MATCHES // 2 * day)
    one = next(r for r in rows if r["key"] == "cards_points_1h_total|OVER"
               and r["line"] == 1.5)
    assert one["y"] == 1  # 1 + 1 > 1.5
