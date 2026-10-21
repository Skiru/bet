"""RESOLVE's searched anchor (2026-10-21): the K8 day anchor for a SEARCHED
football side - resolve.searched_anchor_event, resolve.searched_anchor_agreement,
epochs.FOOTBALL_SEARCHED_ANCHOR_FROM_UTC.

The searched team's only game at Superbet's start was refused because the
opponent's name scored under 82 (Bunyodkor - Sogdiyona Jizzax as FC Bunyodkor -
FC Sogdiana Jizzakh, 74). Measured: scripts/sofa/measure_searched_anchor.py,
docs/sofa/history/RAPORT_RESOLVE_KOTWICA_WYSZUKANA_2026-10-21.md.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from bet.sofa import epochs
from bet.sofa.cache import SofaCache
from bet.sofa.config import SofaConfig
from bet.sofa.db import migrate
from bet.sofa.resolve import (
    SofaResolver,
    parse_fixture,
    searched_anchor_agreement,
    searched_anchor_event,
)

NOW = datetime.now(UTC)
KICKOFF = NOW + timedelta(hours=3)
KO_TS = int(KICKOFF.timestamp())


def _team(id_: int, name: str, gender: str = "M") -> dict[str, Any]:
    return {"id": id_, "name": name, "gender": gender, "sport": {"slug": "football"}}


def _ev(eid: int, home: tuple[int, str], away: tuple[int, str],
        dt_min: int = 0, status: str = "notstarted") -> dict[str, Any]:
    return {
        "id": eid, "startTimestamp": KO_TS + 60 * dt_min,
        "status": {"type": status},
        "tournament": {"name": "Super League"},
        "homeTeam": {"id": home[0], "name": home[1], "gender": "M"},
        "awayTeam": {"id": away[0], "name": away[1], "gender": "M"},
    }


BUNYODKOR = (23481, "FC Bunyodkor")
SOGDIANA = (40001, "FC Sogdiana Jizzakh")
GAME = _ev(15462346, BUNYODKOR, SOGDIANA)


def _anchor(cands: list[tuple[dict[str, Any], list[dict[str, Any]]]],
            side: str, opp: str, a: str, b: str) -> Any:
    return searched_anchor_event(cands, KICKOFF, side, opp, a, b)


def test_the_searched_sides_one_game_with_a_weakly_agreeing_opponent() -> None:
    got = _anchor([(_team(*BUNYODKOR), [GAME])], "Bunyodkor", "Sogdiyona Jizzax",
                  "Bunyodkor", "Sogdiyona Jizzax")
    assert got is not None and got[1]["id"] == 15462346
    assert searched_anchor_agreement(
        GAME, got[0], KICKOFF, "Bunyodkor", "Sogdiyona Jizzax", []) == "NAME"
    # Superbet's side_b must be away (the F25 gate).
    assert _anchor([(_team(*BUNYODKOR), [GAME])], "Bunyodkor", "Sogdiyona Jizzax",
                   "Sogdiyona Jizzax", "Bunyodkor") is None
    # postponed, or outside the hour
    assert _anchor([(_team(*BUNYODKOR), [_ev(1, BUNYODKOR, SOGDIANA, 0, "postponed")])],
                   "Bunyodkor", "Sogdiyona Jizzax", "Bunyodkor",
                   "Sogdiyona Jizzax") is None
    assert _anchor([(_team(*BUNYODKOR), [_ev(1, BUNYODKOR, SOGDIANA, 61)])],
                   "Bunyodkor", "Sogdiyona Jizzax", "Bunyodkor",
                   "Sogdiyona Jizzax") is None


def test_a_candidate_must_be_named_as_the_side() -> None:
    # Backtest 10-13: "Worcester City" (82.8) stood for Gloucester City.
    worcester = (9, "Worcester City")
    assert _anchor([(_team(*worcester), [_ev(2, worcester, (8, "Stourbridge"))])],
                   "Gloucester City", "Taunton Town", "Gloucester City",
                   "Taunton Town") is None
    # Backtest 10-11: the senior FC St. Pauli is no candidate for St. Pauli II.
    senior = (10, "FC St. Pauli")
    assert _anchor([(_team(*senior), [_ev(3, senior, (11, "Karlsruher SC"))])],
                   "St. Pauli II", "Hannoverscher SC", "St. Pauli II",
                   "Hannoverscher SC") is None
    # An unmarked squad word: "Inter Turku" is not "Inter Turku 2".
    inter = (12, "Inter Turku")
    assert _anchor([(_team(*inter), [_ev(4, inter, (13, "KuPS Akatemia"))])],
                   "Inter Turku 2", "KuPS Akatemia", "Inter Turku 2",
                   "KuPS Akatemia") is None


def test_two_games_of_two_candidates_refuse() -> None:
    a, b = (1, "Setubal"), (2, "FC Setubal")
    cands = [(_team(*a), [_ev(5, a, (3, "UD Serra"))]),
             (_team(*b), [_ev(6, b, (4, "Lusitano"), 30)])]
    assert _anchor(cands, "Setubal", "UD Serra", "Setubal", "UD Serra") is None


def test_sutton_and_kelantan_are_refused() -> None:
    # 10-13: WBA U21's game is Sutton United - WBA U21; Superbet's Sutton
    # Coldfield Town is its own Sofascore team (139), not in the game.
    wba, sutton_utd = (43510, "West Bromwich Albion U21"), (1001, "Sutton United")
    game = _ev(16802185, sutton_utd, wba)
    got = _anchor([(_team(*wba), [game])], "West Bromwich Albion U21",
                  "Sutton Coldfield Town", "Sutton Coldfield Town",
                  "West Bromwich Albion U21")
    assert got is not None
    args = (game, got[0], KICKOFF, "West Bromwich Albion U21",
            "Sutton Coldfield Town")
    assert searched_anchor_agreement(
        *args, [_team(139, "Sutton Coldfield Town")]) is None
    # Only the veto holds it: "sutton" is a shared word at the same minute.
    assert searched_anchor_agreement(*args, []) == "SHARED_WORD"
    # 10-16: Kelantan Red Warrior played Star City FC, not Imigresen FC.
    krw = (1110076, "Kelantan Red Warrior FC")
    game = _ev(16916841, krw, (2002, "Star City FC"))
    got = _anchor([(_team(*krw), [game])], "Kelantan Red Warrior FC",
                  "Imigresen FC", "Kelantan Red Warrior FC", "Imigresen FC")
    assert got is not None
    for opp_cands in ([], [_team(481757, "Imigresen FC")]):
        assert searched_anchor_agreement(
            game, got[0], KICKOFF, "Kelantan Red Warrior FC", "Imigresen FC",
            opp_cands) is None


def test_mutual_and_the_veto_before_it() -> None:
    cand = _team(*BUNYODKOR)
    args = (GAME, cand, KICKOFF, "Bunyodkor", "Jizzax")
    assert searched_anchor_agreement(*args, [_team(*SOGDIANA)]) == "MUTUAL"
    # A verified entity of the opponent elsewhere refuses even a mutual hit.
    assert searched_anchor_agreement(
        *args, [_team(*SOGDIANA), {"id": 5, "name": "x", "verified": True}]) is None


class _Client:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def search(self, q: str) -> dict[str, Any]:
        self.queries.append(q)
        if "bunyodkor" in q.lower():
            return {"results": [{"type": "team", "entity": _team(*BUNYODKOR)}]}
        if "kelantan" in q.lower():
            return {"results": [{"type": "team",
                                 "entity": _team(1110076, "Kelantan Red Warrior FC")}]}
        if "imigresen" in q.lower():
            return {"results": [{"type": "team",
                                 "entity": _team(481757, "Imigresen FC")}]}
        return {"results": []}

    def entity_events(self, entity_id: int, kind: str, page: int) -> dict[str, Any]:
        if page == 0 and kind == "next" and entity_id == BUNYODKOR[0]:
            return {"events": [GAME], "hasNextPage": False}
        if page == 0 and kind == "next" and entity_id == 1110076:
            return {"events": [_ev(16916841, (1110076, "Kelantan Red Warrior FC"),
                                   (2002, "Star City FC"))], "hasNextPage": False}
        return {"events": [], "hasNextPage": False}

    def event(self, event_id: int) -> dict[str, Any] | None:
        return None


def _resolver(tmp_path: Any, name: str) -> SofaResolver:
    config = SofaConfig(db_path=str(tmp_path / f"{name}.db"))
    migrate(config.db_path)
    return SofaResolver(config, _Client(), SofaCache(config))  # type: ignore[arg-type]


def test_resolve_entity_switch_on_and_off(tmp_path: Any,
                                          monkeypatch: pytest.MonkeyPatch) -> None:
    def run(r: SofaResolver, side: str, opp: str) -> tuple[Any, Any, bool]:
        return r.resolve_entity("football", side, KICKOFF, opp,
                                board_side_a=side, board_side_b=opp)

    monkeypatch.setattr(epochs, "FOOTBALL_SEARCHED_ANCHOR_FROM_UTC", None)
    assert run(_resolver(tmp_path, "off"), "Bunyodkor", "Sogdiyona Jizzax") == (
        None, None, False)

    monkeypatch.setattr(epochs, "FOOTBALL_SEARCHED_ANCHOR_FROM_UTC",
                        NOW - timedelta(hours=1))
    r = _resolver(tmp_path, "on")
    entity_id, event, ambiguous = run(r, "Bunyodkor", "Sogdiyona Jizzax")
    assert (entity_id, ambiguous) == (BUNYODKOR[0], False)
    assert event["id"] == 15462346
    assert event["_match_rule"] == "SEARCHED_ANCHOR:NAME"
    fixture = parse_fixture(event, "football", ["1"], r.client, identity="FUZZY")
    assert fixture.match_rule == "SEARCHED_ANCHOR:NAME"
    # Nothing learned: the name is not a verified alias.
    cached = r.cache.get_entity("football", "bunyodkor")
    assert not cached or cached["status"] != "verified"
    # Kelantan: Imigresen FC is its own team, not in the game.
    assert run(_resolver(tmp_path, "k"), "Kelantan Red Warrior FC",
               "Imigresen FC") == (None, None, False)
