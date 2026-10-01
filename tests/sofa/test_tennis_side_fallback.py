"""Tennis per-player rungs whose names Superbet and Sofascore spell
differently still find their side - and a name that fits both sides finds
none (review 2026-10-01; pairs from the 2026-09-30 offer)."""

from __future__ import annotations

import pytest

from bet.sofa.contracts import Fixture
from scripts.sofa.run_sheet import determine_side


def _fx(home: str, away: str, sport: str = "tennis") -> Fixture:
    return Fixture.model_construct(sport=sport, home_name=home, away_name=away)


@pytest.mark.parametrize(
    ("subject", "home", "away", "side"),
    [
        ("barakat oyinlomo quadre", "Lan Mi", "Barakat Qyinlomo Quadre", "side_b"),
        (
            "esdras martinez",
            "Wulfrano Martinez Mora Esdras",
            "Abdumalik Kamalov",
            "side_a",
        ),
        ("tai sach", "Tai Leonard Sach", "Jeremy Beale", "side_a"),
        ("rafael alfonso de alba valdes", "Benjamin Lock", "Rafael de Alba", "side_b"),
        ("d.nicolae madaras", "Dragos Nicolae Madaras", "Jeremy Gschwendtner", "side_a"),
        ("heerae im", "Seda Baslilar", "Im Hee Rae", "side_b"),
    ],
)
def test_a_differently_spelled_player_finds_his_side(
    subject: str, home: str, away: str, side: str
) -> None:
    assert determine_side(subject, _fx(home, away)) == side


def test_a_surname_both_players_share_is_no_answer() -> None:
    assert determine_side("martinez", _fx("Pedro Martinez", "Juan Martinez")) is None


def test_an_unrelated_name_is_no_answer() -> None:
    assert determine_side("john smith", _fx("Alex Brown", "Chris Green")) is None


def test_the_fallback_is_tennis_only() -> None:
    football = _fx("Tai Leonard Sach", "Jeremy Beale", "football")
    assert determine_side("tai sach", football) is None
