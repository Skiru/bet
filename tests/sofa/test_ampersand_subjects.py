"""A club named with "&" is a subject; a Superbet combination with "&" is not.

Names and listings are real: the unmapped markets and the board matchNames of
runs/sofa/2026-09-18..10-05 (04_offer.json, 01_board.json). Over those days
77,474 unmapped names carried "&"; the rule admits 37 of them, every one a
club's own goals line, and no combination.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from bet.sofa import epochs
from bet.sofa.contracts import Fixture
from bet.sofa.market_mapper import classify_market, subject_is_combination
from bet.sofa.offer import OfferFetcher, classify_odd, listing_sides
from bet.sofa.timeutil import now

DAGENHAM = ("Dagenham & Redbridge", "Waltham Abbey")


@pytest.mark.parametrize(
    ("name", "sides", "expected"),
    [
        ("Dagenham & Redbridge - liczba goli", DAGENHAM,
         ("goals_for", "dagenham & redbridge")),
        ("1.połowa - Dagenham & Redbridge - liczba goli", DAGENHAM,
         ("goals_1h_for", "dagenham & redbridge")),
        ("2.połowa - Havant & Waterlooville - liczba goli",
         ("Havant & Waterlooville", "Hanwell Town"),
         ("goals_2h_for", "havant & waterlooville")),
        ("H&W Welders - liczba goli", ("Newry City", "H&W Welders"),
         ("goals_for", "h&w welders")),
        ("MEG & Centre FC - liczba goli", ("MEG & Centre FC", "SC Bengaluru"),
         ("goals_for", "meg & centre fc")),
    ],
)
def test_a_club_named_with_an_ampersand_is_its_own_subject(
    name: str, sides: tuple[str, str], expected: tuple[str, str]
) -> None:
    assert classify_market(name, sides) == expected


@pytest.mark.parametrize(
    ("name", "sides"),
    [
        # Superbet's combined markets: "&" is the operator, and the captured
        # prefix is never a side - not even when it names one.
        ("Mecz & liczba gemów", ("Borna Gojo", "Titouan Droguet")),
        ("1. set - zwycięzca & liczba gemów", ("Holger Rune", "Iliyan Radulov")),
        ("Mecz & Deportivo Cali liczba goli (2.5)", ("Deportivo Cali", "Millonarios")),
        ("Mecz & Dagenham & Redbridge - liczba goli", DAGENHAM),
    ],
)
def test_a_superbet_combination_stays_refused(
    name: str, sides: tuple[str, str]
) -> None:
    assert classify_market(name, sides) is None


def test_without_the_listing_sides_every_ampersand_is_refused_as_before() -> None:
    assert classify_market("Dagenham & Redbridge - liczba goli") is None
    assert classify_market("Waltham Abbey - liczba goli") == (
        "goals_for", "waltham abbey")


def test_a_semicolon_is_a_parlay_even_when_it_reads_like_a_side() -> None:
    assert subject_is_combination("a; b", ("a; b",))
    assert subject_is_combination("dagenham & redbridge", ("Waltham Abbey",))
    assert not subject_is_combination("dagenham & redbridge", DAGENHAM)
    assert not subject_is_combination("waltham abbey", ())


def test_listing_sides_reads_superbets_own_match_name() -> None:
    assert listing_sides({"matchName": "Dagenham & Redbridge·Hampton & Richmond"}) == (
        "Dagenham & Redbridge", "Hampton & Richmond")
    assert listing_sides({}) == ()
    assert listing_sides(None) == ()


def test_classify_odd_passes_the_sides_through() -> None:
    item = {"marketName": "Dagenham & Redbridge - liczba goli",
            "specialBetValue": "1.5", "name": "Powyżej 1.5", "price": 1.9}
    assert classify_odd(item) == (None, "Dagenham & Redbridge - liczba goli")
    assert classify_odd(item, DAGENHAM) == (
        ("goals_for", "dagenham & redbridge", 1.5, "OVER"), None)


def _fixture() -> Fixture:
    return Fixture(
        sofascore_event_id=1, superbet_event_ids=["101"], sport="football",
        kickoff_utc=now(), home_name="Dagenham & Redbridge",
        away_name="Waltham Abbey", home_entity_id=1, away_entity_id=2,
        competition_name="FA Cup", competition_id=3, season_id=4,
        category_name="England", identity="CONFIRMED", round_number=None,
        round_name=None, cup_round_type=None, previous_leg_event_id=None,
        venue_name=None, referee=None, ground_type=None, default_period_count=2,
    )


class _Client:
    def event_odds(self, event_id: str) -> dict[str, Any]:
        return {
            "matchName": "Dagenham & Redbridge·Waltham Abbey",
            "odds": [
                {"marketName": "Dagenham & Redbridge - liczba goli",
                 "specialBetValue": "1.5", "name": "Powyżej 1.5", "price": 1.9},
                {"marketName": "Dagenham & Redbridge - liczba goli",
                 "specialBetValue": "1.5", "name": "Poniżej 1.5", "price": 1.85},
                {"marketName": "Mecz & liczba goli (2.5)",
                 "specialBetValue": "2.5", "name": "1 i powyżej 2.5", "price": 2.6},
            ],
        }


@pytest.mark.parametrize("on", [True, False])
def test_offer_maps_the_ampersand_club_only_when_the_epoch_allows(on: bool) -> None:
    [offer] = OfferFetcher(_Client(), ampersand_subjects=on).fetch_offers([_fixture()])
    subjects = {(r.market, r.subject) for r in offer.rungs}
    assert (("goals_for", "dagenham & redbridge") in subjects) is on
    assert ("Dagenham & Redbridge - liczba goli" in offer.unmapped_markets) is not on
    # The combination is unmapped either way.
    assert "Mecz & liczba goli (2.5)" in offer.unmapped_markets


def test_the_epoch_starts_on_10_06_and_leaves_10_05_alone() -> None:
    late_on_10_05 = datetime(2026, 10, 5, 23, 59, tzinfo=UTC)
    first_of_10_06 = datetime(2026, 10, 6, 0, 0, tzinfo=UTC)
    assert not epochs.ampersand_subjects("2026-10-05", late_on_10_05)
    assert not epochs.ampersand_subjects("2026-10-05", first_of_10_06)
    assert not epochs.ampersand_subjects("2026-10-06", late_on_10_05)
    assert epochs.ampersand_subjects("2026-10-06", first_of_10_06)
