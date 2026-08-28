"""ESPN league resolution: what the map may assert, and where it must stay silent.

A wrong answer here is worse than none. `_provider_client` pins the ESPN client
to whatever code comes back, so a bad pin sends a Saudi club into a Premier
League team search -- which either finds nothing (a data_gap blaming the team
name for a league problem) or quietly answers with the wrong club's season.
"""
import pytest

from bet.api_clients.espn import get_espn_league_for_competition as resolve


@pytest.mark.parametrize(
    "competition, expected",
    [
        # The odds-api feed names England's top flight "EPL". Without this the
        # best-corroborated league in the sheet resolved to None and every one
        # of its rows came back SINGLE_SOURCE (measured 2026-08-28).
        ("EPL", "eng.1"),
        ("epl", "eng.1"),
        ("Premier League", "eng.1"),
        ("English Premier League", "eng.1"),
    ],
)
def test_englands_top_flight_resolves_under_every_name_a_feed_uses(competition, expected):
    assert resolve(competition) == expected


@pytest.mark.parametrize(
    "competition",
    ["Kepler Cup", "Deportivo Epla", "Epsom Town"],
)
def test_a_three_letter_abbreviation_does_not_match_mid_word(competition):
    """"epl" sits inside "kepler" and "epsom". Matched as a bare substring it
    would win on longest-match and hand an unrelated fixture to eng.1 -- the
    map would stop asserting and start guessing."""
    assert resolve(competition) != "eng.1"


@pytest.mark.parametrize(
    "competition, expected",
    [("Euro 2028", "uefa.euro"), ("MLS Cup", "usa.1"), ("UCL", "uefa.champions")],
)
def test_short_keys_still_resolve_as_whole_words(competition, expected):
    """Word-boundary matching, not exact-only: an exact-only rule would drop
    every abbreviation that appears inside a longer real name."""
    assert resolve(competition) == expected


@pytest.mark.parametrize(
    "competition, expected",
    [
        ("Nigerian Premier League", "nga.1"),
        ("Ukrainian Premier League", "ukr.1"),
        ("Israeli Premier League", "isr.1"),
        ("Egyptian Premier League", "egy.1"),
        ("Championship", "eng.2"),
        ("Chinese Super League", "chn.1"),
        ("Saudi Pro League", "sau.1"),
        ("Ekstraklasa", "pol.1"),
        ("WSL", "eng.w.1"),
        ("NWSL", "usa.w.1"),
    ],
)
def test_a_longer_specific_name_still_beats_the_generic_one(competition, expected):
    """Longest-match ordering must survive the short-key change: every one of
    these contains a shorter key that would otherwise capture it."""
    assert resolve(competition) == expected


def test_an_unknown_competition_stays_unresolved():
    assert resolve("Totally Invented Cup") is None
    assert resolve("") is None
