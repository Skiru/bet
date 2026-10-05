"""F4.1 (plan 2026-10-05 production grade): every pair of legs of one match
has a relation label, derived from the market map, and the implications are
the right way round."""

from __future__ import annotations

import itertools
from typing import Any

import pytest

from bet.sofa import leg_relations as lr
from bet.sofa.leg_relations import (
    DEPENDENT,
    INDEPENDENT_ASSUMED,
    RELATIONS,
    SAME_VARIABLE,
    SAME_VARIABLE_EXCLUSIVE,
    SAME_VARIABLE_IMPLIES,
    SAME_VARIABLE_OVERLAP,
    relate,
)
from bet.sofa.market_mapper import MATCH_MARKET_NAMES, TEAM_MARKET_PATTERNS


def _leg(market: str, line: float | None = 2.5, direction: str = "OVER",
         subject: str = "", sport: str | None = None, **kw: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"sofascore_event_id": 1, "market": market,
                           "subject": subject, "line": line, "direction": direction}
    if sport:
        out["sport"] = sport
    out.update(kw)
    return out


def _sheet_variants(sport: str, market: str) -> list[dict[str, Any]]:
    subj = "" if market.endswith("_total") else "home fc"
    if market.startswith("most_"):
        return [_leg(market, 0.0, "OVER", s, sport) for s in ("home fc", "__draw__")]
    if market.startswith("handicap_"):
        return [_leg(market, h, "OVER", "home fc", sport) for h in (-1.5, 1.5)]
    return [_leg(market, line, d, subj, sport)
            for line in (1.5, 2.5) for d in ("OVER", "UNDER")]


def _sport_variants(sport: str, family: str) -> list[dict[str, Any]]:
    base = {"sofascore_event_id": 1, "sport": sport, "family": family,
            "market": family, "period": 1 if "period" in family or "set_" in family
            or "quarter" in family or family.startswith("map_") else 0}
    if family.startswith("player_"):
        sides = [("OVER", 1.5, "a player"), ("UNDER", 2.5, "a player")]
    elif family in ("team_total", "period_team_total", "h1_team_total",
                    "h2_team_total", "quarter_team_total", "team_maps",
                    "team_rounds", "map_team_rounds", "team_kills"):
        sides = [("OVER", 2.5, "T1"), ("UNDER", 2.5, "T2")]
    elif "odd_even" in family:
        sides = [("ODD", None, ""), ("EVEN", None, "")]
    elif family.startswith("exact"):
        sides = [("3:1", None, ""), ("3:0", None, "")]
    elif family == "set_extra_points":
        sides = [("YES", None, ""), ("NO", None, "")]
    elif "1x2" in family:
        sides = [("T1", None, ""), ("DRAW", None, "")]
    elif "handicap" in family:
        sides = [("T1", 1.5, ""), ("T2", -1.5, "")]
    elif "winner" in family or "dnb" in family:
        sides = [("T1", None, ""), ("T2", None, "")]
    else:
        sides = [("OVER", 2.5, ""), ("UNDER", 5.5, "")]
    out = []
    for side, line, subject in sides:
        out.append({**base, "side": side, "direction": side, "line": line,
                    "subject": subject, "map_nr": base["period"]})
    return out


def test_the_market_map_is_covered_by_the_engine() -> None:
    """Every key the mapper can emit has a proposition - no market of the
    map falls through to 'not in the market map'."""
    names = {*MATCH_MARKET_NAMES.values(), *(m for _, m in TEAM_MARKET_PATTERNS)}
    keys = {m for _, m in lr.mapped_sheet_markets()}
    assert names <= keys
    for sport, market in lr.mapped_sheet_markets():
        for leg in _sheet_variants(sport, market):
            assert lr.proposition(leg) is not None, (sport, market)
    for sport, family in lr.mapped_sport_markets():
        for leg in _sport_variants(sport, family):
            assert lr.proposition(leg) is not None, (sport, family, leg)


def test_every_pair_of_market_keys_gets_a_label() -> None:
    """The criterion of F4.1: all pairs of market keys of one sport, every
    side / line variant, each labelled, none raising, none unlabelled."""
    by_sport: dict[str, list[dict[str, Any]]] = {}
    for sport, market in lr.mapped_sheet_markets():
        by_sport.setdefault(sport, []).extend(_sheet_variants(sport, market))
    for sport, family in lr.mapped_sport_markets():
        by_sport.setdefault(sport, []).extend(_sport_variants(sport, family))
    seen: dict[str, int] = {}
    n = 0
    for legs in by_sport.values():
        for a, b in itertools.combinations_with_replacement(legs, 2):
            rel = relate(a, b)
            assert rel.label in RELATIONS
            assert rel.reason
            assert "not in the market map" not in rel.reason
            # symmetric in its label
            assert relate(b, a).label == rel.label
            seen[rel.label] = seen.get(rel.label, 0) + 1
            n += 1
    assert n > 50_000
    assert set(seen) == set(RELATIONS)


@pytest.mark.parametrize("a,b,label,implies", [
    (("goals_total", 2.5, "UNDER"), ("goals_total", 3.5, "UNDER"),
     SAME_VARIABLE_IMPLIES, "a=>b"),
    (("goals_total", 1.5, "OVER"), ("goals_total", 2.5, "OVER"),
     SAME_VARIABLE_IMPLIES, "b=>a"),
    (("goals_total", 2.5, "OVER"), ("goals_total", 2.5, "OVER"),
     SAME_VARIABLE_IMPLIES, "equivalent"),
    (("goals_total", 2.5, "OVER"), ("goals_total", 2.5, "UNDER"),
     SAME_VARIABLE_EXCLUSIVE, None),
    (("goals_total", 3.5, "OVER"), ("goals_total", 2.5, "UNDER"),
     SAME_VARIABLE_EXCLUSIVE, None),
    (("goals_total", 1.5, "OVER"), ("goals_total", 3.5, "UNDER"),
     SAME_VARIABLE_OVERLAP, None),
    (("corners_total", 9.5, "OVER"), ("corners_total", 8.5, "UNDER"),
     SAME_VARIABLE_EXCLUSIVE, None),
    # 9 corners wins both
    (("corners_total", 8.5, "OVER"), ("corners_total", 9.5, "UNDER"),
     SAME_VARIABLE_OVERLAP, None),
])
def test_same_variable_rungs(a: tuple[Any, ...], b: tuple[Any, ...], label: str,
                             implies: str | None) -> None:
    rel = relate(_leg(a[0], a[1], a[2]), _leg(b[0], b[1], b[2]))
    assert rel.label == label
    assert rel.implies == implies


def test_over_and_under_of_one_line_are_complements() -> None:
    rel = relate(_leg("goals_total", 2.5, "OVER"), _leg("goals_total", 2.5, "UNDER"))
    assert rel.complement
    rel = relate(_leg("goals_total", 3.5, "OVER"), _leg("goals_total", 2.5, "UNDER"))
    assert not rel.complement  # 3 goals loses both


def test_a_side_is_its_own_variable() -> None:
    home = _leg("goals_for", 1.5, "UNDER", "Home FC")
    assert relate(home, _leg("goals_for", 2.5, "UNDER", "home fc")).label == (
        SAME_VARIABLE_IMPLIES)
    other = relate(home, _leg("goals_for", 1.5, "UNDER", "Away FC"))
    assert other.label == DEPENDENT
    assert "two sides" in other.reason


@pytest.mark.parametrize("a,b,needle", [
    (_leg("goals_total"), _leg("goals_for", subject="x"), "total and side"),
    (_leg("goals_total"), _leg("goals_2h_total"), "part of the period"),
    (_leg("corners_1h_total"), _leg("corners_total"), "part of the period"),
    (_leg("corners_total"), _leg("shots_total"), "corners follow"),
    (_leg("cards_points_total"), _leg("fouls_total"), "cards are given for fouls"),
    (_leg("shots_on_target_for", subject="x"), _leg("goals_total"), "shot on target"),
    (_leg("both_over_corners"), _leg("corners_for", subject="x"), "min and side"),
    (_leg("handicap_corners", -1.5, subject="x"), _leg("corners_total"),
     "diff and total"),
    (_leg("player_shots_for", 0.5, subject="a. player"), _leg("shots_for", subject="x"),
     "player and side"),
    (_leg("games_total", 21.5, sport="tennis"), _leg("sets_total", 2.5, sport="tennis"),
     "sets are won in games"),
    (_leg("games_won_for", 12.5, subject="a", sport="tennis"),
     _leg("games_total", 21.5, sport="tennis"), "side and total"),
    (_leg("games_set1_total", 9.5, sport="tennis"),
     _leg("games_total", 21.5, sport="tennis"), "part of the period"),
    (_leg("aces_total", 9.5, sport="tennis"),
     _leg("serve_points_total", 12.5, sport="tennis"), "the sum"),
])
def test_dependent_pairs(a: dict[str, Any], b: dict[str, Any], needle: str) -> None:
    rel = relate(a, b)
    assert rel.label == DEPENDENT, rel
    assert needle in rel.reason


def test_halves_of_one_count_are_assumed_independent() -> None:
    rel = relate(_leg("goals_1h_total"), _leg("goals_2h_total"))
    assert rel.label == INDEPENDENT_ASSUMED
    assert "assumed" in rel.reason


def test_unrelated_stats_are_assumed_not_independent() -> None:
    rel = relate(_leg("corners_total"), _leg("goals_total"))
    assert rel.label == INDEPENDENT_ASSUMED
    assert "assumed" in rel.reason


def test_a_third_set_depends_on_the_first_two() -> None:
    rel = relate(_leg("games_won_set1_for", 4.5, subject="a", sport="tennis"),
                 _leg("games_won_set3_for", 4.5, subject="a", sport="tennis"))
    assert rel.label == DEPENDENT


def test_most_and_handicap_are_one_difference() -> None:
    home_most = _leg("most_corners", 0.0, "OVER", "home fc")
    away_most = _leg("most_corners", 0.0, "OVER", "away fc")
    draw = _leg("most_corners", 0.0, "OVER", "__draw__")
    assert relate(home_most, away_most).label == SAME_VARIABLE_EXCLUSIVE
    assert relate(home_most, draw).label == SAME_VARIABLE_EXCLUSIVE
    # home -1.5 (home wins by 2+) implies home has more corners
    hcp = _leg("handicap_corners", -1.5, "OVER", "home fc")
    rel = relate(hcp, home_most)
    assert rel.label == SAME_VARIABLE_IMPLIES and rel.implies == "a=>b"
    # away +1.5 is the complement of home -1.5
    rel = relate(hcp, _leg("handicap_corners", 1.5, "OVER", "away fc"))
    assert rel.label == SAME_VARIABLE_EXCLUSIVE and rel.complement


def test_both_over_ladder() -> None:
    a = _leg("both_over_goals", 0.5, "OVER")
    b = _leg("both_over_goals", 1.5, "OVER")
    assert relate(b, a).implies == "a=>b"
    assert relate(a, _leg("both_over_goals", 0.5, "UNDER")).complement


def _sport(sport: str, family: str, side: str, line: float | None,
           subject: str = "", period: int = 0) -> dict[str, Any]:
    return {"sofascore_event_id": 1, "sport": sport, "family": family,
            "market": family, "side": side, "direction": side, "line": line,
            "subject": subject, "period": period}


def test_hockey_handicap_and_winner_sides() -> None:
    t1_plus = _sport("hockey", "handicap", "T1", 1.5)   # T1 - T2 > -1.5
    t2_minus = _sport("hockey", "handicap", "T2", 1.5)  # T1 - T2 < -1.5
    assert relate(t1_plus, t2_minus).label == SAME_VARIABLE_EXCLUSIVE
    assert relate(t1_plus, t2_minus).complement
    t1_minus = _sport("hockey", "handicap", "T1", -1.5)  # T1 wins by 2+
    assert relate(t1_minus, t1_plus).implies == "a=>b"
    # the regulation 1X2 is the regulation difference: T1 => T1 +1.5
    rel = relate(_sport("hockey", "result_1x2", "T1", None), t1_plus)
    assert rel.label == SAME_VARIABLE_IMPLIES
    # the winner counts overtime: a different period, DEPENDENT
    assert relate(_sport("hockey", "winner", "T1", None), t1_plus).label == DEPENDENT


def test_hockey_totals_and_team_totals() -> None:
    total = _sport("hockey", "total", "OVER", 3.5)
    t1 = _sport("hockey", "team_total", "OVER", 1.5, "T1")
    t2 = _sport("hockey", "team_total", "OVER", 1.5, "T2")
    assert relate(total, _sport("hockey", "total", "OVER", 4.5)).implies == "b=>a"
    assert relate(total, t1).label == DEPENDENT
    assert relate(t1, t2).label == DEPENDENT
    period = _sport("hockey", "period_total", "OVER", 1.5, period=1)
    assert "part of the period" in relate(total, period).reason


def test_volleyball_exact_scores_exclude_each_other() -> None:
    a = _sport("volleyball", "exact_sets", "3:0", None)
    b = _sport("volleyball", "exact_sets", "3:1", None)
    assert relate(a, b).label == SAME_VARIABLE_EXCLUSIVE
    assert relate(a, _sport("volleyball", "winner", "T1", None)).label == DEPENDENT


def test_cs2_map_and_series() -> None:
    m1 = {**_sport("cs2", "map_winner", "T1", None, period=1), "map_nr": 1}
    series = _sport("cs2", "match_winner", "T1", None)
    assert relate(m1, series).label == DEPENDENT
    kills = {**_sport("cs2", "player_kills", "OVER", 15.5, "s1mple", 1), "map_nr": 1}
    assert relate(m1, kills).label == DEPENDENT


def test_an_unmapped_market_is_labelled_assumed() -> None:
    rel = relate(_leg("not_a_market"), _leg("goals_total"))
    assert rel.label == INDEPENDENT_ASSUMED
    assert "not in the market map" in rel.reason


def test_match_relations_label_every_pair_of_a_match() -> None:
    legs = [
        {**_leg("goals_total", 2.5, "UNDER"), "position": 1, "match": "A - B"},
        {**_leg("goals_total", 3.5, "UNDER"), "position": 2, "match": "A - B"},
        {**_leg("corners_total", 9.5, "UNDER"), "position": 3, "match": "A - B"},
        {**_leg("goals_total", 2.5, "UNDER"), "sofascore_event_id": 2,
         "position": 4, "match": "C - D"},
    ]
    out = lr.match_relations(legs)
    assert len(out) == 1  # one leg on C - D: no pair
    pairs = out[0]["pairs"]
    assert len(pairs) == 3
    assert all(p["relation"] in RELATIONS for p in pairs)
    first = next(p for p in pairs
                 if p["a"]["position"] == 1 and p["b"]["position"] == 2)
    assert first["relation"] == SAME_VARIABLE_IMPLIES and first["implies"] == "a=>b"


def test_ladders_group_one_variable_of_one_match() -> None:
    legs = [
        _leg("goals_total", 2.5, "UNDER"),
        _leg("corners_total", 9.5, "UNDER"),
        _leg("goals_total", 1.5, "OVER"),
        _leg("goals_total", 3.5, "UNDER"),
        {**_leg("goals_total", 3.5, "UNDER"), "sofascore_event_id": 2},
    ]
    out = lr.ladders(legs)
    assert len(out) == 1
    assert out[0]["n_rungs"] == 3
    assert out[0]["over_under_pair"]
    assert set(lr.ladder_index(legs).values()) == {1}
    assert all(r in SAME_VARIABLE for r in (
        relate(legs[0], legs[2]).label, relate(legs[0], legs[3]).label))


def test_one_rung_keeps_the_highest_x_and_never_a_locked_leg() -> None:
    legs = [
        {**_leg("goals_total", 2.5, "UNDER"), "confidence": 0.80, "offered_odds": 1.20},
        {**_leg("goals_total", 3.5, "UNDER"), "confidence": 0.90, "offered_odds": 1.05},
        {**_leg("goals_total", 4.5, "UNDER"), "confidence": 0.95, "offered_odds": 1.01,
         "locked": True},
        {**_leg("corners_total", 9.5, "UNDER"), "confidence": 0.7, "offered_odds": 1.4},
    ]
    kept, dropped = lr.one_rung_per_variable(legs)
    assert [x["line"] for x in kept] == [2.5, 4.5, 9.5]
    assert [x["line"] for x in dropped] == [3.5]
    assert dropped[0]["refusal"] == "LADDER_FORM_ONE_RUNG"
