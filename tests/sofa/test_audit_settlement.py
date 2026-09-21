"""The settlement audit's two jobs, and the trap under each.

The report exists to answer "ile weszło, ile nie weszło, dlaczego". Both
halves of that have a way of going quietly wrong:

  * the *why* of a loss is arithmetic on the row's own numbers. A note that
    restates the line or the result from anywhere else can end up contradicting
    the row it sits next to (L: a note can contradict its own arithmetic).
  * the *why* of an ungraded row is a gap, not a loss, and the two must not be
    pooled — a blind row counted as a miss understates the model exactly as
    much as counting it as a hit overstates it.
"""

import pytest

from scripts.sofa.audit_settlement import _family, _reason_for_loss, _table


def _row(**over):
    base = dict(line=4.5, actual_value=3.0, direction="OVER")
    base.update(over)
    return base


def test_the_reason_reads_off_the_row_it_describes():
    assert _reason_for_loss(_row()) == "padło 3, potrzebne > 4.5"
    assert _reason_for_loss(_row(direction="UNDER", actual_value=12.0, line=10.5)) == (
        "padło 12, potrzebne < 10.5"
    )


def test_a_negative_handicap_line_keeps_its_sign():
    """`handicap_cards_points OVER -1.5` settled at -2 is a loss, and the note
    has to say so without losing the minus."""
    assert _reason_for_loss(_row(line=-1.5, actual_value=-2.0)) == (
        "padło -2, potrzebne > -1.5"
    )


@pytest.mark.parametrize(
    "market,family",
    [
        ("corners_1h_for", "corners"),
        ("both_over_corners", "corners"),
        ("handicap_cards_points", "cards"),
        ("shots_on_target_for", "shots_on"),
        ("shots_for", "shots"),
        ("goals_2h_total", "goals"),
        ("games_won_for", "games_won"),
        ("double_faults_for", "double_faults"),
    ],
)
def test_the_family_groups_scopes_of_the_same_question(market, family):
    """A per-market table over 56k rows is 400 lines long and says less."""
    assert _family(market) == family


def test_shots_on_target_is_not_filed_under_shots():
    """The order of the token list is load-bearing: `shots` is a prefix of
    `shots_on_target`, so a naive scan files every shot-on-target row under
    plain shots and the two families' hit rates both become fiction."""
    assert _family("shots_on_target_total") != _family("shots_total")


def test_a_pipe_in_a_cell_would_end_the_cell():
    """Markdown has no escape here that renders in every viewer, so the
    header text itself must not contain one. This is the whole reason the
    column is called "mediana odchylenia od linii" and not "|wynik - linia|"."""
    rendered = _table(["a", "b"], [["1", "2"]])
    assert rendered.splitlines()[0].count("|") == 3
    assert len(rendered.splitlines()) == 3
