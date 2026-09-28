"""Country exonyms in the opponent-name gate (2026-09-28).

During the September international break 13 of the 17 national-team fixtures
on 2026-09-28's board failed RESOLVE, although Sofascore listed every one of
them. The Polish name never became Sofascore's:

    turkey            vs turkiye            76.9
    ireland polnocna  vs northern ireland   68.8
    czarnogora        vs montenegro         30.0

against a threshold of 82. Two table entries ("włochy", "korea płd") could
never fire at all, because `normalize_name` folds "ł" to "l" before it looks
the alias up.
"""

from datetime import UTC, datetime

import pytest

from bet.sofa.names import get_aliases, normalize_name
from bet.sofa.resolve import SofaResolver

KICKOFF = datetime(2026, 9, 28, 18, 45, tzinfo=UTC)


class _Resolver(SofaResolver):
    def __init__(self):  # no config, no client, no cache: pure matching
        pass


def _event(home: str, away: str) -> dict:
    tournament = "UEFA Nations League, League A, Gr. 1"
    return {
        "id": 1,
        "startTimestamp": int(KICKOFF.timestamp()),
        "homeTeam": {"name": home},
        "awayTeam": {"name": away},
        "tournament": {"name": tournament, "slug": "uefa-nations-league"},
    }


@pytest.mark.parametrize(
    ("board_a", "board_b", "home", "away"),
    [
        ("Turcja", "Włochy", "Türkiye", "Italy"),
        ("Irlandia Północna", "Węgry", "Northern Ireland", "Hungary"),
        ("Armenia", "Czarnogóra", "Armenia", "Montenegro"),
        ("Gruzja", "Ukraina", "Georgia", "Ukraine"),
        ("Łotwa", "Cypr", "Latvia", "Cyprus"),
        ("Korea Płd.", "Urugwaj", "South Korea", "Uruguay"),
    ],
)
def test_nations_league_fixture_resolves_from_either_side(
    board_a: str, board_b: str, home: str, away: str
) -> None:
    event = _event(home, away)
    for opponent in (board_a, board_b):
        assert _Resolver()._is_match(
            event,
            KICKOFF,
            normalize_name(opponent),
            sport="football",
            superbet_side_a=board_a,
            superbet_side_b=board_b,
        ), opponent


def test_czechy_is_czechia_as_sofascore_spells_it() -> None:
    assert normalize_name("Czechy") == normalize_name("Czechia")


def test_every_alias_key_is_reachable() -> None:
    # apply_aliases runs on the folded, lower-case, ASCII name; a key with a
    # diacritic or a capital is a dead entry that looks like coverage.
    dead = [k for k in get_aliases() if not k.isascii() or k != k.lower()]
    assert dead == []
