# ruff: noqa: E501  - Superbet names and graded rows quoted whole read better unwrapped.
"""MAPPABLE families behind epochs.MAPPABLE_FAMILIES_FROM_UTC (night plan
2026-10-12, C1).

Names, selections and specialBetValues are Superbet's own, from two real
events fetched 2026-10-12 (tests/sofa/golden/offer_mappable_items.json) and
the 2026-10-12 board's unmapped_markets (runs/sofa/2026-10-12/04_offer.json):

    "Villarreal strzeli gola"                 tak / nie       (182 on 10-12)
    "1.połowa - Napoli strzeli gola"          tak / nie       (364)
    "1.połowa - obie drużyny strzelą"         tak / nie       (182)
    "Zostanie rozegrany 3. set"               Tak / Nie, "3"  (49)
    "1. set - handicap gemy"                  "Alexander Zverev (-1.5)", "-1.5-1" (98)
    "Każda z drużyn powyżej X obronionych strzałów przez bramkarza"
                                              "Powyżej 1.5 - tak", "1.5" (16, half 4)
    "1. połowa - rzuty rożne - handicap"      "Villarreal (-0.5)", "-0.5" (8)
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest

from bet.sofa import epochs
from bet.sofa.confidence import overround
from bet.sofa.contracts import FixtureOffer
from bet.sofa.market_mapper import classify_mappable_family, is_ladder_answer
from bet.sofa.metrics import extract_metric
from bet.sofa.offer import OfferFetcher, classify_odd
from bet.sofa.samples import metrics_from_offer
from bet.sofa.settle import settle as settle_value
from scripts.sofa.run_settle import _settle_derived
from tests.sofa.offer_mappable_scenarios import (
    FROZEN,
    GOLDEN_DIR,
    dumps,
    fixture,
    offer_dump,
)

FOOTBALL = ("Villarreal", "Napoli")
TENNIS = ("Alexander Zverev", "Alexander Bublik")


# --- the switch ------------------------------------------------------------


def test_the_switch_is_on_from_10_14_by_the_operator() -> None:
    assert epochs.MAPPABLE_FAMILIES_FROM_UTC == datetime(2026, 10, 14, tzinfo=UTC)
    assert not epochs.mappable_families("2026-10-13", datetime(2026, 10, 13, 12, tzinfo=UTC))
    assert epochs.mappable_families("2026-10-14", datetime(2026, 10, 14, 1, tzinfo=UTC))


def test_the_switch_is_judged_on_the_day_built_and_the_clock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        epochs, "MAPPABLE_FAMILIES_FROM_UTC", datetime(2026, 10, 13, tzinfo=UTC)
    )
    before = datetime(2026, 10, 12, 23, 59, tzinfo=UTC)
    at = datetime(2026, 10, 13, 0, 0, tzinfo=UTC)
    assert not epochs.mappable_families("2026-10-12", at)
    assert not epochs.mappable_families("2026-10-13", before)
    assert epochs.mappable_families("2026-10-13", at)


def test_with_the_switch_off_offer_is_byte_identical_to_before() -> None:
    """The golden is OFFER's output at 40b42923, before the switch existed."""
    golden = (GOLDEN_DIR / "offer_mappable_off.json").read_text(encoding="utf-8")
    assert dumps(offer_dump(False)) + "\n" == golden
    # And the default (no keyword, as every caller before the switch).
    assert dumps(offer_dump(None)) + "\n" == golden


def test_with_the_switch_off_classify_odd_leaves_every_family_unmapped() -> None:
    for item in _ITEMS:
        assert classify_odd(item) == (None, item["marketName"])
        assert classify_odd(item, FOOTBALL, False, FOOTBALL) == (None, item["marketName"])


# --- one test per name template ----------------------------------------------


@pytest.mark.parametrize(
    ("market", "selection", "sbv", "sides", "expected"),
    [
        # "<club> strzeli gola": goals_for at 0.5; team 1 and team 2.
        ("Villarreal strzeli gola", "tak", None, FOOTBALL,
         ("goals_for", "villarreal", 0.5, "OVER")),
        ("Villarreal strzeli gola", "nie", None, FOOTBALL,
         ("goals_for", "villarreal", 0.5, "UNDER")),
        ("Napoli strzeli gola", "tak", None, FOOTBALL,
         ("goals_for", "napoli", 0.5, "OVER")),
        # Halves, with and without the space Superbet sometimes writes.
        ("1.połowa - Napoli strzeli gola", "tak", None, FOOTBALL,
         ("goals_1h_for", "napoli", 0.5, "OVER")),
        ("1. połowa - Villarreal strzeli gola", "nie", None, FOOTBALL,
         ("goals_1h_for", "villarreal", 0.5, "UNDER")),
        ("2.połowa - Villarreal strzeli gola", "nie", None, FOOTBALL,
         ("goals_2h_for", "villarreal", 0.5, "UNDER")),
        ("2.połowa - Napoli strzeli gola", "tak", None, FOOTBALL,
         ("goals_2h_for", "napoli", 0.5, "OVER")),
        # "Zostanie rozegrany N. set": the match lasts N sets = sets_total
        # over N - 0.5, for a best-of-3 and a best-of-5 alike.
        ("Zostanie rozegrany 3. set", "Tak", "3", TENNIS,
         ("sets_total", "", 2.5, "OVER")),
        ("Zostanie rozegrany 3. set", "Nie", "3", TENNIS,
         ("sets_total", "", 2.5, "UNDER")),
        ("Zostanie rozegrany 5. set", "Tak", "5", TENNIS,
         ("sets_total", "", 4.5, "OVER")),
        ("Zostanie rozegrany 4. set", "Nie", "4", TENNIS,
         ("sets_total", "", 3.5, "UNDER")),
        # Both teams score in a half.
        ("1.połowa - obie drużyny strzelą", "tak", None, FOOTBALL,
         ("both_over_goals_1h", "", 0.5, "OVER")),
        ("2.połowa - obie drużyny strzelą", "nie", None, FOOTBALL,
         ("both_over_goals_2h", "", 0.5, "UNDER")),
        # Both goalkeepers over X saves; the line is the specialBetValue.
        ("Każda z drużyn powyżej X obronionych strzałów przez bramkarza",
         "Powyżej 1.5 - tak", "1.5", FOOTBALL, ("both_over_saves", "", 1.5, "OVER")),
        ("1. połowa - każda z drużyn powyżej X obronionych strzałów przez bramkarza",
         "Powyżej 0.5 - tak", "0.5", FOOTBALL, ("both_over_saves_1h", "", 0.5, "OVER")),
        # Corner handicap in a half: the selection carries its own side and line.
        ("1. połowa - rzuty rożne - handicap", "Villarreal (-0.5)", "-0.5", FOOTBALL,
         ("handicap_corners_1h", "villarreal", -0.5, "OVER")),
        ("1. połowa - rzuty rożne - handicap", "Napoli (0.5)", "-0.5", FOOTBALL,
         ("handicap_corners_1h", "napoli", 0.5, "OVER")),
        ("2. połowa - rzuty rożne - handicap", "Napoli (0.5)", "-0.5", FOOTBALL,
         ("handicap_corners_2h", "napoli", 0.5, "OVER")),
        # Games handicap in a set: "-1.5-1" is the line, then the set.
        ("1. set - handicap gemy", "Alexander Zverev (-1.5)", "-1.5-1", TENNIS,
         ("handicap_games_won_set1", "alexander zverev", -1.5, "OVER")),
        ("1. set - handicap gemy", "Alexander Bublik (1.5)", "-1.5-1", TENNIS,
         ("handicap_games_won_set1", "alexander bublik", 1.5, "OVER")),
        ("2. set - handicap gemy", "Alexander Bublik (-1.5)", "1.5-2", TENNIS,
         ("handicap_games_won_set2", "alexander bublik", -1.5, "OVER")),
    ],
)
def test_each_template_maps_to_its_subject_line_and_direction(
    market: str, selection: str, sbv: str | None, sides: tuple[str, str],
    expected: tuple[str, str, float, str],
) -> None:
    assert classify_mappable_family(market, selection, sbv, sides) == expected
    item = {"marketName": market, "name": selection, "specialBetValue": sbv, "price": 1.9}
    assert classify_odd(item, (), True, sides) == (expected, None)


@pytest.mark.parametrize(
    ("market", "selection", "sbv", "sides"),
    [
        # A player shares the club's shape: only a listing side is a subject.
        ("Georges Mikautadze strzeli gola", "tak", None, FOOTBALL),
        ("Zawodnik rezerwowy strzeli gola", "Tak", None, FOOTBALL),
        ("Zawodnik - strzeli gola", "Zeno Debast", None, FOOTBALL),
        ("Którykolwiek z zawodników strzeli gola", "tak", None, FOOTBALL),
        # No listing names known: nothing is guessed.
        ("Villarreal strzeli gola", "tak", None, ()),
        # A Superbet combination is never one statistic.
        ("Gol w obu polowach; Villarreal strzeli gola", "tak", None, FOOTBALL),
        # A selection that is neither yes nor no.
        ("Villarreal strzeli gola", "Villarreal", None, FOOTBALL),
        # The set number repeated in the specialBetValue disagrees.
        ("Zostanie rozegrany 3. set", "Tak", "4", TENNIS),
        ("1. set - handicap gemy", "Alexander Zverev (-1.5)", "-1.5-2", TENNIS),
        # A scope sofa has no metric for (saves_2h_for is not declared).
        ("2. połowa - każda z drużyn powyżej X obronionych strzałów przez bramkarza",
         "Powyżej 0.5 - tak", "0.5", FOOTBALL),
        # Set 3 is not part of this family (a set that may not be played).
        ("3. set - handicap gemy", "Alexander Zverev (-1.5)", "-1.5-3", TENNIS),
        # A handicap selection that names neither side.
        ("1. połowa - rzuty rożne - handicap", "Remis (0)", "0", FOOTBALL),
    ],
)
def test_what_is_not_this_family_stays_unmapped(
    market: str, selection: str, sbv: str | None, sides: tuple[str, ...]
) -> None:
    assert classify_mappable_family(market, selection, sbv, sides) is None


def test_only_the_yes_no_answers_to_a_ladder_rung_are_answers() -> None:
    assert is_ladder_answer("Villarreal strzeli gola")
    assert is_ladder_answer("2.połowa - Napoli strzeli gola")
    assert is_ladder_answer("Zostanie rozegrany 3. set")
    assert not is_ladder_answer("1.połowa - obie drużyny strzelą")
    assert not is_ladder_answer("1. set - handicap gemy")


_ITEMS: list[dict[str, Any]] = [
    {"marketName": "Villarreal strzeli gola", "name": "tak", "price": 1.17},
    {"marketName": "1.połowa - obie drużyny strzelą", "name": "tak", "price": 3.55},
    {"marketName": "Zostanie rozegrany 3. set", "name": "Tak",
     "specialBetValue": "3", "price": 2.4},
    {"marketName": "1. set - handicap gemy", "name": "Alexander Zverev (-1.5)",
     "specialBetValue": "-1.5-1", "price": 2.17},
]


# --- OFFER with the switch on --------------------------------------------------


def _on() -> dict[int, dict[str, Any]]:
    return {o["sofascore_event_id"]: o for o in offer_dump(True)}


def _rungs(entry: dict[str, Any]) -> dict[tuple[str, str, float], dict[str, Any]]:
    return {(r["market"], r["subject"], r["line"]): r for r in entry["rungs"]}


def test_on_the_ladder_keeps_its_own_rung_and_the_answer_adds_none() -> None:
    """Villarreal - liczba goli quotes 0.5 at 1.17 / 4.7; "Villarreal strzeli
    gola" quotes 1.17 / 4.8. One quantity, one rung - the ladder's - and no
    price collision is invented between two markets."""
    off = {o["sofascore_event_id"]: o for o in offer_dump(False)}
    on = _on()
    football = 14738966
    rung = _rungs(on[football])[("goals_for", "villarreal", 0.5)]
    assert (rung["over_odds"], rung["under_odds"]) == (1.17, 4.7)
    assert _rungs(on[football])[("goals_1h_for", "napoli", 0.5)] == \
        _rungs(off[football])[("goals_1h_for", "napoli", 0.5)]
    assert on[football]["price_collisions"] == []
    tennis = 15410344
    assert _rungs(on[tennis])[("sets_total", "", 2.5)] == \
        _rungs(off[tennis])[("sets_total", "", 2.5)]
    # Every rung OFF had is unchanged ON; ON only adds.
    for event_id, entry in off.items():
        before, after = _rungs(entry), _rungs(on[event_id])
        assert all(after[k] == v for k, v in before.items())
    # And the names it read leave unmapped_markets.
    assert "Villarreal strzeli gola" not in on[football]["unmapped_markets"]
    assert "Zostanie rozegrany 3. set" not in on[tennis]["unmapped_markets"]


def test_on_the_new_derived_markets_are_rungs() -> None:
    on = _on()
    football, tennis = _rungs(on[14738966]), _rungs(on[15410344])
    btts = football[("both_over_goals_1h", "", 0.5)]
    assert (btts["over_odds"], btts["under_odds"]) == (3.55, 1.27)
    saves = football[("both_over_saves", "", 1.5)]
    assert (saves["over_odds"], saves["under_odds"]) == (1.43, None)
    assert football[("both_over_saves_1h", "", 0.5)]["over_odds"] == 1.68
    assert football[("handicap_corners_1h", "villarreal", -0.5)]["over_odds"] == 1.97
    assert football[("handicap_corners_2h", "napoli", 0.5)]["over_odds"] == 1.74
    assert tennis[("handicap_games_won_set1", "alexander zverev", -1.5)]["over_odds"] == 2.17
    assert tennis[("handicap_games_won_set2", "alexander bublik", 1.5)]["over_odds"] == 1.67


class _OneListing:
    def __init__(self, odds: list[dict[str, Any]]) -> None:
        self.odds = odds

    def event_odds(self, event_id: str) -> dict[str, Any]:
        return {"matchName": "Villarreal·Napoli", "utcDate": "2026-10-13T19:00:00Z",
                "odds": self.odds}


def _fetch(odds: list[dict[str, Any]], on: bool = True) -> FixtureOffer:
    from bet.sofa import offer as offer_mod

    saved = offer_mod.now
    offer_mod.now = lambda: FROZEN  # type: ignore[assignment]
    try:
        [entry] = OfferFetcher(_OneListing(odds), mappable_families=on).fetch_offers(
            [fixture("football", "14738966")])
    finally:
        offer_mod.now = saved  # type: ignore[assignment]
    return entry


def test_on_an_answer_fills_a_rung_the_ladder_does_not_quote() -> None:
    """The ladder quotes 1.5 and up only (10-12: 19 of 546 football answers
    had no ladder rung at 0.5): the answer is the 0.5 rung, both sides from
    the one market."""
    entry = _fetch([
        {"marketName": "Villarreal - liczba goli", "name": "powyżej 1.5",
         "specialBetValue": "1.5", "price": 1.83},
        {"marketName": "Villarreal - liczba goli", "name": "poniżej 1.5",
         "specialBetValue": "1.5", "price": 1.9},
        {"marketName": "Villarreal strzeli gola", "name": "tak", "price": 1.17},
        {"marketName": "Villarreal strzeli gola", "name": "nie", "price": 4.8},
    ])
    rungs = {(r.market, r.subject, r.line): r for r in entry.rungs}
    answer = rungs[("goals_for", "villarreal", 0.5)]
    assert (answer.over_odds, answer.under_odds) == (1.17, 4.8)
    # A two-way yes/no is one rung with a measurable margin, not a ladder.
    margin = overround(answer.over_odds, answer.under_odds)
    assert margin == pytest.approx(1 / 1.17 + 1 / 4.8 - 1)
    assert margin is not None and margin < 0.15
    assert ("goals_for", "villarreal", 1.5) in rungs
    assert entry.price_collisions == []


def test_on_a_ladder_side_is_never_mixed_with_an_answer_side() -> None:
    """The ladder quotes only OVER 0.5 (its UNDER suspended): the rung stays
    the ladder's one-sided rung - an answer's 'nie' is not glued onto it."""
    entry = _fetch([
        {"marketName": "Villarreal - liczba goli", "name": "powyżej 0.5",
         "specialBetValue": "0.5", "price": 1.17},
        {"marketName": "Villarreal - liczba goli", "name": "poniżej 0.5",
         "specialBetValue": "0.5", "price": 4.7, "status": "block"},
        {"marketName": "Villarreal strzeli gola", "name": "tak", "price": 1.16},
        {"marketName": "Villarreal strzeli gola", "name": "nie", "price": 4.8},
    ])
    [rung] = [r for r in entry.rungs if r.market == "goals_for"]
    assert (rung.over_odds, rung.under_odds) == (1.17, None)


def test_on_samples_ask_for_the_side_metrics_the_new_markets_need() -> None:
    wanted: set[str] = set()
    for entry in offer_dump(True):
        wanted |= metrics_from_offer(FixtureOffer.model_validate_json(json.dumps(entry)))
    assert {"saves_for", "saves_1h_for", "goals_1h_for", "goals_2h_for",
            "corners_1h_for", "corners_2h_for", "games_won_set1_for",
            "games_won_set2_for"} <= wanted


# --- SETTLE grades the new rows ---------------------------------------------


def _row(market: str, line: float, direction: str = "OVER", subject: str = "",
         sport: str = "football") -> dict[str, Any]:
    return {"market": market, "line": line, "direction": direction,
            "subject": subject, "sport": sport}


def _football_event(h1: tuple[int, int], h2: tuple[int, int]) -> dict[str, Any]:
    return {
        "id": 1, "homeTeam": {"name": "Villarreal"}, "awayTeam": {"name": "Napoli"},
        "status": {"code": 100, "type": "finished"},
        "homeScore": {"current": h1[0] + h2[0], "period1": h1[0], "period2": h2[0]},
        "awayScore": {"current": h1[1] + h2[1], "period1": h1[1], "period2": h2[1]},
    }


def _flat(all_: dict[str, tuple[float, float]],
          first: dict[str, tuple[float, float]]) -> dict[str, dict[str, tuple[float, float]]]:
    return {"ALL": {**all_, "passes": (400.0, 400.0)},
            "1ST": {**first, "passes": (200.0, 200.0)}}


@pytest.mark.parametrize(
    ("h1", "direction", "expected"),
    [((1, 1), "OVER", "WIN"), ((1, 0), "OVER", "LOSS"), ((1, 0), "UNDER", "WIN"),
     ((0, 0), "UNDER", "WIN")],
)
def test_settle_both_teams_score_in_the_first_half(
    h1: tuple[int, int], direction: str, expected: str
) -> None:
    graded = _settle_derived(
        _row("both_over_goals_1h", 0.5, direction), "football", _flat({}, {}), None,
        _football_event(h1, (2, 2)))
    assert graded == (float(min(h1)), expected)


def test_settle_both_over_saves_match_and_first_half() -> None:
    flat = _flat({"goalkeeperSaves": (4.0, 2.0)}, {"goalkeeperSaves": (1.0, 0.0)})
    event = _football_event((0, 0), (1, 1))
    assert _settle_derived(_row("both_over_saves", 1.5), "football", flat, None,
                           event) == (2.0, "WIN")
    assert _settle_derived(_row("both_over_saves", 2.5), "football", flat, None,
                           event) == (2.0, "LOSS")
    assert _settle_derived(_row("both_over_saves_1h", 0.5), "football", flat, None,
                           event) == (0.0, "LOSS")


def test_settle_corner_handicap_in_a_half_reads_the_half() -> None:
    flat = _flat({"cornerKicks": (3.0, 9.0)}, {"cornerKicks": (3.0, 1.0)})
    event = _football_event((0, 0), (0, 0))
    # First half 3-1: Villarreal -0.5 wins, Napoli +0.5 loses - though the
    # match's corners went 3-9 the other way.
    assert _settle_derived(_row("handicap_corners_1h", -0.5, subject="villarreal"),
                           "football", flat, None, event) == (2.0, "WIN")
    assert _settle_derived(_row("handicap_corners_1h", 0.5, subject="napoli"),
                           "football", flat, None, event) == (-2.0, "LOSS")


def _tennis_event(sets: list[tuple[int, int]]) -> dict[str, Any]:
    home = {f"period{i}": h for i, (h, _) in enumerate(sets, 1)}
    away = {f"period{i}": a for i, (_, a) in enumerate(sets, 1)}
    won = sum(1 for h, a in sets if h > a)
    return {
        "id": 2, "homeTeam": {"name": "Alexander Zverev"},
        "awayTeam": {"name": "Alexander Bublik"},
        "status": {"code": 100, "type": "finished"},
        "homeScore": {"current": won, **home},
        "awayScore": {"current": len(sets) - won, **away},
    }


def test_settle_games_handicap_in_a_set_reads_that_set() -> None:
    event = _tennis_event([(6, 3), (4, 6), (7, 5)])
    assert _settle_derived(
        _row("handicap_games_won_set1", -2.5, subject="alexander zverev", sport="tennis"),
        "tennis", {}, None, event) == (3.0, "WIN")
    assert _settle_derived(
        _row("handicap_games_won_set2", -1.5, subject="alexander zverev", sport="tennis"),
        "tennis", {}, None, event) == (-2.0, "LOSS")
    assert _settle_derived(
        _row("handicap_games_won_set2", 1.5, subject="alexander bublik", sport="tennis"),
        "tennis", {}, None, event) == (2.0, "WIN")


@pytest.mark.parametrize(
    ("sets", "direction", "expected"),
    [([(6, 3), (4, 6), (7, 5)], "OVER", "WIN"), ([(6, 3), (6, 4)], "OVER", "LOSS"),
     ([(6, 3), (6, 4)], "UNDER", "WIN")],
)
def test_settle_third_set_played_is_sets_total_over_2_5(
    sets: list[tuple[int, int]], direction: str, expected: str
) -> None:
    played = extract_metric("sets_total", "tennis", {}, None, _tennis_event(sets), True)
    assert isinstance(played, float)
    assert settle_value(played, 2.5, direction) == expected  # type: ignore[arg-type]


def test_settle_a_team_scores_is_goals_for_over_0_5() -> None:
    event = _football_event((0, 1), (0, 0))
    home = extract_metric("goals_for", "football", {}, None, event, True)
    away = extract_metric("goals_1h_for", "football", {}, None, event, False)
    assert isinstance(home, float) and isinstance(away, float)
    assert settle_value(home, 0.5, "OVER") == "LOSS"
    assert settle_value(away, 0.5, "OVER") == "WIN"
