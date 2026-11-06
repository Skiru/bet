"""epochs.FOOTBALL_SIM: the football path markets wired to the
minute-by-minute simulator - OFFER mapping on real Superbet payload samples,
SETTLE grading edge cases (0-0, an own goal, a penalty, added time, extra
time, contradictions), SHEET pricing, the curves overlay and the gates that
must not move."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import numpy as np
import pytest

from bet.sofa import epochs
from bet.sofa import football_sim_curves as fsc
from bet.sofa import football_sim_markets as fsm
from bet.sofa import football_sim_sheet as fss
from bet.sofa.football_sim import (
    Centres,
    MarketSim,
    MinuteMatch,
    neutral_params,
    path_actual,
    path_outcomes,
    simulate,
)

SIDES = ("Churchill Brothers", "Northeast United")

# Real (marketName, name) pairs of Superbet event 15202205, Churchill
# Brothers - Northeast United, runs/sofa/2026-11-05/unmapped_prices.
REAL = [
    (("1. połowa/mecz", "1/1"), ("htft", "1/1", 0.5, "OVER")),
    (("1. połowa/mecz", "X/2"), ("htft", "X/2", 0.5, "OVER")),
    (("1. połowa/mecz", "2/X"), ("htft", "2/X", 0.5, "OVER")),
    (("1.połowa - 1X2", "Churchill Brothers"), ("result_1h", "1", 0.5, "OVER")),
    (("1.połowa - 1X2", "remis"), ("result_1h", "X", 0.5, "OVER")),
    (("2.połowa - 1X2", "Northeast United"), ("result_2h", "2", 0.5, "OVER")),
    (("Połowa z większą liczbą goli", "1.Połowa"),
     ("higher_scoring_half", "1H", 0.5, "OVER")),
    (("Połowa z większą liczbą goli", "remis"),
     ("higher_scoring_half", "X", 0.5, "OVER")),
    (("Połowa z większą liczbą goli", "2.Połowa"),
     ("higher_scoring_half", "2H", 0.5, "OVER")),
    (("Churchill Brothers zdobędzie gola w obu połowach", "tak"),
     ("team_scores_both_halves", "1", 0.5, "OVER")),
    (("Northeast United zdobędzie gola w obu połowach", "nie"),
     ("team_scores_both_halves", "2", 0.5, "UNDER")),
    (("Obie drużyny strzelą gola - 1.połowa/2.połowa", "Tak/Nie"),
     ("btts_halves", "Tak/Nie", 0.5, "OVER")),
    (("Obie drużyny strzelą gola - 1.połowa/2.połowa", "Nie/Nie"),
     ("btts_halves", "Nie/Nie", 0.5, "OVER")),
    (("Obie drużyny strzelą w przynajmniej jednej połowie meczu", "tak"),
     ("btts_any_half", "", 0.5, "OVER")),
    (("Obie drużyny strzelą w przynajmniej jednej połowie meczu", "nie"),
     ("btts_any_half", "", 0.5, "UNDER")),
    (("1. połowa - 1. gol", "Northeast United"), ("first_goal_1h", "2", 0.5, "OVER")),
    (("1. połowa - 1. gol", "nikt"), ("first_goal_1h", "nikt", 0.5, "OVER")),
    (("1.połowa liczba goli & 2.połowa liczba goli", "poniżej 0.5 & powyżej 1.5"),
     ("half_goals_combo", "U0.5/O1.5", 0.5, "OVER")),
    (("1.połowa liczba goli & 2.połowa liczba goli", "powyżej 1.5 & poniżej 2.5"),
     ("half_goals_combo", "O1.5/U2.5", 0.5, "OVER")),
]

# Real names of the same event that are other questions: never read.
NOT_READ = [
    ("Gol w obu połowach", "Tak"),
    ("1. połowa/mecz - podwójna szansa", "1/1 lub X/1"),
    ("1. połowa/mecz & liczba goli (2.5)", "1/1 & Poniżej 2.5"),
    ("Churchill Brothers wygra jedną z połów; Churchill Brothers strzeli w obu "
     "połowach", "Churchill Brothers wygra jedną z połów; Churchill Brothers "
     "strzeli w obu połowach"),
    ("Palmeiras - 1.połowa liczba goli & 2.połowa liczba goli",
     "poniżej 0.5 & poniżej 0.5"),
    ("1. gol (przedziały 15-minutowe)", "0:00 - 14:59 minuty"),
]


@pytest.mark.parametrize(("item", "want"), REAL)
def test_offer_maps_the_real_superbet_names(item: tuple[str, str],
                                            want: tuple[str, str, float, str]) -> None:
    assert fsm.classify(item[0], item[1], SIDES) == want


@pytest.mark.parametrize("item", NOT_READ)
def test_other_questions_are_not_read(item: tuple[str, str]) -> None:
    assert fsm.classify(item[0], item[1], SIDES) is None


def test_a_team_selection_needs_an_exact_listing_name() -> None:
    assert fsm.classify("1.połowa - 1X2", "Churchill", SIDES) is None
    assert fsm.classify("1. połowa - 1. gol", "Churchill Brothers", ()) is None
    assert fsm.classify("1.połowa - 1X2", "X", SIDES, ) is None


def test_offer_reads_them_only_under_the_switch() -> None:
    from bet.sofa.offer import classify_odd, day_flags

    item = {"marketName": "1. połowa/mecz", "name": "X/1", "price": 4.3}
    off, label = classify_odd(item, listing_names=SIDES)
    assert off is None and label == "1. połowa/mecz"
    on, _ = classify_odd(item, listing_names=SIDES, football_sim=True)
    assert on == ("htft", "X/1", 0.5, "OVER")
    assert day_flags("2026-11-06")["football_sim"] is False
    assert epochs.FOOTBALL_SIM_FROM_UTC == datetime(2026, 11, 7, tzinfo=UTC)
    assert epochs.football_sim("2026-11-07", datetime(2026, 11, 7, 1, tzinfo=UTC))
    assert not epochs.football_sim("2026-11-06", datetime(2026, 11, 7, 1, tzinfo=UTC))


def test_superbet_words_round_trip_through_classify() -> None:
    from bet.sofa.superbet_names import names

    for (market_name, selection), (market, subject, line, direction) in REAL:
        words = fsm.superbet_words(market, subject, direction, SIDES)
        assert words is not None
        assert fsm.classify(words[0], words[1], SIDES) == (
            market, subject, line, direction)
        leg = {"sport": "football", "market": market, "subject": subject,
               "line": line, "direction": direction}
        assert names(leg, SIDES) == words
    assert fsm.superbet_words("result_1h", "1", "OVER", None) is None


# --- SETTLE ---------------------------------------------------------------------


def _event(ht: tuple[int, int], ft: tuple[int, int], code: int = 100,
           normal: tuple[int, int] | None = None) -> dict[str, Any]:
    nt = normal or ft
    return {
        "status": {"code": code, "type": "finished"},
        "homeScore": {"current": ft[0], "period1": ht[0], "period2": nt[0] - ht[0],
                      "normaltime": nt[0]},
        "awayScore": {"current": ft[1], "period1": ht[1], "period2": nt[1] - ht[1],
                      "normaltime": nt[1]},
    }


def _goal(time: int, hs: int, as_: int, cls: str = "regular",
          added: int | None = None) -> dict[str, Any]:
    g: dict[str, Any] = {"incidentType": "goal", "incidentClass": cls,
                         "time": time, "homeScore": hs, "awayScore": as_,
                         "isHome": True}
    if added is not None:
        g["addedTime"] = added
    return g


def _inc(*goals: dict[str, Any], ht: tuple[int, int] | None = None
         ) -> dict[str, Any]:
    lst = list(goals)
    if ht is not None:
        lst.append({"incidentType": "period", "text": "HT", "homeScore": ht[0],
                    "awayScore": ht[1], "time": 45})
    return {"incidents": lst}


def test_goalless_match() -> None:
    ev = _event((0, 0), (0, 0))
    assert fsm.sim_value("first_goal_1h", "nikt", ev, None) == 1.0
    assert fsm.sim_value("first_goal_1h", "1", ev, None) == 0.0
    assert fsm.sim_value("htft", "X/X", ev, None) == 1.0
    assert fsm.sim_value("higher_scoring_half", "X", ev, None) == 1.0
    assert fsm.sim_value("btts_any_half", "", ev, None) == 0.0
    assert fsm.sim_value("btts_halves", "Nie/Nie", ev, None) == 1.0
    assert fsm.sim_value("half_goals_combo", "U0.5/U0.5", ev, None) == 1.0
    assert fsm.sim_value("team_scores_both_halves", "1", ev, None) == 0.0


def test_an_own_goal_counts_for_the_credited_side() -> None:
    # 1H 1-1: an away player's own goal at 10' (home score goes up), then
    # the away side at 30'; 2H home 1 more -> 2-1
    inc = _inc(_goal(10, 1, 0, "ownGoal"), _goal(30, 1, 1), _goal(70, 2, 1),
               ht=(1, 1))
    ev = _event((1, 1), (2, 1))
    assert fsm.sim_value("first_goal_1h", "1", ev, inc) == 1.0
    assert fsm.sim_value("htft", "X/1", ev, inc) == 1.0
    assert fsm.sim_value("team_scores_both_halves", "1", ev, inc) == 1.0
    assert fsm.sim_value("team_scores_both_halves", "2", ev, inc) == 0.0
    assert fsm.sim_value("btts_halves", "Tak/Nie", ev, inc) == 1.0
    assert fsm.sim_value("result_2h", "1", ev, inc) == 1.0


def test_a_penalty_is_a_goal_and_first_half_added_time_is_the_first_half() -> None:
    # away penalty at 45+2 (1H), home at 46' (2H)
    inc = _inc(_goal(45, 0, 1, "penalty", added=2), _goal(46, 1, 1), ht=(0, 1))
    ev = _event((0, 1), (1, 1))
    assert fsm.sim_value("first_goal_1h", "2", ev, inc) == 1.0
    assert fsm.sim_value("result_1h", "2", ev, inc) == 1.0
    assert fsm.sim_value("result_2h", "1", ev, inc) == 1.0
    assert fsm.sim_value("htft", "2/X", ev, inc) == 1.0
    assert fsm.sim_value("higher_scoring_half", "X", ev, inc) == 1.0


def test_second_half_added_time_counts_and_extra_time_does_not() -> None:
    # 90+4 winner counts; after extra time (code 110) the 90-minute score
    ev = _event((0, 0), (1, 0))
    inc = _inc(_goal(90, 1, 0, added=4), ht=(0, 0))
    assert fsm.sim_value("htft", "X/1", ev, inc) == 1.0
    aet = _event((1, 0), (2, 1), code=110, normal=(1, 1))
    aet["homeScore"]["overtime"] = 1
    assert fsm.sim_value("htft", "1/X", aet, None) == 1.0
    assert fsm.sim_value("result_2h", "2", aet, None) == 1.0


def test_first_goal_of_the_first_half_needs_the_list_when_both_scored() -> None:
    ev = _event((1, 1), (1, 1))
    assert fsm.sim_value("first_goal_1h", "1", ev, None) == (
        "FIRST_GOAL_UNREADABLE")
    # the score markets still grade without the list
    assert fsm.sim_value("htft", "X/X", ev, None) == 1.0
    inc = _inc(_goal(5, 0, 1), _goal(40, 1, 1), ht=(1, 1))
    assert fsm.sim_value("first_goal_1h", "2", ev, inc) == 1.0
    # a list that puts another number of goals in the first half: no grade
    bad = _inc(_goal(5, 0, 1), _goal(50, 1, 1))
    assert fsm.sim_value("first_goal_1h", "2", _event((1, 0), (1, 1)), bad) == (
        "FIRST_GOAL_UNREADABLE")


def test_contradictions_are_refused_never_guessed() -> None:
    no_ht = _event((0, 0), (1, 0))
    del no_ht["homeScore"]["period1"]
    assert fsm.sim_value("htft", "X/1", no_ht, None) == "NO_HALF_TIME_SCORE"
    above = _event((2, 0), (1, 0))
    above["homeScore"]["period2"] = None
    assert fsm.sim_value("htft", "1/1", above, None) == "HALF_ABOVE_MATCH"
    inconsistent = _event((0, 0), (1, 0))
    inconsistent["homeScore"]["period2"] = 3
    assert fsm.sim_value("htft", "X/1", inconsistent, None) == (
        "INTERNAL_INCONSISTENT")
    ev = _event((0, 0), (1, 0))
    marker = _inc(_goal(60, 1, 0), ht=(1, 0))
    assert fsm.sim_value("htft", "X/1", ev, marker) == "HALF_TIME_DISAGREES"
    assert fsm.sim_value("htft", "3/1", ev, None) == "UNKNOWN_SUBJECT"
    assert fsm.sim_value("goals_total", "", ev, None) == "NOT_A_SIM_MARKET"


def test_settle_and_regrade_grade_the_rows() -> None:
    from scripts.sofa.run_settle import _settle_sim_market

    ev = _event((0, 1), (2, 1))
    row = {"market": "htft", "subject": "2/1", "line": 0.5, "direction": "OVER"}
    assert _settle_sim_market(row, ev, None) == (1.0, "WIN")
    row = {"market": "btts_any_half", "subject": "", "line": 0.5,
           "direction": "UNDER"}
    assert _settle_sim_market(row, ev, None) == (0.0, "WIN")
    row = {"market": "first_goal_1h", "subject": "1", "line": 0.5,
           "direction": "OVER"}
    assert _settle_sim_market(row, ev, None) == (0.0, "LOSS")
    bad = {"market": "htft", "subject": "9/9", "line": 0.5, "direction": "OVER"}
    assert _settle_sim_market(bad, ev, None) == "htft:UNKNOWN_SUBJECT"


# --- the simulator's events agree with SETTLE's ---------------------------------


def _minute(ht: tuple[int, int], ft: tuple[int, int],
            goals: tuple[tuple[int, int, int], ...]) -> MinuteMatch:
    return MinuteMatch(event_id=1, ts=0, competition_id=1, home_id=1, away_id=2,
                       women=False, ft=ft, ht=ht, goals=goals, reds=(),
                       added=(None, None))


SUBJECTS: list[tuple[str, str, str]] = [
    *((fsm.HTFT, s, "OVER") for s in fsm.HTFT_SUBJECTS),
    *((m, s, "OVER") for m in (fsm.RESULT_1H, fsm.RESULT_2H)
      for s in fsm.RESULT_SUBJECTS),
    *((fsm.HIGHER_HALF, s, "OVER") for s in fsm.HALF_SUBJECTS),
    *((fsm.TEAM_BOTH_HALVES, s, d) for s in fsm.SIDE_SUBJECTS
      for d in ("OVER", "UNDER")),
    *((fsm.BTTS_HALVES, s, "OVER") for s in fsm.BTTS_HALVES_SUBJECTS),
    *((fsm.BTTS_ANY_HALF, "", d) for d in ("OVER", "UNDER")),
    *((fsm.FIRST_GOAL_1H, s, "OVER") for s in fsm.FG1H_SUBJECTS),
    *((fsm.HALF_GOALS_COMBO, f"{a}{x}/{b}{y}", "OVER")
      for a in "OU" for b in "OU" for x in ("0.5", "1.5") for y in ("0.5", "2.5")),
]


@pytest.mark.parametrize(("ht", "ft", "goals"), [
    ((0, 0), (0, 0), ()),
    ((1, 1), (2, 1), ((1, 3, 1), (1, 20, 0), (2, 10, 0))),
    ((0, 2), (3, 2), ((1, 1, 1), (1, 44, 1), (2, 0, 0), (2, 5, 0), (2, 46, 0))),
    ((2, 0), (2, 0), ((1, 1, 0), (1, 2, 0))),
])
def test_settle_grades_as_the_simulator_reads(
        ht: tuple[int, int], ft: tuple[int, int],
        goals: tuple[tuple[int, int, int], ...]) -> None:
    """path_holds (SETTLE) and football_sim.path_actual (the measurement)
    name the same winning outcome for every subject."""
    m = _minute(ht, ft, goals)
    first = None
    if goals and goals[0][0] == 1:
        first = "1" if goals[0][2] == 0 else "2"
    elif sum(ht) == 0:
        first = "nikt"
    for market, subject, direction in SUBJECTS:
        spec = fsm.path_spec(market, subject, direction)
        assert spec is not None, (market, subject, direction)
        kind, param, outcome = spec
        held = fsm.path_holds(market, subject, ht, ft, first)
        assert held is not None
        if direction == "UNDER":
            held = not held
        assert (path_actual(m, kind, param) == outcome) == held, (
            market, subject, direction)


def test_pricer_is_seeded_and_the_outcomes_add_up() -> None:
    params = neutral_params()
    c = Centres(goals=(1.6, 1.1), halves={}, cards=None)
    pricer = fss.SimPricer(params, sims=2000)
    a = pricer.p(17000001, c, "htft", "1/1", "OVER")
    pricer.forget(17000001)
    assert a == fss.SimPricer(params, sims=2000).p(17000001, c, "htft", "1/1", "OVER")
    assert sum(pricer.p(7, c, "htft", s, "OVER") or 0.0
               for s in fsm.HTFT_SUBJECTS) == pytest.approx(1.0)
    assert sum(pricer.p(7, c, "first_goal_1h", s, "OVER") or 0.0
               for s in fsm.FG1H_SUBJECTS) == pytest.approx(1.0)
    over = pricer.p(7, c, "btts_any_half", "", "OVER")
    under = pricer.p(7, c, "btts_any_half", "", "UNDER")
    assert over is not None and under is not None
    assert over + under == pytest.approx(1.0)
    assert pricer.p(7, c, "htft", "1/1", "UNDER") is None  # one-sided
    # the same paths as the measurement's simulate(..., seed = eid % 2**31)
    ms = MarketSim(simulate(params, c, n=2000, seed=fss.seed_of(7)))
    want = float(np.mean(path_outcomes(ms, "half_result", 2)["X"]))
    assert pricer.p(7, c, "result_2h", "X", "OVER") == want


class _Rating:
    def __init__(self, values: dict[tuple[str, str], float]) -> None:
        self.values = values

    def centre(self, market: str, side: str | None) -> tuple[float, str] | None:
        v = self.values.get((market, str(side)))
        return None if v is None else (v, "note")

    def fixture_link(self) -> str:
        return "LINKED"


def test_centres_come_from_the_sheet_rating() -> None:
    r = _Rating({("goals_for", "side_a"): 1.5, ("goals_for", "side_b"): 0.9,
                 ("cards_points_for", "side_a"): 2.0,
                 ("cards_points_for", "side_b"): 2.4})
    c = fss.centres_of(r)
    assert c is not None and c.goals == (1.5, 0.9) and c.cards == (2.0, 2.4)
    assert fss.centres_of(_Rating({("goals_for", "side_a"): 1.5})) is None
    assert fss.centres_of(None) is None


def test_sheet_rows_carry_the_marker_and_refuse_without_a_rating() -> None:
    from bet.sofa.contracts import Fixture, PricedRung
    from scripts.sofa.run_sheet import sim_rows

    fx = Fixture(
        sofascore_event_id=123, superbet_event_ids=["9"], sport="football",
        kickoff_utc=datetime(2026, 11, 7, 15, tzinfo=UTC), home_name="A",
        away_name="B", home_entity_id=1, away_entity_id=2,
        competition_name="Premier League", competition_id=17, season_id=4,
        category_name="England", identity="CONFIRMED", round_number=None,
        round_name=None, cup_round_type=None, previous_leg_event_id=None,
        venue_name=None, referee=None, ground_type=None, default_period_count=2,
    )
    rating = _Rating({("goals_for", "side_a"): 1.5, ("goals_for", "side_b"): 0.9})
    pricer = fss.SimPricer(neutral_params(), sims=1000)
    one = PricedRung(market="htft", subject="1/1", line=0.5, over_odds=3.1,
                     under_odds=None,
                     fetched_at_utc=datetime(2026, 11, 7, 9, tzinfo=UTC))
    rows, skipped = sim_rows(fx, one, rating, pricer, {}, True)  # type: ignore[arg-type]
    assert skipped == [] and len(rows) == 1
    assert rows[0].direction == "OVER"
    assert rows[0].football_sim_rule == epochs.FOOTBALL_SIM
    assert rows[0].sample_size == 0
    assert any(n.startswith("FOOTBALL_SIM:") for n in rows[0].notes)
    two = PricedRung(market="btts_any_half", subject="", line=0.5, over_odds=1.9,
                     under_odds=1.8,
                     fetched_at_utc=datetime(2026, 11, 7, 9, tzinfo=UTC))
    rows, _ = sim_rows(fx, two, rating, pricer, {}, True)  # type: ignore[arg-type]
    assert [r.direction for r in rows] == ["OVER", "UNDER"]
    assert rows[0].p_central + rows[1].p_central == pytest.approx(1.0, abs=2e-4)
    rows, skipped = sim_rows(fx, one, None, pricer, {}, True)
    assert rows == [] and skipped[0][1].value == "NOT_RATED"


# --- CONFIDENCE: curves overlay and the gates that do not move ------------------


def test_curves_overlay_only_under_the_switch(tmp_path: Any) -> None:
    from bet.sofa.confidence import Calibration

    cal = Calibration.load()
    doc = {"by_market_direction": {"htft|OVER": {"0.700-0.750": {
        "n": 500, "realised": 0.73, "realised_lo95": 0.70}},
        "goals_total|OVER": {"0.700-0.750": {"n": 9, "realised": 0.0,
                                             "realised_lo95": 0.0}}},
        "by_class": {"women": {"by_market_direction": {}}}}
    path = tmp_path / "c.json"
    path.write_text(__import__("json").dumps(doc))
    off = fsc.for_day(cal, "2026-11-06", datetime(2026, 11, 6, 12, tzinfo=UTC),
                      path)
    assert off is cal
    on = fsc.for_day(cal, "2026-11-07", datetime(2026, 11, 7, 1, tzinfo=UTC), path)
    assert on.by_market_direction["htft|OVER"]["0.700-0.750"]["n"] == 500
    # an out-of-scope key of the file is never read
    assert on.by_market_direction.get("goals_total|OVER") == (
        cal.by_market_direction.get("goals_total|OVER"))
    assert "htft" in on.no_pool_keys and "result_1h" in on.no_pool_keys


def test_print_gates_do_not_move_for_the_new_keys() -> None:
    from bet.sofa.tennis_winner import RATING_ONLY_MARKETS

    at = datetime(2026, 11, 7, 12, tzinfo=UTC)
    for market in epochs.FOOTBALL_SIM_MARKETS:
        leg = {"sport": "football", "market": market}
        assert epochs.leg_floor(leg, "2026-11-07", 0.70, at) == 0.70
        assert market in RATING_ONLY_MARKETS  # no sample, never a builder
    assert fsm.MARKETS == epochs.FOOTBALL_SIM_MARKETS


def test_line_evidence_backfill_rows_stop_at_the_switch() -> None:
    from bet.sofa.confidence import Calibration

    cal = fsc.overlay(Calibration.load(), {})
    lines = [
        {"day": "2026-10-20", "eid": 1, "market": "btts_any_half", "subject": "",
         "direction": "UNDER", "p": 0.7, "y": 1, "odds": 1.4, "klass": None},
        {"day": "2026-11-07", "eid": 2, "market": "btts_any_half", "subject": "",
         "direction": "UNDER", "p": 0.7, "y": 0, "odds": 1.4, "klass": None},
    ]
    rows = list(fsc.backfill_rows(lines, "2026-11-08", cal, "2026-11-07"))
    assert [r["game"] for r in rows] == ["2026-10-20:1"]
    assert rows[0]["key"] == "btts_any_half|UNDER" and rows[0]["base"] is None
    assert fsc.ours("women:htft|OVER") and not fsc.ours("goals_total|OVER")
    fitted: dict[str, Any] = {"keys": {"football": {"htft|OVER": 1,
                                                    "goals_total|OVER": 2}},
                              "bands": {"football": {"htft|OVER": 1}}}
    fsc.merge_evidence(fitted, {"keys": {"football": {"result_1h|OVER": 3,
                                                      "goals_total|OVER": 9}}})
    assert fitted["keys"]["football"] == {"goals_total|OVER": 2,
                                          "result_1h|OVER": 3}
    assert fitted["bands"]["football"] == {}
