"""A footballer Superbet writes under his full registered name is matched by
whole name tokens (epochs.PLAYER_NAME_TOKENS_FROM_UTC, 2026-10-12 00:00Z).

"Andrade, Matheus Araujo" (Superbet) and "Matheus Araujo" (Sofascore) score
78 under token_sort_ratio, below match_player's 85, so the player had no
sample: 346 of the 680 NO_ENTITY_FOUND players of 2026-10-08..10-10 were such
near names (docs/sofa/evidence/player_name_tokens_2026-10-11.md). The token
rule is a fallback for a player match_player found in NO squad, it needs two
shared tokens and one candidate, and SETTLE grades the name it sampled.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from bet.sofa import epochs
from bet.sofa.contracts import FixtureOffer, GapReason
from bet.sofa.players import match_player, match_player_by_tokens
from bet.sofa.samples import build_player_samples
from scripts.sofa import run_settle
from tests.sofa.test_player_markets import (
    _fixture,
    _player_samples,
    _result,
    _rung,
    _sheet,
)


def _played(shots: float, minutes: float = 90.0) -> dict[str, Any]:
    return {"minutesPlayed": minutes, "totalShots": shots}


# --- the matcher -----------------------------------------------------------


@pytest.mark.parametrize(
    ("superbet", "sofascore"),
    [
        ("Andrade, Matheus Araujo", "matheus araujo"),
        ("Santos Batista, Joao Gabriel", "joao gabriel"),
        ("Goncalves, Julio Cesar", "julio cesar"),
        ("Brock, Eduardo Schroeder", "eduardo brock"),
        # Superbet the shorter one.
        ("Philippe Coutinho", "philippe coutinho correia"),
    ],
)
def test_a_registered_name_finds_the_playing_name(
    superbet: str, sofascore: str
) -> None:
    squad = {sofascore: {}, "piotr nowak": {}, "jan kowalski": {}}
    assert match_player(superbet, squad) is None  # the gap being closed
    assert match_player_by_tokens(superbet, squad) == sofascore


@pytest.mark.parametrize(
    ("superbet", "sofascore"),
    [
        # One shared token: Spearman 0.292 on n=23 - not shown to be him.
        ("Tavares, Lucca", "lucca"),
        ("Bryan", "bryan borges"),
        ("Lima, Vinicius", "lima"),
        # Not contained at all.
        ("Freitas, Rodrigo", "rodrigo fagundes"),
    ],
)
def test_a_lone_token_or_a_different_name_never_matches(
    superbet: str, sofascore: str
) -> None:
    assert match_player_by_tokens(superbet, {sofascore: {}, "piotr nowak": {}}) is None


def test_two_contained_names_are_no_answer() -> None:
    """"carlos" is a one-token name, but it is contained too: the squad holds
    two people the Superbet name could mean, and the rule does not pick."""
    squad = {"joao carlos": {}, "carlos": {}}
    assert match_player_by_tokens("Lopes, Joao Carlos", squad) is None
    assert match_player_by_tokens("Lopes, Joao Carlos", {"joao carlos": {}}) == (
        "joao carlos")


def test_an_empty_squad_or_name_is_no_answer() -> None:
    assert match_player_by_tokens("Andrade, Matheus Araujo", None) is None
    assert match_player_by_tokens("Andrade, Matheus Araujo", {}) is None
    assert match_player_by_tokens("", {"matheus araujo": {}}) is None


# --- SAMPLES ---------------------------------------------------------------

WANT = {"player_shots_for": {"Andrade, Matheus Araujo"}}
KEY = "player_shots_for|Andrade, Matheus Araujo"


def _side(name: str, shots: list[float]) -> list[dict[str, Any]]:
    return [_result(i + 1, {name: _played(s), "piotr nowak": _played(1.0)})
            for i, s in enumerate(shots)]


def test_without_the_switch_the_player_still_has_no_sample() -> None:
    gaps: list[Any] = []
    samples = build_player_samples(
        WANT, {"side_a": _side("matheus araujo", [2, 3, 1]), "side_b": []}, gaps)
    assert samples == {}
    assert [g.detail for g in gaps] == [
        "player 'Andrade, Matheus Araujo' matched no squad member"]


def test_with_the_switch_the_sample_is_his_and_says_how_it_was_found() -> None:
    gaps: list[Any] = []
    samples = build_player_samples(
        WANT, {"side_a": _side("matheus araujo", [2, 3, 1]), "side_b": []}, gaps,
        token_fallback=True)
    sample = samples[KEY]
    assert sample.match_rule == "tokens"
    assert sample.matched_name == "matheus araujo"
    assert sample.side == "side_a"
    assert sorted(o.value for o in sample.observations) == [1.0, 2.0, 3.0]
    assert sample.squad_matches == 3
    assert gaps == []


def test_a_fuzzy_match_is_unchanged_by_the_switch() -> None:
    """The fallback never runs where match_player answered: the same sample,
    `match_rule` "fuzzy", whatever the switch says."""
    want = {"player_shots_for": {"Kowalski, Jan"}}
    sides = {"side_a": _side("jan kowalski", [2, 0]), "side_b": []}
    off = build_player_samples(want, sides, [])
    on = build_player_samples(want, sides, [], token_fallback=True)
    assert off == on
    assert on["player_shots_for|Kowalski, Jan"].match_rule == "fuzzy"


def test_a_bench_player_is_not_re_matched_by_tokens() -> None:
    """Found by match_player but never on the pitch: no appearance is the
    answer, and the gap says that instead of "matched no squad member"."""
    want = {"player_shots_for": {"Kowalski, Jan"}}
    # Squad 2's "jan kowalski pawel" is under match_player's 85 but a token
    # match: a fallback run here would sample him as Jan Kowalski.
    assert match_player("Kowalski, Jan", {"jan kowalski pawel": {}}) is None
    assert match_player_by_tokens("Kowalski, Jan", {"jan kowalski pawel": {}}) == (
        "jan kowalski pawel")
    bench = [_result(1, {"jan kowalski": {"totalShots": 0}}),
             _result(2, {"jan kowalski pawel": _played(4.0)})]
    gaps: list[Any] = []
    samples = build_player_samples(
        want, {"side_a": bench, "side_b": []}, gaps, token_fallback=True)
    assert samples == {}
    assert [g.detail for g in gaps] == [
        "player 'Kowalski, Jan' named in 1 squads, never came on"]


def test_a_token_match_on_both_sides_is_refused() -> None:
    gaps: list[Any] = []
    samples = build_player_samples(
        WANT,
        {"side_a": _side("matheus araujo", [2, 3, 1]),
         "side_b": _side("matheus araujo", [1])},
        gaps, token_fallback=True)
    assert samples == {}
    assert [g.reason for g in gaps] == [GapReason.AMBIGUOUS_ENTITY]


def test_two_different_token_names_on_one_side_are_refused() -> None:
    """One squad reads him as "matheus araujo", another as "matheus andrade":
    two people, or one we cannot place - never a pooled sample."""
    side = _side("matheus araujo", [2]) + [
        _result(5, {"matheus andrade": _played(0.0)})]
    gaps: list[Any] = []
    samples = build_player_samples(
        WANT, {"side_a": side, "side_b": []}, gaps, token_fallback=True)
    assert samples == {}
    assert [g.reason for g in gaps] == [GapReason.AMBIGUOUS_ENTITY]


def test_an_accepted_token_sample_keeps_its_gaps() -> None:
    side_a = _side("matheus araujo", [2, 3]) + [
        _result(5, {"matheus araujo": {"minutesPlayed": 90}})]  # no shots key
    gaps: list[Any] = []
    samples = build_player_samples(
        WANT, {"side_a": side_a, "side_b": []}, gaps, token_fallback=True)
    assert len(samples[KEY].observations) == 2
    assert [g.detail for g in gaps] == [
        "player 'Andrade, Matheus Araujo' event 5 gap"]


def test_a_refused_token_pass_leaves_no_gaps_of_its_own() -> None:
    """A token candidate's missing statistic is a gap only when his sample is
    taken; a refused fallback writes the refusal and nothing else."""
    side_a = [_result(1, {"matheus araujo": {"minutesPlayed": 90}})]  # no shots key
    gaps: list[Any] = []
    build_player_samples(
        WANT, {"side_a": side_a, "side_b": _side("matheus araujo", [1])}, gaps,
        token_fallback=True)
    assert [g.reason for g in gaps] == [GapReason.AMBIGUOUS_ENTITY]


# --- SHEET -----------------------------------------------------------------


def test_the_sheet_row_names_the_token_match() -> None:
    samples = _player_samples([3, 2, 4, 1, 3, 2, 5, 2, 3, 2])
    sample = samples.players["player_shots_for|Romarinho"]
    samples.players["player_shots_for|Romarinho"] = sample.model_copy(
        update={"match_rule": "tokens", "matched_name": "romario silva"})
    offer = FixtureOffer(
        sofascore_event_id=1, status="PRICED",
        rungs=[_rung("player_shots_for", "Romarinho", 1.5, over=2.6)],
        unmapped_markets=[])
    rows = _sheet(_fixture(), samples, offer)
    notes = [n for n in rows[0].notes if n.startswith("PLAYER_NAME_TOKENS")]
    assert notes == ["PLAYER_NAME_TOKENS: Superbet 'Romarinho' read as Sofascore "
                     "'romario silva' by whole name tokens "
                     "(players.match_player_by_tokens)"]


def test_a_fuzzy_sheet_row_carries_no_token_note() -> None:
    offer = FixtureOffer(
        sofascore_event_id=1, status="PRICED",
        rungs=[_rung("player_shots_for", "Romarinho", 1.5, over=2.6)],
        unmapped_markets=[])
    rows = _sheet(_fixture(), _player_samples([3, 2, 4, 1, 3, 2, 5, 2, 3, 2]), offer)
    assert not any(n.startswith("PLAYER_NAME_TOKENS") for n in rows[0].notes)


# --- SETTLE ----------------------------------------------------------------


def _row(subject: str = "Andrade, Matheus Araujo") -> dict[str, Any]:
    return {"market": "player_shots_for", "subject": subject, "line": 1.5,
            "direction": "OVER"}


def test_settle_grades_the_name_samples_sampled() -> None:
    squads = {True: {"matheus araujo": _played(2.0)},
              False: {"piotr nowak": _played(5)}}
    assert run_settle._settle_player(_row(), squads, True) == "PLAYER_NOT_MATCHED"
    assert run_settle._settle_player(_row(), squads, True, "matheus araujo") == (
        2.0, "WIN")


def test_settle_never_uses_the_token_name_without_a_side() -> None:
    squads = {True: {"matheus araujo": _played(2.0)}, False: {}}
    assert run_settle._settle_player(_row(), squads, None, "matheus araujo") == (
        "PLAYER_NOT_MATCHED")


def test_settle_refuses_when_the_other_squad_holds_a_candidate() -> None:
    squads = {True: {"matheus araujo": _played(2.0)},
              False: {"matheus araujo andrade": _played(0.0)}}
    assert run_settle._settle_player(_row(), squads, True, "matheus araujo") == (
        "PLAYER_AMBIGUOUS")


def test_settle_refuses_a_candidate_only_the_token_matcher_sees() -> None:
    """"andrade matheus" scores 81 - under the fuzzy bar - but is a token
    match in the other squad: a second person the name could mean."""
    squads = {True: {"matheus araujo": _played(2.0)},
              False: {"andrade matheus": _played(0.0)}}
    assert run_settle._settle_player(_row(), squads, True, "matheus araujo") == (
        "PLAYER_AMBIGUOUS")


def test_settle_a_token_player_who_did_not_play_is_void() -> None:
    squads = {True: {"matheus araujo": {"totalShots": 0}}, False: {}}
    assert run_settle._settle_player(_row(), squads, True, "matheus araujo") == (
        "PLAYER_DID_NOT_PLAY")


def test_settle_a_token_name_absent_from_the_squad_is_not_matched() -> None:
    squads = {True: {"someone else": _played(2.0)}, False: {}}
    assert run_settle._settle_player(_row(), squads, True, "matheus araujo") == (
        "PLAYER_NOT_MATCHED")


def test_settle_prefers_match_player_when_it_answers() -> None:
    """A row with a token name whose player match_player finds after all (a
    renamed payload, a later squad) is graded the way every row is."""
    squads = {True: {"jan kowalski": _played(3.0)}, False: {}}
    assert run_settle._settle_player(
        _row("Kowalski, Jan"), squads, True, "someone else") == (3.0, "WIN")


def test_the_token_names_come_only_from_token_samples() -> None:
    doc = [{"sofascore_event_id": 7, "players": {
        KEY: {"match_rule": "tokens", "matched_name": "matheus araujo",
              "side": "side_a"},
        "player_shots_for|Kowalski, Jan": {"match_rule": "fuzzy",
                                           "matched_name": "jan kowalski",
                                           "side": "side_b"},
        "player_shots_for|Old": {"matched_name": "old", "side": "side_a"},
    }}]
    assert run_settle.player_token_names(doc) == {(7, KEY): "matheus araujo"}


# --- the switch --------------------------------------------------------------


def test_the_switch_starts_the_next_day_and_never_mid_day() -> None:
    at = datetime(2026, 10, 12, 0, 0, tzinfo=UTC)
    assert epochs.PLAYER_NAME_TOKENS_FROM_UTC == at
    assert epochs.player_name_tokens("2026-10-12", at)
    assert not epochs.player_name_tokens("2026-10-11", at)
    assert not epochs.player_name_tokens("2026-10-12", datetime(2026, 10, 11, 23, 59,
                                                                tzinfo=UTC))
