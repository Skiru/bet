"""T10 — card points from /incidents (L3, L4, PULAPKA #4, §5.4a)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from bet.sofa.contracts import GapReason
from bet.sofa.metrics import calculate_cards_points

FIXTURE = Path("tests/fixtures/sofascore/incidents_second_yellow.json")


@pytest.fixture(scope="module")
def variants() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_missing_payload_is_not_zero() -> None:
    """L3: the provider does not write a zero for a red card nobody got."""
    assert calculate_cards_points(None) == GapReason.NO_INCIDENTS


def test_present_payload_with_no_cards_is_a_real_zero() -> None:
    assert calculate_cards_points({"incidents": []}) == (0.0, 0.0)


def test_rescinded_cards_do_not_count() -> None:
    """PULAPKA #4: a rescinded card is documented nowhere and counts nowhere."""
    incidents = {
        "incidents": [
            {
                "incidentType": "card",
                "incidentClass": "yellow",
                "rescinded": True,
                "isHome": True,
            },
            {
                "incidentType": "card",
                "incidentClass": "red",
                "rescinded": True,
                "isHome": False,
            },
        ]
    }
    assert calculate_cards_points(incidents) == (0.0, 0.0)


def test_points_not_yellows() -> None:
    """L4: the market is booking points. A straight red is 2, not 1."""
    incidents = {
        "incidents": [
            {"incidentType": "card", "incidentClass": "yellow", "isHome": True},
            {"incidentType": "card", "incidentClass": "red", "isHome": False},
            {"incidentType": "card", "incidentClass": "yellow", "isHome": False},
        ]
    }
    assert calculate_cards_points(incidents) == (1.0, 3.0)


def test_non_card_incidents_are_ignored() -> None:
    incidents = {
        "incidents": [
            {"incidentType": "goal", "isHome": True},
            {"incidentType": "substitution", "isHome": True},
            {"incidentType": "card", "incidentClass": "yellow", "isHome": True},
        ]
    }
    assert calculate_cards_points(incidents) == (1.0, 0.0)


# --------------------------------------------------------------------------
# §5.4a — the one number the plan said must not be guessed.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "variant",
    ["one_yellow_plus_yellowRed", "two_yellows_plus_yellowRed", "yellowRed_only"],
)
def test_second_yellow_is_three_points_under_every_convention(
    variants: dict[str, Any], variant: str
) -> None:
    """A dismissal for a second yellow is worth 3 booking points at Superbet.

    Whether Sofascore emits zero, one or two separate `yellow` incidents
    alongside the `yellowRed` changes what the remainder should be — and no
    recorded payload answers which it does. So the code does not hold a
    constant: it counts that player's standing yellows and pays the balance.
    All three conventions must therefore give 3, and if Sofascore ever changes
    convention this stays correct without anyone noticing.
    """
    assert calculate_cards_points(variants[variant]) == (3.0, 0.0)


def test_a_rescinded_first_yellow_still_totals_three(
    variants: dict[str, Any],
) -> None:
    """One standing yellow plus a dismissal is still a 3-point disciplinary record."""
    assert calculate_cards_points(variants["rescinded_first_yellow"]) == (3.0, 0.0)


def test_two_players_dismissed_do_not_borrow_each_other_s_yellows() -> None:
    """The remainder is per player. Pooling them under-counts the second one."""
    incidents = {
        "incidents": [
            {
                "incidentType": "card",
                "incidentClass": "yellow",
                "isHome": True,
                "player": {"id": 1},
            },
            {
                "incidentType": "card",
                "incidentClass": "yellowRed",
                "isHome": True,
                "player": {"id": 1},
            },
            {
                "incidentType": "card",
                "incidentClass": "yellow",
                "isHome": True,
                "player": {"id": 2},
            },
            {
                "incidentType": "card",
                "incidentClass": "yellowRed",
                "isHome": True,
                "player": {"id": 2},
            },
        ]
    }
    assert calculate_cards_points(incidents) == (6.0, 0.0)


def test_player_identity_falls_back_to_the_name() -> None:
    incidents = {
        "incidents": [
            {
                "incidentType": "card",
                "incidentClass": "yellow",
                "isHome": False,
                "playerName": "Sergio Ramos",
            },
            {
                "incidentType": "card",
                "incidentClass": "yellowRed",
                "isHome": False,
                "playerName": "Sergio Ramos",
            },
        ]
    }
    assert calculate_cards_points(incidents) == (0.0, 3.0)


def test_an_unattributed_yellow_red_pays_the_full_three() -> None:
    """With no player key there are no yellows to credit, so nothing is netted off.

    Paying 3 is the safe direction: under-counting a dismissal is what makes
    every UNDER on the card market look like a winner.
    """
    incidents = {
        "incidents": [
            {"incidentType": "card", "incidentClass": "yellowRed", "isHome": True}
        ]
    }
    assert calculate_cards_points(incidents) == (3.0, 0.0)


def test_fixture_declares_itself_synthetic(variants: dict[str, Any]) -> None:
    """Nobody may later read this file as a measurement of §5.4a."""
    doc = " ".join(variants["_doc"])
    assert "SYNTHETIC" in doc
