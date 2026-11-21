"""The opponent may not match the side the searched team stands on.

2026-11-21: board "CD Tenerife C·Real Union Tenerife" (16:00Z, regional
league) searched "CD Tenerife C", found CD Tenerife - Mallorca (20:00Z,
inside the 4 h window), and its opponent "Real Union Tenerife" cleared the
name threshold on CD Tenerife itself (84.2). OFFER then merged two Superbet
events into sofa:16418334 (29 price collisions, a foreign kickoff clock).
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from bet.sofa.names import normalize_name
from bet.sofa.resolve import SofaResolver

KICKOFF = datetime(2026, 11, 21, 20, 0, tzinfo=UTC)


class _Resolver(SofaResolver):
    def __init__(self) -> None:  # pure matching, no IO
        pass


def _event(home: str, away: str) -> dict[str, Any]:
    return {
        "id": 16418334,
        "startTimestamp": int(KICKOFF.timestamp()),
        "homeTeam": {"name": home},
        "awayTeam": {"name": away},
        "tournament": {"name": "LaLiga 2", "slug": "laliga-2"},
    }


def test_same_city_reserve_pair_does_not_bind_to_first_team_game() -> None:
    assert not _Resolver()._is_match(
        _event("CD Tenerife", "Mallorca"),
        KICKOFF - timedelta(hours=4),
        normalize_name("Real Union Tenerife"),
        sport="football",
        superbet_side_a="CD Tenerife C",
        superbet_side_b="Real Union Tenerife",
    )


def test_real_pair_still_resolves() -> None:
    assert _Resolver()._is_match(
        _event("CD Tenerife", "Mallorca"),
        KICKOFF,
        normalize_name("Mallorca"),
        sport="football",
        superbet_side_a="Tenerife",
        superbet_side_b="Mallorca",
    )


def test_searched_by_alias_keeps_both_sides() -> None:
    # The searched name clears neither side (found by id / alias): no side
    # is guessed for it, the opponent is matched as before.
    assert _Resolver()._is_match(
        _event("Tottenham Hotspur", "Arsenal"),
        KICKOFF,
        normalize_name("Arsenal"),
        sport="football",
        superbet_side_a="Spurs",
        superbet_side_b="Arsenal",
    )


def test_same_city_derby_with_agreeing_clocks_still_resolves() -> None:
    # 2026-10-26: the opponent's city name lands on the searched side, but
    # both clocks agree to the minute - a derby, not a foreign game.
    event = _event("Los Angeles FC", "LA Galaxy")
    assert _Resolver()._is_match(
        event,
        KICKOFF,
        normalize_name("Los Angeles Galaxy"),
        sport="football",
        superbet_side_a="Los Angeles FC",
        superbet_side_b="Los Angeles Galaxy",
    )
