"""Three competition names that arrived every day and resolved to nothing.

Resolution is by *token signature*, not substring, so a name the feed sends with
a suffix is a different key from the bare one. Measured on the 2026-09-06 slate,
where these three cost 14 fixtures their only corroborator on both sides and
their h2h -- every Brasileirão Serie A and Liga MX row on the file read
SINGLE_SOURCE with corroborated_matches 0.

Each maps to a code already in ``ESPN_FOOTBALL_LEAGUE_CODES``; no new code is
introduced here, so nothing needs a fresh /teams probe.
"""
import pytest

from bet.api_clients.espn import (
    ESPN_FOOTBALL_LEAGUE_CODES,
    get_espn_league_for_competition,
)


@pytest.mark.parametrize(
    "name,code",
    [
        ("Brasileirão Serie A", "bra.1"),
        ("Brasileirao Serie A", "bra.1"),
        ("Liga MX Apertura", "mex.1"),
        ("Liga MX Clausura", "mex.1"),
        ("Stoiximan Super League", "gre.1"),
    ],
)
def test_the_names_the_feed_actually_sends_now_resolve(name, code):
    assert get_espn_league_for_competition(name) == code
    assert code in ESPN_FOOTBALL_LEAGUE_CODES


@pytest.mark.parametrize(
    "name,code",
    [
        ("Brasileirão Serie B", "bra.2"),
        ("Brasileirao", "bra.1"),
        ("Liga MX", "mex.1"),
        ("Greece Super League", "gre.1"),
    ],
)
def test_the_keys_that_already_worked_still_do(name, code):
    assert get_espn_league_for_competition(name) == code


def test_serie_a_and_serie_b_do_not_collide():
    """The whole reason "Brasileirao Serie B" was authored separately: it used
    to resolve to bra.1. Adding the Serie A key must not undo that."""
    assert get_espn_league_for_competition("Brasileirão Serie A") == "bra.1"
    assert get_espn_league_for_competition("Brasileirão Serie B") == "bra.2"


@pytest.mark.parametrize("bare", ["Super League", "Serie A", "Serie B", "Superliga"])
def test_the_bare_ambiguous_names_are_still_refused(bare):
    """"Super League" is the top flight in several countries and "Serie A" in
    at least three. Authoring a sponsor-prefixed Greek name must not weaken the
    doctrine that the bare token set resolves to nothing."""
    assert get_espn_league_for_competition(bare) is None


@pytest.mark.parametrize("dead", ["Ekstraklasa", "K League 1"])
def test_competitions_whose_espn_code_is_dead_stay_unresolved(dead):
    """pol.1 and kor.1 were among the 21 codes removed on 2026-08-28 for
    returning an empty team directory. These names have no answer and must not
    be given one -- None drops the provider, a wrong pin files another league's
    history under this one."""
    assert get_espn_league_for_competition(dead) is None
