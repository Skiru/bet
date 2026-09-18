"""Club affixes, squad level and Polish exonyms in the opponent-name gate (F50).

On 2026-09-18 two fixtures from Europe's biggest leagues — Monaco·Lens and
Bayern Monachium·Union Berlin — were on the Superbet board, had the right
Sofascore event found and in window, passed the gender and orientation gates,
and were then thrown away on the name:

    fuzz.ratio("lens", "rc lens")                     72.7
    fuzz.ratio("bayern monachium", "fc bayern munchen") 66.7

against a threshold of 85. Neither is a near-miss of identity; one is a club
prefix the two sources spell differently and the other is a city's Polish name.

Measured over the day's 982 (board side -> Sofascore side) pairs, with every
other team name of the same sport that day as the negative set:

    fuzz.ratio             @85   recall 86.5%   11 false pairs / 496,058
    name_score + level     @82   recall 97.0%   11 false pairs / 496,058
"""

from datetime import UTC, datetime

import pytest

from bet.sofa.names import levels_compatible, normalize_name, team_levels
from bet.sofa.resolve import NAME_MATCH_THRESHOLD, SofaResolver, name_score

KICKOFF = datetime(2026, 9, 18, 18, 45, tzinfo=UTC)


class _Resolver(SofaResolver):
    def __init__(self):  # no config, no client, no cache: pure matching
        pass


def _event(home: str, away: str, *, tournament: str = "Ligue 1") -> dict:
    return {
        "id": 1,
        "startTimestamp": int(KICKOFF.timestamp()),
        "homeTeam": {"name": home},
        "awayTeam": {"name": away},
        "tournament": {"name": tournament, "slug": tournament.lower()},
    }


# --- the two fixtures that were lost -------------------------------------


def test_monaco_lens_resolves():
    event = _event("AS Monaco", "RC Lens")
    assert _Resolver()._is_match(
        event,
        KICKOFF,
        normalize_name("Lens"),
        sport="football",
        superbet_side_a="Monaco",
        superbet_side_b="Lens",
    )


def test_bayern_union_berlin_resolves():
    event = _event("FC Bayern München", "1. FC Union Berlin", tournament="Bundesliga")
    assert _Resolver()._is_match(
        event,
        KICKOFF,
        normalize_name("Bayern Monachium"),
        sport="football",
        superbet_side_a="Bayern Monachium",
        superbet_side_b="Union Berlin",
    )


# --- what the scorer must and must not do ---------------------------------


@pytest.mark.parametrize(
    ("board", "sofascore"),
    [
        ("lens", "rc lens"),
        ("monaco", "as monaco"),
        ("union berlin", "1. fc union berlin"),
        ("napoli", "ssc napoli"),
        ("koln", "1. fc koln"),
        ("brugge", "club brugge kv"),
    ],
)
def test_a_club_affix_is_not_a_difference(board, sofascore):
    assert name_score(board, sofascore) > NAME_MATCH_THRESHOLD


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("manchester united", "manchester city"),
        ("real madrid", "real sociedad"),
        ("atletico madrid", "athletic bilbao"),
        ("bayern munchen", "werder bremen"),
    ],
)
def test_two_different_clubs_still_fail(a, b):
    assert name_score(a, b) <= NAME_MATCH_THRESHOLD


# --- squad level ----------------------------------------------------------


def test_a_senior_side_is_not_its_own_academy():
    """The case a token-set score cannot see: "flamengo" is a strict subset."""
    assert name_score("flamengo", "flamengo de guarulhos u20") == 100.0
    assert not levels_compatible("flamengo", "flamengo de guarulhos u20")


def test_the_level_gate_rejects_the_academy_match():
    event = _event("Flamengo de Guarulhos U20", "Jaguar PE U20")
    assert not _Resolver()._is_match(
        event,
        KICKOFF,
        normalize_name("Flamengo"),
        sport="football",
        superbet_side_a="Jaguar PE",
        superbet_side_b="Flamengo",
    )


def test_a_name_carrying_both_markers_matches_either():
    """Panama's "Plaza Amador Reserves U20" is the board's "Plaza Amador (R)"."""
    assert team_levels("plaza amador reserves u20") == frozenset({"R", "U20"})
    assert levels_compatible("plaza amador (r)", "plaza amador reserves u20")


def test_an_unmarked_name_is_senior():
    assert team_levels("as monaco") == frozenset({"S"})
    assert levels_compatible("as monaco", "monaco")


# --- exonyms --------------------------------------------------------------


@pytest.mark.parametrize(
    ("polish", "local"),
    [
        ("Bayern Monachium", "FC Bayern München"),
        ("Rapid Bukareszt", "FC Rapid București"),
        ("RB Lipsk", "RB Leipzig"),
        ("Werder Brema", "SV Werder Bremen"),
        ("Rapid Wieden", "SK Rapid Wien"),
        ("Dynamo Kijow", "Dynamo Kyiv"),
        ("FC Kopenhaga", "FC København"),
        ("Szachtar Donieck", "Shakhtar Donetsk"),
        ("Dukla Praga", "Dukla Praha"),
        ("AEK Ateny", "AEK Athens"),
        ("Real Madryt", "Real Madrid"),
    ],
)
def test_a_polish_exonym_reaches_the_local_spelling(polish, local):
    assert name_score(normalize_name(polish), normalize_name(local)) >= 99.0


def test_an_alias_applies_where_the_word_is_not_a_country_at_the_front():
    """The old table only rewrote the FIRST word, which is where a country
    sits and is not where a city sits."""
    assert normalize_name("Bayern Monachium") == "bayern munchen"
    assert normalize_name("Polska") == "poland"
    assert normalize_name("Stany Zjednoczone") == "usa"


# --- identity stays a fact ------------------------------------------------


def test_a_subset_match_is_reported_as_fuzzy_not_confirmed():
    """`match_quality` gates on the relaxed score and REPORTS the strict one.

    Accepting "Lens" as "RC Lens" is right; calling the two strings identical
    is not, and `identity` is published as CONFIRMED on exactly that number.
    """
    quality = _Resolver().match_quality(
        _event("AS Monaco", "RC Lens"),
        KICKOFF,
        normalize_name("Lens"),
        sport="football",
        superbet_side_a="Monaco",
        superbet_side_b="Lens",
    )
    assert quality is not None
    assert quality < 99.0


def test_an_exact_name_is_still_confirmed():
    quality = _Resolver().match_quality(
        _event("AS Monaco", "RC Lens"),
        KICKOFF,
        normalize_name("RC Lens"),
        sport="football",
        superbet_side_a="AS Monaco",
        superbet_side_b="RC Lens",
    )
    assert quality == 100.0
