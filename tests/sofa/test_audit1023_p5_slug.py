"""P5 of the coverage audit 2026-10-23 (B5): a footballer's Sofascore slug
read as a second name (epochs.PLAYER_SLUG_NAME_FROM_UTC).

Superbet writes "Julian Chabot"; Sofascore's `name` is "Jeff Chabot" and its
slug "julian-chabot" (Stuttgart). Off: no squad member matches and the player
has no sample. On: the slug matcher finds him, last of every fallback, only
when exactly one squad member carries that slug.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, get_args

import pytest

from bet.sofa.contracts import GapEntry, GapReason, PlayerSample
from bet.sofa.players import SLUG_NAME_KEY, match_player_by_slug, squad_statistics
from bet.sofa.samples import build_player_samples


def entry(name: str, slug: str, shots: int = 1) -> dict[str, Any]:
    return {"player": {"name": name, "slug": slug, "id": hash(slug) % 10**6},
            "substitute": False,
            "statistics": {"minutesPlayed": 90, "totalShots": shots}}


def lineups(*extra: dict[str, Any]) -> dict[str, Any]:
    players = [entry("Jeff Chabot", "julian-chabot", 2),
               entry("Angelo Stiller", "angelo-stiller"), *extra]
    return {"home": {"players": players}, "away": {"players": []}}


def squad(slug_name: bool, *extra: dict[str, Any]) -> dict[str, dict[str, Any]]:
    got = squad_statistics(lineups(*extra), is_home=True, slug_name=slug_name)
    assert got is not None
    return got


def test_off_no_slug_is_recorded() -> None:
    assert all(SLUG_NAME_KEY not in st for st in squad(False).values())


def test_on_the_slug_is_a_second_name() -> None:
    assert squad(True)["jeff chabot"][SLUG_NAME_KEY] == "julian chabot"
    assert match_player_by_slug("Julian Chabot", squad(True)) == "jeff chabot"
    assert match_player_by_slug("Chabot, Julian", squad(True)) == "jeff chabot"


def test_the_slug_matcher_refuses_what_it_cannot_tell() -> None:
    assert match_player_by_slug("Julian Chabot", squad(False)) is None
    assert match_player_by_slug("Chabot", squad(True)) is None  # one token
    two = squad(True, entry("J. Chabot", "julian-chabot"))
    assert match_player_by_slug("Julian Chabot", two) is None
    assert match_player_by_slug("Julian Stiller", squad(True)) is None


def results(slug_name: bool) -> dict[str, list[dict[str, Any]]]:
    side_a = [
        {"event_id": 100 + i, "squad": squad(slug_name),
         "match_date_utc": datetime(2026, 10, 1 + i, tzinfo=UTC),
         "opponent": "X", "competition_id": 35, "season_id": 1, "venue": "home"}
        for i in range(6)
    ]
    return {"side_a": side_a, "side_b": []}


# contracts.PlayerSample.match_rule must admit "slug" (and run_settle's
# player_token_names grade a "slug" sample by matched_name) before the switch
# may go on: neither file is this fix's (report A-football, P5).
CONTRACT_HAS_SLUG = "slug" in get_args(
    PlayerSample.model_fields["match_rule"].annotation)


@pytest.mark.xfail(not CONTRACT_HAS_SLUG, strict=True,
                   reason="contracts.PlayerSample.match_rule lacks 'slug'")
def test_build_player_samples_both_switch_states() -> None:
    wanted = {"player_shots_for": {"Julian Chabot"}}
    gaps: list[GapEntry] = []
    off = build_player_samples(wanted, results(False), gaps, token_fallback=True,
                               surname_fallback=True)
    assert off == {}
    assert [g.reason for g in gaps] == [GapReason.NO_ENTITY_FOUND]
    on = build_player_samples(wanted, results(True), [], token_fallback=True,
                              surname_fallback=True, slug_fallback=True)
    (sample,) = on.values()
    assert str(sample.match_rule) == "slug"
    assert sample.matched_name == "jeff chabot"
    assert [o.value for o in sample.observations] == [2.0] * 6


def test_a_name_another_rule_finds_never_reads_the_slug() -> None:
    wanted = {"player_shots_for": {"Angelo Stiller"}}
    on = build_player_samples(wanted, results(True), [], slug_fallback=True)
    assert next(iter(on.values())).match_rule == "fuzzy"
