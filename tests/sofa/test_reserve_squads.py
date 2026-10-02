"""A club's second squad under the first team's id (2026-10-02).

Londrina (Serie B) carried five Copa Parana matches - played by its U23 - into
its sample for Londrina - Criciuma, one of them 25 h after a Serie B match.
These pin the rule in reserve_squads: two schedule clashes make a (side,
competition) pair a second squad; a listed competition decides for the main
competitions measured to field reserves there; a genuine cup with no clash
stays; with no list and no clash nothing changes; the rating moves neither
side on a second squad's match.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

import bet.sofa.samples as samples
from bet.sofa.contracts import Fixture, GapEntry, GapReason
from bet.sofa.football_rating import (
    FootballResult,
    RatingBook,
    mark_second_squads,
)
from bet.sofa.reserve_squads import (
    CLASH_MAX_S,
    MIN_CLASHES,
    TeamMatch,
    load_reserve_competitions,
    reserve_event_ids,
    reserve_fingerprint,
)
from bet.sofa.samples import get_historical_events, second_squad_matches

REPO = Path(__file__).resolve().parents[2]
ME = 7
H = 3600
WEEK = 7 * 24 * H
T0 = 1_790_000_000  # the fixture's kick-off
LEAGUE, RESERVE_CUP, CUP = 390, 24285, 373


def ev(
    eid: int, ts: int, comp: int, opp: int, gf: int = 1, ga: int = 0
) -> dict[str, Any]:
    return {
        "id": eid,
        "startTimestamp": ts,
        "status": {"type": "finished", "code": 100},
        "tournament": {"uniqueTournament": {"id": comp}},
        "homeTeam": {"id": ME, "name": "Me"},
        "awayTeam": {"id": opp, "name": f"Opp {opp}"},
        "homeScore": {"current": gf},
        "awayScore": {"current": ga},
    }


def league(n: int = 12) -> list[dict[str, Any]]:
    """A league match every Saturday before the fixture."""
    return [ev(100 + k, T0 - k * WEEK, LEAGUE, 200 + k) for k in range(1, n + 1)]


def ids(events: list[dict[str, Any]]) -> set[int]:
    return {int(e["id"]) for e in events}


# --- the rule -------------------------------------------------------------


def test_reserve_cup_with_two_clashes_is_a_second_squad_whole() -> None:
    # Two cup matches 25 h after a league match (Londrina, 09-20/21), one
    # four days away: all three are the second squad's.
    events = league() + [
        ev(501, T0 - 1 * WEEK + 25 * H, RESERVE_CUP + 1, 301),
        ev(502, T0 - 3 * WEEK + 30 * H, RESERVE_CUP + 1, 302),
        ev(503, T0 - 5 * WEEK + 96 * H, RESERVE_CUP + 1, 303),
    ]
    reserve, fixture_is_reserve = second_squad_matches(events, LEAGUE, T0, listed={})
    assert reserve == {501, 502, 503}
    assert not fixture_is_reserve


def test_a_genuine_cup_with_no_clash_is_kept() -> None:
    # Copa do Brasil midweek, three or four days from the league: one squad.
    events = league() + [
        ev(601, T0 - 2 * WEEK + 72 * H, CUP, 401),
        ev(602, T0 - 4 * WEEK + 96 * H, CUP, 402),
        ev(603, T0 - 6 * WEEK + 80 * H, CUP, 403),
    ]
    reserve, _ = second_squad_matches(events, LEAGUE, T0, listed={})
    assert reserve == frozenset()


def test_one_clash_is_not_enough() -> None:
    # A single clash fired on genuine national cups (Slovnaft Cup, Israel
    # State Cup) when measured; MIN_CLASHES is two.
    assert MIN_CLASHES == 2
    events = league() + [
        ev(701, T0 - 2 * WEEK + 26 * H, CUP, 401),
        ev(702, T0 - 4 * WEEK + 96 * H, CUP, 402),
    ]
    assert second_squad_matches(events, LEAGUE, T0, listed={})[0] == frozenset()


def test_a_clash_needs_the_main_competition_and_the_window() -> None:
    # Two cups clashing with each other, not with the league, prove nothing
    # about the league squad; a 45 h gap is outside CLASH_MAX_S.
    assert CLASH_MAX_S == 44 * H
    events = league() + [
        ev(801, T0 - 2 * WEEK + 80 * H, CUP, 401),
        ev(802, T0 - 2 * WEEK + 100 * H, CUP + 1, 402),
        ev(803, T0 - 4 * WEEK + 45 * H, CUP + 2, 403),
        ev(804, T0 - 6 * WEEK + 45 * H, CUP + 2, 404),
    ]
    assert second_squad_matches(events, LEAGUE, T0, listed={})[0] == frozenset()


def test_listed_competition_decides_without_a_clash() -> None:
    # No lineups (Copa Parana publishes none) and no clash: the list decides
    # for a side whose main competition is listed as fielding reserves there.
    events = league() + [
        ev(901, T0 - 2 * WEEK + 96 * H, RESERVE_CUP, 501),
        ev(902, T0 - 4 * WEEK + 96 * H, RESERVE_CUP, 502),
    ]
    listed = {RESERVE_CUP: frozenset({LEAGUE})}
    assert second_squad_matches(events, LEAGUE, T0, listed=listed)[0] == {901, 902}
    # The same cup for a side from a main competition not listed (a Serie D
    # club whose first team plays it out of season) stays.
    other = {RESERVE_CUP: frozenset({325})}
    assert second_squad_matches(events, LEAGUE, T0, listed=other)[0] == frozenset()


def test_the_main_competition_itself_is_never_a_second_squad() -> None:
    # A club whose main competition IS the listed cup keeps every match.
    events = [ev(100 + k, T0 - k * WEEK, RESERVE_CUP, 200 + k) for k in range(1, 9)]
    listed = {RESERVE_CUP: frozenset({RESERVE_CUP, LEAGUE})}
    assert second_squad_matches(events, RESERVE_CUP, T0, listed=listed) == (
        frozenset(), False)


def test_empty_list_and_no_clash_changes_nothing() -> None:
    events = league() + [ev(601, T0 - 2 * WEEK + 72 * H, CUP, 401)]
    assert second_squad_matches(events, LEAGUE, T0, listed={}) == (frozenset(), False)
    assert second_squad_matches(events, None, T0, listed={}) == (frozenset(), False)
    assert reserve_event_ids([], {}) == frozenset()


def test_the_fixture_itself_can_be_the_second_squads() -> None:
    # Athletico (Serie A) - Independente in Copa Parana, 2026-10-02.
    events = league() + [
        ev(501, T0 - 1 * WEEK + 25 * H, RESERVE_CUP, 301),
        ev(502, T0 - 3 * WEEK + 30 * H, RESERVE_CUP, 302),
    ]
    assert second_squad_matches(events, RESERVE_CUP, T0, listed={})[1]
    listed = {RESERVE_CUP: frozenset({LEAGUE})}
    assert second_squad_matches(league(), RESERVE_CUP, T0, listed=listed)[1]
    assert not second_squad_matches(league(), RESERVE_CUP, T0, listed={})[1]


def test_probe_does_not_count_as_a_match() -> None:
    matches = [TeamMatch(100 + k, T0 - k * WEEK, LEAGUE) for k in range(1, 5)]
    assert -1 not in reserve_event_ids(matches, {}, probe=(T0, LEAGUE))


# --- SAMPLES --------------------------------------------------------------


class _Cache:
    def __init__(self, listing: dict[str, Any]) -> None:
        self.listing = listing

    def get_entity_events(self, *a: Any) -> dict[str, Any] | None:
        return self.listing if a[2] == 0 else None

    def save_entity_events(self, *_: Any) -> None:
        raise AssertionError("no write expected")

    def get_listed_events(self, *_: object) -> list[dict[str, Any]]:
        return []


class _Client:
    def entity_events(self, *_: Any) -> None:
        return None


def _fixture(competition_id: int) -> Fixture:
    return Fixture(
        sofascore_event_id=1, superbet_event_ids=["1"], sport="football",
        kickoff_utc=datetime.fromtimestamp(T0, UTC),
        home_name="Me", away_name="X", home_entity_id=ME, away_entity_id=8,
        competition_name="C", competition_id=competition_id, season_id=1,
        category_name="X", identity="CONFIRMED", round_number=None,
        round_name=None, cup_round_type=None, previous_leg_event_id=None,
        venue_name=None, referee=None, ground_type=None,
        default_period_count=None,
    )


def _sample(
    events: list[dict[str, Any]], competition_id: int
) -> tuple[list[dict[str, Any]], list[GapEntry]]:
    from bet.sofa.config import SofaConfig

    gaps: list[GapEntry] = []
    got = get_historical_events(
        _Client(), _Cache({"events": events}), ME, "football",  # type: ignore[arg-type]
        _fixture(competition_id), SofaConfig.from_env(), gaps,
    )
    return got, gaps


def test_sample_drops_the_second_squads_matches_and_says_so(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(samples, "RESERVE_COMPETITIONS", {})
    # 25 h passes one_squad_per_entity's 24 h guard - which is how
    # Londrina's sample took its Copa Parana matches.
    cup = [
        ev(501, T0 - 1 * WEEK + 25 * H, RESERVE_CUP, 301),
        ev(502, T0 - 3 * WEEK + 30 * H, RESERVE_CUP, 302),
        ev(503, T0 - 5 * WEEK + 96 * H, RESERVE_CUP, 303),
    ]
    got, gaps = _sample(league() + cup, LEAGUE)
    assert ids(got).isdisjoint({501, 502, 503})
    assert ids(got) <= {100 + k for k in range(1, 13)}
    assert [g.reason for g in gaps] == [GapReason.RESERVE_SQUAD]
    assert f"competition {RESERVE_CUP}: 3" in gaps[0].detail


def test_sample_keeps_a_genuine_cup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(samples, "RESERVE_COMPETITIONS", {})
    cup = [ev(601, T0 - 1 * WEEK + 72 * H, CUP, 401)]
    got, gaps = _sample(league(4) + cup, LEAGUE)
    assert 601 in ids(got)
    assert gaps == []


def test_sample_listed_competition_decides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        samples, "RESERVE_COMPETITIONS", {RESERVE_CUP: frozenset({LEAGUE})})
    cup = [ev(901, T0 - 1 * WEEK + 96 * H, RESERVE_CUP, 501)]
    got, gaps = _sample(league(4) + cup, LEAGUE)
    assert 901 not in ids(got)
    assert [g.reason for g in gaps] == [GapReason.RESERVE_SQUAD]


def test_sample_of_a_second_squad_fixture_is_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        samples, "RESERVE_COMPETITIONS", {RESERVE_CUP: frozenset({LEAGUE})})
    cup = [ev(901, T0 - 1 * WEEK + 96 * H, RESERVE_CUP, 501)]
    got, gaps = _sample(league(4) + cup, RESERVE_CUP)
    assert got == []
    assert [g.reason for g in gaps] == [GapReason.RESERVE_SQUAD]
    assert "side left empty" in gaps[0].detail


def test_sample_with_empty_list_and_no_clash_is_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(samples, "RESERVE_COMPETITIONS", {})
    events = league(4) + [ev(601, T0 - 1 * WEEK + 72 * H, CUP, 401)]
    got, gaps = _sample(events, LEAGUE)
    assert ids(got) == ids(events) and gaps == []


# --- the rating -----------------------------------------------------------


def _r(
    eid: int, ts: int, comp: int, home: int, away: int, gh: float, ga: float
) -> FootballResult:
    return FootballResult(eid, ts, comp, home, away, {"goals_for": (gh, ga)})


def _history(reserve_goals: float) -> list[FootballResult]:
    # Teams 1..6 play a league (comp 10) round robin, weekly; team 1 also
    # plays a cup (comp 20) a day after two league rounds against team 9.
    out: list[FootballResult] = []
    eid = 0
    pairs = [(a, b) for a in range(1, 7) for b in range(1, 7) if a != b]
    for k, (a, b) in enumerate(pairs * 2):
        eid += 1
        out.append(_r(eid, k * WEEK // 3, 10, a, b, 1.0, 1.0))
    t_league = [r.ts for r in out if 1 in (r.home_id, r.away_id)]
    for ts in t_league[-3:]:
        eid += 1
        out.append(_r(eid, ts + 26 * H, 20, 1, 9, reserve_goals, 0.0))
    return sorted(out, key=lambda r: (r.ts, r.event_id))


def test_history_marks_the_second_squad_side_only() -> None:
    marked = mark_second_squads(_history(0.0), {})
    cup = [r for r in marked if r.competition_id == 20]
    assert cup and all(r.home_reserve and not r.away_reserve for r in cup)
    assert not any(r.home_reserve or r.away_reserve
                   for r in marked if r.competition_id == 10)


def test_a_second_squad_match_moves_no_rating() -> None:
    def book(history: list[FootballResult]) -> RatingBook:
        b = RatingBook()
        for r in history:
            b.update(r)
        return b

    a = book(mark_second_squads(_history(0.0), {}))
    b = book(mark_second_squads(_history(9.0), {}))
    ta, tb = a.teams[(1, "goals_for")], b.teams[(1, "goals_for")]
    assert (ta.attack, ta.defence, ta.n) == (tb.attack, tb.defence, tb.n)
    assert a.team_matches(9, "goals_for") == 0
    # The cup's own league rate still counts the match, as played.
    assert a.leagues[(20, "goals_for")].n == 3
    # The cup is not the senior side's domain evidence.
    assert all(c == 10 for _, c in a.team_comps[1])
    # Unmarked, the same scores do move team 1.
    c = book(_history(9.0))
    assert c.teams[(1, "goals_for")].attack != ta.attack


def test_empty_list_and_no_clash_leaves_the_history_unchanged() -> None:
    history = [r for r in _history(0.0) if r.competition_id == 10]
    assert mark_second_squads(history, {}) is history


# --- the config -----------------------------------------------------------


def test_every_listed_competition_carries_its_evidence() -> None:
    cfg = json.loads((REPO / "config/sofa_reserve_competitions.json").read_text())
    entries = cfg["competitions"]
    assert entries
    for e in entries:
        assert isinstance(e["competition_id"], int)
        assert e["reserve_when_main_in"]
        for main in e["reserve_when_main_in"]:
            assert isinstance(main, int)
        ev_ = e["evidence"]
        # Every listed main competition was measured here, or the entry says
        # it rests on the pooled state-cup evidence.
        assert any(str(m) in ev_ for m in e["reserve_when_main_in"])
        measured = all(str(m) in ev_ for m in e["reserve_when_main_in"])
        assert measured or "pooled" in ev_.get("note", "")
    listed = load_reserve_competitions()
    assert listed[24285] == frozenset({325, 390})


def test_the_rule_and_list_are_in_the_history_cache_key() -> None:
    assert reserve_fingerprint({}) != reserve_fingerprint({1: frozenset({2})})
