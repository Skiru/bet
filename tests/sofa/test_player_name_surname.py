"""A footballer Superbet registers under his full name and Sofascore under the
short one he plays by is matched by surname + first-name prefix (identity
plan K7, epochs.PLAYER_NAME_SURNAME_FROM_UTC 2026-10-15 00:00Z).

"Benjamin Joshua Chrisene" / "Ben Chrisene", "Treymaurice Nyoni" / "Trey
Nyoni": neither match_player (similarity) nor the token rule (containment)
bridges a short first name. Measured on 10-12..10-14: 1,827 / 1,827 matched
players picked the same person; with only the first INITIAL 6 were another
man - so the first names must share a prefix of three letters.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from bet.sofa import epochs
from bet.sofa.players import (
    match_player,
    match_player_by_surname,
    match_player_by_tokens,
)
from bet.sofa.samples import build_player_samples
from scripts.sofa import run_settle
from tests.sofa.test_player_markets import _result


def _played(shots: float, minutes: float = 90.0) -> dict[str, Any]:
    return {"minutesPlayed": minutes, "totalShots": shots}


@pytest.mark.parametrize(
    ("superbet", "sofascore"),
    [
        ("Treymaurice Nyoni", "trey nyoni"),
        ("Benjamin Joshua Chrisene", "ben chrisene"),
        ("Samuel Edward Field", "sam field"),
        ("Benjamin Anthony Brereton Díaz", "ben brereton diaz"),
        ("Evan N Dicka", "evan ndicka"),
        ("Phillips, Nat", "nathaniel phillips"),
        ("Arfsten, Max", "maximilian arfsten"),
        ("Francisco Garcia", "fran garcia"),
    ],
)
def test_a_registered_name_finds_the_short_name(superbet: str, sofascore: str) -> None:
    squad = {sofascore: {}, "piotr nowak": {}, "jan kowalski": {}}
    assert match_player(superbet, squad) is None
    assert match_player_by_tokens(superbet, squad) is None
    assert match_player_by_surname(superbet, squad) == sofascore


@pytest.mark.parametrize(
    ("superbet", "sofascore"),
    [
        # 10-12..10-14: the first-initial rule picked these - other men
        ("Reina Campos, Alberto", "andres campos"),
        ("Leonardo Caetano Silva", "lucas silva"),
        ("Edenilson Andrade dos Santos", "eduardo santos"),
        # a surname inside another surname is not it
        ("Berg, Patrick", "nicolai remberg"),
        # a two-letter prefix is not enough; a one-word name has no surname
        ("Jo Smith", "joe smith"),
        ("Pablo", "pablo felipe"),
    ],
)
def test_another_man_or_too_little_never_matches(superbet: str, sofascore: str) -> None:
    assert match_player_by_surname(superbet, {sofascore: {}, "piotr nowak": {}}) is None


def test_two_candidates_are_no_answer() -> None:
    squad = {"ben smith": {}, "benjamin smith": {}}
    assert match_player_by_surname("Benjamin Smith", squad) is None
    assert match_player_by_surname("Benjamin Smith", {"ben smith": {}}) == "ben smith"
    assert match_player_by_surname("Benjamin Smith", None) is None


WANT = {"player_shots_for": {"Benjamin Joshua Chrisene"}}
KEY = "player_shots_for|Benjamin Joshua Chrisene"


def _side(name: str, shots: list[float]) -> list[dict[str, Any]]:
    return [
        _result(i + 1, {name: _played(s), "piotr nowak": _played(1.0)})
        for i, s in enumerate(shots)
    ]


def test_samples_use_the_surname_only_with_the_switch_and_after_the_others() -> None:
    sides = {"side_a": _side("ben chrisene", [2, 3, 1]), "side_b": []}
    assert build_player_samples(WANT, sides, [], token_fallback=True) == {}
    gaps: list[Any] = []
    on = build_player_samples(
        WANT, sides, gaps, token_fallback=True, surname_fallback=True
    )
    sample = on[KEY]
    assert (sample.match_rule, sample.matched_name, sample.side) == (
        "surname",
        "ben chrisene",
        "side_a",
    )
    assert sorted(o.value for o in sample.observations) == [1.0, 2.0, 3.0]
    # a token match keeps its rule: the surname pass never runs there
    want = {"player_shots_for": {"Andrade, Matheus Araujo"}}
    tok = build_player_samples(
        want,
        {"side_a": _side("matheus araujo", [2]), "side_b": []},
        [],
        token_fallback=True,
        surname_fallback=True,
    )
    assert tok["player_shots_for|Andrade, Matheus Araujo"].match_rule == "tokens"


def test_a_surname_hit_on_both_sides_is_refused() -> None:
    sides = {
        "side_a": _side("ben chrisene", [2]),
        "side_b": _side("benjamin chrisene", [1]),
    }
    assert build_player_samples(WANT, sides, [], surname_fallback=True) == {}


def _row(subject: str = "Benjamin Joshua Chrisene") -> dict[str, Any]:
    return {
        "market": "player_shots_for",
        "subject": subject,
        "line": 1.5,
        "direction": "OVER",
    }


def test_settle_grades_the_surname_name_and_refuses_a_rival() -> None:
    squads = {True: {"ben chrisene": _played(2.0)}, False: {"piotr nowak": _played(5)}}
    assert run_settle._settle_player(_row(), squads, True) == "PLAYER_NOT_MATCHED"
    assert run_settle._settle_player(_row(), squads, True, "ben chrisene") == (
        2.0,
        "WIN",
    )
    rival = {
        True: {"ben chrisene": _played(2.0)},
        False: {"benjamin chrisene": _played(0)},
    }
    assert run_settle._settle_player(_row(), rival, True, "ben chrisene") == (
        "PLAYER_AMBIGUOUS"
    )
    doc = [
        {
            "sofascore_event_id": 7,
            "players": {
                KEY: {
                    "match_rule": "surname",
                    "matched_name": "ben chrisene",
                    "side": "side_a",
                }
            },
        }
    ]
    assert run_settle.player_token_names(doc) == {(7, KEY): "ben chrisene"}


def test_the_switch_starts_the_next_day() -> None:
    assert epochs.PLAYER_NAME_SURNAME_FROM_UTC == datetime(2026, 10, 15, tzinfo=UTC)
    assert epochs.player_name_surname(
        "2026-10-15", datetime(2026, 10, 15, 0, 1, tzinfo=UTC)
    )
    assert not epochs.player_name_surname(
        "2026-10-14", datetime(2026, 10, 15, 6, tzinfo=UTC)
    )
    assert not epochs.player_name_surname(
        "2026-10-15", datetime(2026, 10, 14, 23, tzinfo=UTC)
    )
