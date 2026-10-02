"""A dash between letters is a word break (2026-10-02).

SETTLE could not grade the 2026-10-01 "al wahda" rows of Baniyas - Al-Wahda FC
(event 17081548): the hyphen glued "al-wahda" into one token and the pair
scored 73.7 against the 82 gate. Pairs below are the ones measured on the
2026-09-29..10-01 boards, fixtures and offers.
"""

from __future__ import annotations

import pytest

from bet.sofa.config import MATCH_LOGIC_VERSION
from bet.sofa.contracts import Fixture
from bet.sofa.names import apply_aliases, get_aliases, normalize_name, team_levels
from bet.sofa.resolve import NAME_MATCH_THRESHOLD, name_score
from scripts.sofa.run_settle import _named_side
from scripts.sofa.run_sheet import determine_side


def _fx(home: str, away: str, sport: str = "football") -> Fixture:
    return Fixture.model_construct(sport=sport, home_name=home, away_name=away)


@pytest.mark.parametrize(
    ("raw", "folded"),
    [
        ("Al-Wahda FC", "al wahda fc"),
        ("Al–Wahda FC", "al wahda fc"),  # en dash: used to be deleted
        ("Al—Wahda", "al wahda"),
        ("Al‑Wahda", "al wahda"),  # non-breaking hyphen
        ("Arna-Bjørnar", "arna bjornar"),
        ("Felix Auger-Aliassime", "felix auger aliassime"),
        ("Pablo Carreño-Busta", "pablo carreno busta"),
    ],
)
def test_a_dash_between_letters_is_a_space(raw: str, folded: str) -> None:
    assert normalize_name(raw) == folded


def test_a_dash_not_between_letters_is_left_alone() -> None:
    # "U-21" is read by the reserve suffix rule and the age marker as it is.
    assert normalize_name("Bayern U-21") == "bayern (r)"
    assert team_levels(normalize_name("Flamengo U-20 Guarulhos")) == {"U20"}
    assert normalize_name("Team 1-2") == "team 1-2"


def test_settle_grades_al_wahda() -> None:
    # The 2026-10-01 defect itself: was None (SUBJECT_NOT_MATCHED).
    assert _named_side("al wahda", "Baniyas", "Al-Wahda FC") is False
    assert _named_side("umm salal", "Al Khor", "Umm-Salal SC") is False


@pytest.mark.parametrize(
    ("subject", "home", "away", "side"),
    [
        ("al wahda", "Baniyas", "Al-Wahda FC", "side_b"),
        ("dibba al hisn", "Palm City FC", "Dibba Al-Hisn", "side_b"),
        ("umm salal", "Al Khor", "Umm-Salal SC", "side_b"),
        ("gwinea bissau", "Guinea-Bissau", "Nigeria", "side_a"),
        # Same-prefix derbies keep their sides: "al" is shared, the rest is not.
        ("al sharjah", "Al-Sharjah", "Al-Dhafra", "side_a"),
        ("al dhafra", "Al-Sharjah", "Al-Dhafra", "side_b"),
        ("flamengo pi", "Flamengo-PI", "Comercial-PI", "side_a"),
        ("comercial pi", "Flamengo-PI", "Comercial-PI", "side_b"),
    ],
)
def test_sheet_places_a_hyphenated_side(
    subject: str, home: str, away: str, side: str
) -> None:
    assert determine_side(subject, _fx(home, away)) == side


@pytest.mark.parametrize(
    ("subject", "home", "away", "side"),
    [
        ("felix auger-aliassime", "Felix Auger-Aliassime", "Karen Khachanov", "side_a"),
        ("pablo carreno-busta", "Pablo Carreño Busta", "Some Player", "side_a"),
        ("jack bruce-smith", "Haruto Ishikawa", "Jack Bruce-Smith", "side_b"),
        ("jan-lennard struff", "Jan-Lennard Struff", "Thiago Tirante", "side_a"),
        ("kai-i wang", "Kazuki Nakajima", "Kai-I Wang", "side_b"),
        ("chan-yeong oh", "Sasikumar Mukund", "Oh Chan-Yeong", "side_b"),
    ],
)
def test_double_barrelled_tennis_names_keep_their_side(
    subject: str, home: str, away: str, side: str
) -> None:
    assert determine_side(subject, _fx(home, away, "tennis")) == side
    assert _named_side(subject, home, away) is (side == "side_a")


@pytest.mark.parametrize(
    ("board", "sofascore"),
    [
        ("Al Wahda", "Al-Wahda FC"),
        ("Umm Salal", "Umm-Salal SC"),
        ("Pablo Carreno-Busta", "Pablo Carreño Busta"),
        ("Anna Lena Friedsam", "Anna-Lena Friedsam"),
        ("Inaki Monte De La Torre", "Inaki Montes-de la Torre"),
    ],
)
def test_resolve_accepts_the_spaced_spelling(board: str, sofascore: str) -> None:
    score = name_score(normalize_name(board), normalize_name(sofascore))
    assert score > NAME_MATCH_THRESHOLD


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("Al Sharjah", "Al-Dhafra"),
        ("Al Gharafa", "Al-Sharjah"),
        ("Jo-Yee Chan", "Oh Chan-Yeong"),
        ("Flamengo PI", "Comercial-PI"),
    ],
)
def test_resolve_still_refuses_a_different_team(a: str, b: str) -> None:
    assert name_score(normalize_name(a), normalize_name(b)) <= NAME_MATCH_THRESHOLD


def test_no_alias_key_is_lost_to_the_fold() -> None:
    # apply_aliases runs on the folded name, so a key with a dash could never
    # match again.
    aliases = get_aliases()
    assert aliases
    for key in aliases:
        assert not any(c in key for c in "-‐‑‒–—−"), key
    # and a Polish exonym spelled with a dash still reaches its alias
    assert apply_aliases(normalize_name("Gwinea-Bissau")) == apply_aliases(
        normalize_name("Gwinea Bissau")
    )


def test_the_fold_invalidates_misses_recorded_before_it() -> None:
    assert MATCH_LOGIC_VERSION >= 7
