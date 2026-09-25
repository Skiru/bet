"""Settling the both-teams / most / handicap rows (F53).

These are 5 of the 33 singles the 2026-09-18 coupon actually staked, and
before this they could not be graded at all: `extract_metric` has no reading
for "both_over_corners", so they fell out as STAT_KEY_ABSENT and never reached
`sofa_settled_row`. 15% of what was staked was unmeasurable.

Every assertion below pins settlement to the SAME arithmetic `derived.probability`
prices with. A settlement that reads "powyżej 3.5" as "> 3.5" while the pricer
reads it as ">= 4" disagrees with itself at every integer, and the disagreement
is invisible because both halves look right on their own.
"""

import pytest

from bet.sofa.derived import probability
from bet.sofa.joint import build_joint
from scripts.sofa.run_settle import _handicap_side, _settle_derived


def _flat(home: float, away: float, key: str = "cornerKicks"):
    return {"ALL": {key: (home, away)}}


def _event():
    return {
        "id": 1,
        "homeTeam": {"name": "Brentford"},
        "awayTeam": {"name": "Chelsea"},
        "status": {"code": 100, "type": "finished"},
        "homeScore": {"current": 1, "period1": 0, "period2": 1},
        "awayScore": {"current": 0, "period1": 0, "period2": 0},
    }


def _row(market, line, direction="OVER", subject=""):
    return {
        "market": market,
        "line": line,
        "direction": direction,
        "subject": subject,
        "sport": "football",
    }


# --- both_over -----------------------------------------------------------


@pytest.mark.parametrize(
    ("home", "away", "line", "expected"),
    [
        (4, 5, 3.5, "WIN"),  # both >= 4
        (4, 3, 3.5, "LOSS"),  # away short
        (3, 3, 3.5, "LOSS"),
        (9, 4, 3.5, "WIN"),
        (1, 1, 0.5, "WIN"),  # "obie druzyny strzela"
        (1, 0, 0.5, "LOSS"),
    ],
)
def test_both_over_is_the_smaller_side_against_the_line(home, away, line, expected):
    value, outcome = _settle_derived(
        _row("both_over_corners", line), "football", _flat(home, away), None, _event()
    )
    assert outcome == expected
    assert value == min(home, away)


def test_both_over_under_is_the_complement():
    args = ("football", _flat(4, 5), None, _event())
    assert _settle_derived(_row("both_over_corners", 3.5, "OVER"), *args)[1] == "WIN"
    assert _settle_derived(_row("both_over_corners", 3.5, "UNDER"), *args)[1] == "LOSS"


def test_settlement_reads_the_line_the_way_the_pricer_does():
    """Both sides must read "powyzej L" on a count as ">= floor(L) + 1".

    Checked as an equivalence rather than by asserting a probability, because
    the pricer floors the variance at the mean (Poisson) and so never reaches
    certainty however tight the sample is. What matters is the threshold: 3.5
    and 3.9 are the same bet, 4.0 is a different one — and settlement has to
    agree with the pricer on exactly that, or the two part company on the one
    integer the line straddles.
    """
    joint = build_joint(4.0, 4.0, 4.0, 4.0, 0.0)
    p35 = probability(joint, "both_over_corners", 3.5, "OVER", None)
    p39 = probability(joint, "both_over_corners", 3.9, "OVER", None)
    p40 = probability(joint, "both_over_corners", 4.0, "OVER", None)
    assert p35 == pytest.approx(p39)
    assert p40 < p35

    def settle_at(line, home, away):
        return _settle_derived(
            _row("both_over_corners", line),
            "football",
            _flat(home, away),
            None,
            _event(),
        )[1]

    # The same three lines, settled against a match both sides finished on 4.
    assert settle_at(3.5, 4, 4) == "WIN"
    assert settle_at(3.9, 4, 4) == "WIN"
    assert settle_at(4.0, 4, 4) == "LOSS"


# --- most_ ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("home", "away", "subject", "expected"),
    [
        (6, 4, "1", "WIN"),
        (6, 4, "2", "LOSS"),
        (6, 4, "__draw__", "LOSS"),
        (4, 4, "__draw__", "WIN"),
        (4, 4, "1", "LOSS"),
        (2, 7, "2", "WIN"),
    ],
)
def test_most_is_a_three_way_partition(home, away, subject, expected):
    value, outcome = _settle_derived(
        _row("most_corners", 0.0, "OVER", subject),
        "football",
        _flat(home, away),
        None,
        _event(),
    )
    assert outcome == expected
    assert value == home - away


def test_the_three_most_selections_settle_to_exactly_one_winner():
    for home, away in ((6, 4), (4, 4), (1, 9)):
        wins = [
            _settle_derived(
                _row("most_corners", 0.0, "OVER", s),
                "football",
                _flat(home, away),
                None,
                _event(),
            )[1]
            for s in ("1", "2", "__draw__")
        ]
        assert wins.count("WIN") == 1


# --- handicap_ -----------------------------------------------------------


@pytest.mark.parametrize(
    ("home", "away", "subject", "line", "expected"),
    [
        # "Brentford (-1.5)": wins when Brentford beat Chelsea by 2+
        (6, 4, "brentford", -1.5, "WIN"),
        (5, 4, "brentford", -1.5, "LOSS"),
        # "Chelsea (+1.5)": wins unless Chelsea lose by 2+
        (5, 4, "chelsea", 1.5, "WIN"),
        (6, 4, "chelsea", 1.5, "LOSS"),
        (2, 9, "chelsea", 1.5, "WIN"),
    ],
)
def test_a_handicap_is_the_subjects_own_margin(home, away, subject, line, expected):
    value, outcome = _settle_derived(
        _row("handicap_corners", line, "OVER", subject),
        "football",
        _flat(home, away),
        None,
        _event(),
    )
    assert outcome == expected


def test_a_whole_number_handicap_landing_exactly_is_a_push():
    assert (
        _settle_derived(
            _row("handicap_corners", -1.0, "OVER", "brentford"),
            "football",
            _flat(5, 4),
            None,
            _event(),
        )
        == "PUSH"
    )


def test_the_two_sides_of_a_half_line_handicap_are_complements():
    for home, away in ((6, 4), (4, 4), (1, 9), (5, 4)):
        a = _settle_derived(
            _row("handicap_corners", -1.5, "OVER", "brentford"),
            "football",
            _flat(home, away),
            None,
            _event(),
        )[1]
        b = _settle_derived(
            _row("handicap_corners", 1.5, "OVER", "chelsea"),
            "football",
            _flat(home, away),
            None,
            _event(),
        )[1]
        assert {a, b} == {"WIN", "LOSS"}


def test_a_handicap_subject_naming_neither_side_is_refused():
    assert (
        _settle_derived(
            _row("handicap_corners", -1.5, "OVER", "arsenal"),
            "football",
            _flat(6, 4),
            None,
            _event(),
        )
        == "DERIVED_SUBJECT"
    )


def test_a_club_affix_still_finds_its_side_in_a_handicap():
    assert _handicap_side("brentford", {}, _event()) == "home"
    assert _handicap_side("2", {}, _event()) == "away"


# --- refusals -------------------------------------------------------------


def test_a_missing_statistic_is_reported_not_guessed():
    got = _settle_derived(
        _row("both_over_corners", 3.5), "football", {"ALL": {}}, None, _event()
    )
    assert isinstance(got, str) and "corners_for" in got


# --- named subjects (2026-09-25) -------------------------------------------
#
# 2026-09-24: 740 SUBJECT_NOT_MATCHED rows, every one a national team, because
# the subject was compared un-normalised ("niemcy" 46 against "germany", 100
# once the alias applies), and 412 `most_` rows with a named side refused as
# DERIVED_SUBJECT although SHEET priced them through `resolve_subject`.


def _national_event():
    return {
        **_event(),
        "homeTeam": {"name": "Netherlands"},
        "awayTeam": {"name": "Germany"},
    }


def test_a_polish_exonym_finds_its_side_in_a_per_team_row():
    from scripts.sofa.run_settle import _subject_is_home

    fixture = {"home_name": "Netherlands", "away_name": "Germany"}
    assert _subject_is_home("niemcy", fixture) is False
    assert _subject_is_home("holandia", fixture) is True
    assert _subject_is_home("francja", fixture) is None


@pytest.mark.parametrize(
    ("subject", "expected"), [("niemcy", "WIN"), ("holandia", "LOSS")]
)
def test_a_named_side_settles_a_most_market(subject, expected):
    value, outcome = _settle_derived(
        _row("most_corners", 0.0, "OVER", subject),
        "football",
        _flat(3, 6),
        None,
        _national_event(),
    )
    assert (value, outcome) == (-3, expected)


def test_a_named_most_subject_naming_neither_side_is_still_refused():
    assert (
        _settle_derived(
            _row("most_corners", 0.0, "OVER", "francja"),
            "football",
            _flat(3, 6),
            None,
            _national_event(),
        )
        == "DERIVED_SUBJECT"
    )


def test_a_polish_exonym_finds_its_side_in_a_handicap():
    assert _handicap_side("niemcy", {}, _national_event()) == "away"


@pytest.mark.parametrize(
    ("subject", "name"),
    [
        ("palestyna", "Palestine"),
        ("libia", "Libya"),
        ("katar", "Qatar"),
        ("białoruś u21", "Belarus U21"),
        ("bahrajn", "Bahrain"),
    ],
)
def test_the_exonyms_2026_09_24_left_unsettled_have_an_alias(subject, name):
    from bet.sofa.names import normalize_name

    assert normalize_name(subject) == normalize_name(name)


@pytest.mark.parametrize(
    ("status", "reason"),
    [
        ({"type": "finished", "code": 92}, "FINISHED_ABNORMALLY"),  # retired
        ({"type": "interrupted", "code": 80}, "NOT_FINISHED"),
        ({"type": "notstarted", "code": 0}, "NOT_FINISHED"),
        ({"type": "inprogress", "code": 7}, "NOT_FINISHED"),
        ({"type": "canceled", "code": 70}, "CANCELED"),
        ({"type": "abandoned", "code": 90}, "ABANDONED"),
        ({"type": "postponed", "code": 60}, "POSTPONED"),
    ],
)
def test_an_unsettleable_event_says_which_kind_it_is(status, reason):
    from scripts.sofa.run_settle import unfinished_reason

    assert unfinished_reason({"status": status}) == reason
