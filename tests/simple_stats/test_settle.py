"""settle.py: what actually happened to a row.

This module is the only thing in the pipeline that can contradict it, so its
own arithmetic has to be beyond argument. The failure modes it guards are all
of the same kind -- a settlement that is *confidently wrong* is worse than one
that is absent, because it becomes evidence:

* a per-team row settled against the other team's figure,
* a match total settled against one side's figure,
* a market the provider never reported scored as a loss,
* a push on a whole-number line scored as a loss.

Every one of those makes a configuration look better or worse than it was, and
none of them would show up as an error anywhere.
"""
from __future__ import annotations

import pytest

from bet.simple_stats.settle import (
    actual_value,
    hit_rate,
    profit,
    settle,
    settle_row,
    team_side,
)


def _actuals(**kwargs) -> dict[str, dict[str, float]]:
    base = {"home": {}, "away": {}, "total": {}}
    base.update(kwargs)
    return base


# --- the line, and the push -------------------------------------------------


@pytest.mark.parametrize(
    "direction,line,value,expected",
    [
        ("UNDER", 4.5, 4.0, "WON"),
        ("UNDER", 4.5, 5.0, "LOST"),
        ("OVER", 4.5, 5.0, "WON"),
        ("OVER", 4.5, 4.0, "LOST"),
        # Whole-number lines: Superbet posts corners 9, cards 4, goals 3, and a
        # stake is returned when the count lands exactly there.
        ("OVER", 9.0, 9.0, "PUSH"),
        ("UNDER", 9.0, 9.0, "PUSH"),
        ("OVER", 9.0, 10.0, "WON"),
        ("UNDER", 9.0, 8.0, "WON"),
        # Zero is a real count, not a missing one.
        ("UNDER", 0.5, 0.0, "WON"),
        ("OVER", 0.5, 0.0, "LOST"),
    ],
)
def test_the_line_decides_and_landing_on_it_is_a_push(direction, line, value, expected):
    assert settle(direction, line, value) == expected


def test_an_unreported_market_is_not_a_loss():
    """A coverage gap in this module is not a failed bet. Folding the two
    together would make every configuration look worse in proportion to how
    many exotic markets it reached -- which is the opposite of what a backtest
    is for."""
    assert settle("OVER", 4.5, None) == "NO_DATA"
    assert settle("UNDER", 4.5, None) == "NO_DATA"


def test_an_unknown_direction_settles_nothing():
    """Defensive rather than reachable: ``direction`` is a Literal on the
    contract. But a settlement that silently treats an unrecognised direction
    as a loss would be the worst kind of wrong here."""
    assert settle("BOTH", 4.5, 5.0) == "NO_DATA"


# --- whose figure -----------------------------------------------------------


def test_a_per_team_row_reads_its_own_side():
    actuals = _actuals(home={"corners_for": 5.0}, away={"corners_for": 2.0})
    assert actual_value(actuals, "corners_for", "home") == 5.0
    assert actual_value(actuals, "corners_for", "away") == 2.0


def test_a_per_team_row_with_no_side_settles_nothing():
    """Rather than falling back to the total. "Sheffield's corners" against the
    match's sixteen is not a near miss, it is a different bet."""
    actuals = _actuals(home={"corners_for": 5.0}, total={"corners_total": 7.0})
    assert actual_value(actuals, "corners_for", None) is None


def test_a_match_total_never_reads_a_side():
    """The mistake this prevents: settling "corners_total OVER 9.5" against one
    team's five corners. The side key is ignored for a total by construction,
    not by a caller remembering not to pass one."""
    actuals = _actuals(home={"corners_total": 5.0}, total={"corners_total": 16.0})
    assert actual_value(actuals, "corners_total", "home") == 16.0
    assert actual_value(actuals, "corners_total", None) == 16.0


def test_a_non_numeric_value_is_a_gap_and_not_a_zero():
    actuals = _actuals(total={"corners_total": "n/a"})
    assert actual_value(actuals, "corners_total", None) is None


def test_a_tracker_that_never_engaged_settles_nothing():
    """Panathinaikos-Kifisia, bzzoiro event 601009, 2026-09-10: FT 3-1 with a
    red card, but ``/events/{id}/stats/`` reported ``fouls_total: 0.0`` and a
    literal 100/0 ball-possession split for both sides, because the live
    tracker never engaged for this fixture (confirmed live: ``total_shots``,
    ``shots_on_target`` and ``corner_kicks`` are absent from the raw payload
    entirely, not zero). Read at face value, ``fouls_total OVER 20.5`` -- a
    71%-confidence pick backed by 17 real observations -- settled a LOST
    instead of NO_DATA.

    ``_is_absent_not_zero`` already catches this shape for the *sample* it
    feeds into other fixtures' history (``fouls_total == 0.0`` on a finished
    match is its first, hard-coded check); this pins that the settlement path
    now refuses the same block rather than trusting it selectively.
    """
    actuals = _actuals(
        home={"fouls_for": 0.0, "cards_points_for": 1.0, "goals_for": 3.0},
        away={"fouls_for": 0.0, "cards_points_for": 6.0, "goals_for": 1.0},
        total={
            "fouls_total": 0.0,
            "cards_total": 1.0,
            "cards_points_total": 7.0,
            "goals_total": 4.0,
        },
    )
    assert actual_value(actuals, "fouls_total", None) is None
    assert settle_row(market="fouls_total", line=20.5, direction="OVER", actuals=actuals)[0] == "NO_DATA"
    # The whole block is distrusted, not just the market that tipped it off:
    # goals_total and cards_points_total came from a different endpoint
    # (incidents) for this exact match and happened to be right, but nothing
    # in the payload lets settlement tell that apart from the broken fields.
    assert actual_value(actuals, "goals_total", None) is None
    assert actual_value(actuals, "cards_for", "home") is None


def test_a_tennis_retirement_settles_nothing():
    """Total games/sets below what a completed singles match can produce is
    the tennis half of the same fault: a player who quits at 2-1 down
    contributes three games to a "total games UNDER 21.5" sample as though he
    had played a whole match. The scoreboard states a real, non-zero score --
    this is not a missing-value case, it is a value that describes something
    no finished match can be, same as ``fouls_total: 0.0`` above.
    """
    actuals = _actuals(
        home={"games_won": 3.0},
        away={"games_won": 2.0},
        total={"total_games": 5.0, "total_sets": 1.0},
    )
    assert actual_value(actuals, "total_games", None) is None
    assert actual_value(actuals, "games_won", "home") is None
    assert settle_row(market="total_games", line=21.5, direction="UNDER", actuals=actuals)[0] == "NO_DATA"

    # A genuine completed match is untouched.
    finished = _actuals(
        home={"games_won": 13.0},
        away={"games_won": 8.0},
        total={"total_games": 21.0, "total_sets": 2.0},
    )
    assert actual_value(finished, "total_games", None) == 21.0
    assert actual_value(finished, "games_won", "home") == 13.0


# --- which side -------------------------------------------------------------


def test_the_side_is_matched_with_the_pipelines_own_team_test():
    """Exact string equality left real rows unsettled: the coupon carries our
    spelling and the event list the provider's."""
    assert team_side("KS Lechia Gdańsk", "Lechia Gdansk", "MKS Kluczbork") == "home"
    assert team_side("Manchester Utd", "Arsenal", "Manchester United") == "away"


def test_a_name_that_matches_neither_side_is_refused():
    assert team_side("Real Madrid", "Sheffield United", "Bolton Wanderers") is None


def test_a_name_that_matches_both_sides_is_refused():
    """The direction that would be catastrophic rather than merely missing. A
    row scored against the wrong team looks exactly like evidence, so an
    ambiguous match returns None -- the same rule ``_opponent_of`` follows."""
    assert team_side("United", "Manchester United", "Newcastle United") is None


def test_a_fragment_does_not_carry_a_whole_name():
    """``_team_matches`` is already hardened against this and the test is here
    to say that this module depends on it: "Botafogo-SP" is not "Botafogo RJ",
    and settling one against the other would be silent."""
    assert team_side("Botafogo-SP", "Botafogo RJ", "Santos") is None


def test_settle_row_refuses_a_team_row_it_cannot_place():
    outcome, value = settle_row(
        market="corners_for", line=4.5, direction="UNDER",
        actuals=_actuals(home={"corners_for": 5.0}),
        team_name="Real Madrid", home_team="Sheffield United", away_team="Bolton",
    )
    assert outcome == "NO_DATA" and value is None


def test_settle_row_end_to_end_on_the_row_that_lost():
    """#1 of 2026-09-01: Sheffield United corners UNDER 4.5, and the match
    returned five."""
    outcome, value = settle_row(
        market="corners_for", line=4.5, direction="UNDER",
        actuals=_actuals(home={"corners_for": 5.0}, away={"corners_for": 3.0}),
        team_name="Sheffield United",
        home_team="Sheffield United", away_team="Bolton Wanderers",
    )
    assert (outcome, value) == ("LOST", 5.0)


# --- aggregates -------------------------------------------------------------


def test_pushes_and_gaps_leave_the_hit_rate_alone():
    won, decided, rate = hit_rate(["WON", "WON", "LOST", "PUSH", "NO_DATA"])
    assert (won, decided) == (2, 3)
    assert rate == pytest.approx(2 / 3)


def test_nothing_decided_is_unknown_and_not_zero():
    """A configuration that emitted ten rows and could settle none has an
    unknown hit rate. Printing 0% for it would read as ten losses, which is
    exactly the wrong conclusion to draw from a coverage gap."""
    assert hit_rate(["NO_DATA", "PUSH"]) == (0, 0, None)
    assert hit_rate([]) == (0, 0, None)


def test_an_unpriced_row_is_not_staked_at_evens():
    """The commonest reason a row has no price is that Superbet never posted
    its line. A bet that could not be placed must not appear in the return of
    a strategy in either direction."""
    staked, returned, priced = profit(["WON", "WON"], [2.0, None])
    assert (staked, returned, priced) == (1.0, 2.0, 1)


def test_a_push_returns_the_stake():
    staked, returned, priced = profit(["PUSH"], [2.5])
    assert (staked, returned, priced) == (1.0, 1.0, 1)


def test_a_row_with_no_data_is_not_staked_even_when_priced():
    staked, returned, priced = profit(["NO_DATA"], [2.5])
    assert (staked, returned, priced) == (0.0, 0.0, 0)


def test_the_2026_09_01_slate_reproduces_its_recorded_result():
    """The seven singles that day's file admitted, their real Superbet prices,
    and the outcomes read off the operator's own slips. Six lost, one was void
    when the match was abandoned -- and a void is a returned stake, so it is
    scored as a push rather than as a loss.

    Pinned as an end-to-end check on the aggregates: if this arithmetic ever
    stops reproducing the one result that is known independently of the code,
    nothing else the backtest prints can be trusted.
    """
    outcomes = ["LOST", "LOST", "PUSH", "LOST", "LOST", "LOST", "LOST"]
    prices = [2.70, 2.12, 1.85, 2.07, 1.95, 1.88, 1.49]
    won, decided, rate = hit_rate(outcomes)
    assert (won, decided, rate) == (0, 6, 0.0)
    staked, returned, priced = profit(outcomes, prices)
    assert priced == 7
    assert staked == pytest.approx(7.0)
    # Six stakes lost outright, the void one returned.
    assert returned == pytest.approx(1.0)
    assert returned / staked - 1.0 == pytest.approx(-0.857, abs=0.001)
