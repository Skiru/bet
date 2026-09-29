"""A 10-point match tiebreak is one game, not ten (2026-09-29).

Event 16498311, ITF M15 Slobozia: 6-4 6-7(3) 10-5. Sofascore stores the
deciding match tiebreak as period3 = 10 / 5. Summing periods read it as
22 games won by Prunescu Nita - impossible in best of three (21 is the
maximum) - and, where /statistics carried gamesWon (which counts the
tiebreak as NO game), marked the whole match INTERNAL_INCONSISTENT.
"""

from __future__ import annotations

from typing import Any

from bet.sofa.contracts import GapReason
from bet.sofa.metrics import check_identities, extract_metric
from bet.sofa.tennis_rating import parse_event
from bet.sofa.tennis_score import match_tiebreak_sets, set_games

MTB_HOME = {
    "current": 2, "period1": 6, "period2": 6, "period3": 10, "period2TieBreak": 3
}
MTB_AWAY = {
    "current": 1, "period1": 4, "period2": 7, "period3": 5, "period2TieBreak": 7
}


def _event(home: dict[str, Any], away: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": 16498311,
        "homeScore": home,
        "awayScore": away,
        "status": {"type": "finished", "description": "Ended"},
        "winnerCode": 1,
        "startTimestamp": 1_783_000_000,
        "homeTeam": {"id": 1, "type": 1},
        "awayTeam": {"id": 2, "type": 1},
        "tournament": {"category": {"sport": {"slug": "tennis"}, "name": "ITF Men"}},
        "groundType": "Red clay",
    }


def test_the_match_tiebreak_is_one_game_to_its_winner() -> None:
    assert set_games(MTB_HOME, MTB_AWAY) == [(6, 4), (6, 7), (1, 0)]
    assert match_tiebreak_sets(MTB_HOME, MTB_AWAY) == {3}


def test_an_ordinary_three_setter_is_untouched() -> None:
    home = {"period1": 6, "period2": 3, "period3": 7}
    away = {"period1": 4, "period2": 6, "period3": 6}
    assert set_games(home, away) == [(6, 4), (3, 6), (7, 6)]
    assert match_tiebreak_sets(home, away) == set()


def test_an_extended_match_tiebreak_counts_too() -> None:
    home = {"period1": 1, "period2": 6, "period3": 13}
    away = {"period1": 6, "period2": 3, "period3": 11}
    assert set_games(home, away) == [(1, 6), (6, 3), (1, 0)]


def test_a_score_that_is_no_set_score_is_no_observation() -> None:
    # UTS exhibition quarters: 18-11, 20-7 ... are not sets of games.
    home = {"period1": 18, "period2": 20, "period3": 11, "period4": 19}
    away = {"period1": 11, "period2": 7, "period3": 14, "period4": 7}
    assert set_games(home, away) is None


def test_games_from_the_listing_count_the_tiebreak_as_one_game() -> None:
    event = _event(MTB_HOME, MTB_AWAY)
    assert extract_metric("games_won_for", "tennis", {}, None, event, True) == 13.0
    assert extract_metric("games_won_for", "tennis", {}, None, event, False) == 11.0
    assert extract_metric("games_total", "tennis", {}, None, event, True) == 24.0


def test_the_third_set_games_of_a_match_tiebreak_are_no_observation() -> None:
    event = _event(MTB_HOME, MTB_AWAY)
    got = extract_metric("games_won_set3_for", "tennis", {}, None, event, True)
    assert got is GapReason.STAT_KEY_ABSENT
    assert extract_metric("games_won_set2_for", "tennis", {}, None, event, True) == 6.0


def test_gameswon_that_counts_the_tiebreak_as_no_game_is_consistent() -> None:
    # Sofascore's convention on 266 of 270 cached match-tiebreak events:
    # 6-4 6-7 10-5 -> gamesWon 12 : 11, the tiebreak counted as nothing.
    flat = {"ALL": {"gamesWon": (12.0, 11.0)}}
    assert check_identities(flat, None, _event(MTB_HOME, MTB_AWAY), "tennis") is None
    flat_wrong = {"ALL": {"gamesWon": (22.0, 16.0)}}
    assert (
        check_identities(flat_wrong, None, _event(MTB_HOME, MTB_AWAY), "tennis")
        is GapReason.INTERNAL_INCONSISTENT
    )


def test_the_rating_history_reads_the_tiebreak_as_one_game() -> None:
    result = parse_event(_event(MTB_HOME, MTB_AWAY))
    assert result is not None
    assert result.sets == ((6, 4), (6, 7), (1, 0))
    assert sum(h for h, _ in result.sets) == 13


def test_the_statistic_and_the_listing_give_one_convention() -> None:
    # gamesWon says 12 (tiebreak = 0); the observation must still be 13, as
    # it is when only the listing is present - never two conventions.
    flat = {"ALL": {"gamesWon": (12.0, 11.0)}}
    event = _event(MTB_HOME, MTB_AWAY)
    assert extract_metric("games_won_for", "tennis", flat, None, event, True) == 13.0
    assert extract_metric("games_total", "tennis", flat, None, event, True) == 24.0


def test_a_match_without_a_tiebreak_still_reads_the_statistic() -> None:
    home = {"period1": 6, "period2": 7}
    away = {"period1": 3, "period2": 6}
    flat = {"ALL": {"gamesWon": (13.0, 9.0)}}
    event = _event(home, away)
    assert extract_metric("games_won_for", "tennis", flat, None, event, True) == 13.0
