"""RESOLVE's short-name search (2026-10-21, switch left off):
bet.sofa.short_name_search, epochs.FOOTBALL_SHORT_NAME_SEARCH_FROM_UTC.

Sofascore's search finds nothing fitting for "Calcio Avola 1949" or
"Menemenspor" while "avola" / "menemen" find the team; a game is accepted only
when BOTH sides land on it. Measured: scripts/sofa/measure_short_name_search.py,
docs/sofa/history/RAPORT_RESOLVE_KROTKA_NAZWA_2026-10-21.md.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from bet.sofa import epochs
from bet.sofa.cache import SofaCache
from bet.sofa.config import SofaConfig
from bet.sofa.contracts import BoardFixture, GapReason
from bet.sofa.db import migrate
from bet.sofa.names import normalize_name
from bet.sofa.resolve import SofaResolver
from bet.sofa.short_name_search import (
    name_contradicts,
    resolve_short_name_pair,
    short_candidate_fits,
    short_miss_key,
    short_name_pair_event,
    short_name_queries,
    squad_words,
)
from scripts.sofa.run_resolve import _resolve_one

NOW = datetime.now(UTC)
KICKOFF = (NOW + timedelta(hours=3)).replace(microsecond=0)
KO_TS = int(KICKOFF.timestamp())


def _team(id_: int, name: str, gender: str = "M") -> dict[str, Any]:
    return {"id": id_, "name": name, "gender": gender, "sport": {"slug": "football"}}


def _ev(eid: int, home: tuple[int, str], away: tuple[int, str],
        dt_min: int = 0, status: str = "notstarted") -> dict[str, Any]:
    return {
        "id": eid, "startTimestamp": KO_TS + 60 * dt_min,
        "status": {"type": status},
        "tournament": {"name": "Eccellenza"},
        "homeTeam": {"id": home[0], "name": home[1], "gender": "M"},
        "awayTeam": {"id": away[0], "name": away[1], "gender": "M"},
    }


AVOLA = (400379, "Avola")
SAMBIASE = (379983, "A.S.D. Sambiase 2023")
GAME = _ev(16789056, AVOLA, SAMBIASE)
A, B = "Calcio Avola 1949", "AS Sambiase"


def _l(team: tuple[int, str], events: list[dict[str, Any]]) -> Any:
    return (_team(*team), events)


def test_short_queries_are_the_longest_distinctive_words() -> None:
    assert short_name_queries(normalize_name(A)) == ["avola"]
    # The one-word name is the normal query already; its town is new.
    assert short_name_queries(normalize_name("Menemenspor")) == ["menemen"]
    assert short_name_queries(normalize_name("Karsiyakaspor Kulubu")) == [
        "karsiyakaspor", "karsiyaka"]
    assert short_name_queries(normalize_name("Guzide Gebze Spor")) == [
        "guzide", "gebze"]
    # Stopwords, digits and the normal query itself are never asked.
    assert short_name_queries(normalize_name("ASD Polisportiva Modica Calcio")) == [
        "modica"]
    assert short_name_queries(normalize_name("Modica")) == []


def test_a_short_result_must_hold_the_query_and_not_be_the_other_sides_word() -> None:
    a, b = normalize_name(A), normalize_name(B)
    assert short_candidate_fits(a, b, "avola", _team(*AVOLA))
    assert not short_candidate_fits(a, b, "avola", _team(9, "Avolano"))
    assert not short_candidate_fits(a, b, "avola", _team(9, "Avola", gender="F"))
    # "linz" is a word of both board sides: it names neither.
    e, k = normalize_name("Edelweiss Linz"), normalize_name("Blau Weiss Linz")
    assert not short_candidate_fits(e, k, "linz", _team(9, "LASK Linz"))


def test_squad_words_and_name_contradictions() -> None:
    assert squad_words(normalize_name("A.S.D. Sambiase 2023")) == frozenset()
    assert squad_words(normalize_name("Polissya-2 Zhytomyr")) == {"2"}
    assert squad_words(normalize_name("FC Polissya Zhytomyr 2")) == {"2"}
    for board, team in (("Cheltenham Town", "Swindon Town"),
                        ("Real Madryt B (K)", "Atletico Madrid B"),
                        ("Hapoel Petah Tikva U19", "Maccabi Petach Tikva U19"),
                        ("Nomme Kalju U21", "FC Nomme United U21")):
        assert name_contradicts(normalize_name(board), normalize_name(team))
    for board, team in ((A, "Avola"),
                        ("SV Wallern", "SPG Wallern/ASV St Marienkirchen"),
                        ("Menemenspor", "Menemen FK"),
                        ("Probiy Gorodenka", "Probiy Horodenka"),
                        ("LASK Linz (K)", "LASK")):
        assert not name_contradicts(normalize_name(board), normalize_name(team))


def test_both_sides_must_land_on_the_one_game() -> None:
    assert short_name_pair_event([_l(AVOLA, [GAME])], [_l(SAMBIASE, [])],
                                 KICKOFF, A, B)["id"] == GAME["id"]
    # One side alone never: side B holds no candidate that is in the game.
    assert short_name_pair_event([_l(AVOLA, [GAME])], [_l((5, "Sambiase U19"), [])],
                                 KICKOFF, A, B) is None
    # Superbet's order (F25): the board's side_a must be at home.
    rev = _ev(1, SAMBIASE, AVOLA)
    assert short_name_pair_event([_l(AVOLA, [rev])], [_l(SAMBIASE, [rev])],
                                 KICKOFF, A, B) is None
    # Outside 60 minutes, postponed, or two games: refused.
    for evs in ([_ev(2, AVOLA, SAMBIASE, dt_min=61)],
                [_ev(3, AVOLA, SAMBIASE, status="postponed")],
                [GAME, _ev(4, AVOLA, SAMBIASE, dt_min=30)]):
        assert short_name_pair_event([_l(AVOLA, evs)], [_l(SAMBIASE, [])],
                                     KICKOFF, A, B) is None


def test_contradicted_names_and_a_namesake_playing_elsewhere_refuse() -> None:
    town = (11, "Swindon Town")
    barnet = (10, "Barnet")
    game = _ev(5, barnet, town)
    assert short_name_pair_event([_l(barnet, [game])], [_l(town, [game])],
                                 KICKOFF, "Barnet", "Cheltenham Town") is None
    # "Dundee FC" is a candidate of its own name with its own game now.
    utd, dfc, sj = (21, "Dundee United"), (22, "Dundee FC"), (20, "St. Johnstone")
    game = _ev(6, sj, utd)
    other = _ev(7, (23, "Hibernian"), dfc)
    assert short_name_pair_event([_l(sj, [game])], [_l(utd, [game])],
                                 KICKOFF, "St. Johnstone", "Dundee") is not None
    assert short_name_pair_event([_l(sj, [game])],
                                 [_l(utd, [game]), _l(dfc, [other])],
                                 KICKOFF, "St. Johnstone", "Dundee FC") is None


class _Client:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def search(self, q: str) -> dict[str, Any]:
        self.queries.append(q)
        if q == "avola":
            return {"results": [{"type": "team", "entity": _team(*AVOLA)}]}
        if q == "sambiase":
            return {"results": [{"type": "team", "entity": _team(*SAMBIASE)}]}
        return {"results": []}

    def entity_events(self, entity_id: int, kind: str, page: int) -> dict[str, Any]:
        if page == 0 and kind == "next" and entity_id in (AVOLA[0], SAMBIASE[0]):
            return {"events": [GAME], "hasNextPage": False}
        return {"events": [], "hasNextPage": False}

    def event(self, event_id: int) -> dict[str, Any] | None:
        return None


def _resolver(tmp_path: Any, name: str) -> SofaResolver:
    config = SofaConfig(db_path=str(tmp_path / f"{name}.db"))
    migrate(config.db_path)
    return SofaResolver(config, _Client(), SofaCache(config))  # type: ignore[arg-type]


def test_the_pair_step_tags_the_game_and_learns_nothing(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The miss check reads misses recorded since the switch, which is in the
    # past whenever the step runs.
    monkeypatch.setattr(epochs, "FOOTBALL_SHORT_NAME_SEARCH_FROM_UTC",
                        NOW - timedelta(hours=1))
    r = _resolver(tmp_path, "pair")
    event = resolve_short_name_pair(r, A, B, KICKOFF)
    assert event is not None and event["id"] == GAME["id"]
    assert event["_match_rule"] == "SHORT_NAME:BOTH"
    for side in (A, B):
        cached = r.cache.get_entity("football", normalize_name(side))
        assert not cached or cached["status"] != "verified"
    # A pair that found nothing is remembered for its day and not re-asked.
    r2 = _resolver(tmp_path, "miss")
    assert resolve_short_name_pair(r2, "Calcio Nowhere", "AS Elsewhere",
                                   KICKOFF) is None
    key = short_miss_key(normalize_name("Calcio Nowhere"),
                         normalize_name("AS Elsewhere"))
    assert r2.cache.get_entity_miss("football", key)
    asked = len(r2.client.queries)  # type: ignore[attr-defined]
    assert resolve_short_name_pair(r2, "Calcio Nowhere", "AS Elsewhere",
                                   KICKOFF) is None
    assert len(r2.client.queries) == asked  # type: ignore[attr-defined]


def test_resolve_one_switch_off_and_on(tmp_path: Any,
                                       monkeypatch: pytest.MonkeyPatch) -> None:
    bf = BoardFixture(superbet_event_id="15277322", sport="football",
                      match_name=f"{A}·{B}", side_a=A, side_b=B,
                      kickoff_utc=KICKOFF)
    monkeypatch.setattr(epochs, "FOOTBALL_SHORT_NAME_SEARCH_FROM_UTC", None)
    r = _resolver(tmp_path, "off")
    out = _resolve_one(bf, r, r.client, r.cache, "TEST")
    assert out.gap == GapReason.NO_MATCHING_EVENT
    assert not {"avola", "sambiase"} & set(r.client.queries)  # type: ignore[attr-defined]

    monkeypatch.setattr(epochs, "FOOTBALL_SHORT_NAME_SEARCH_FROM_UTC",
                        NOW - timedelta(days=1))
    r = _resolver(tmp_path, "on")
    out = _resolve_one(bf, r, r.client, r.cache, "TEST")
    assert out.fixture is not None
    assert out.fixture.sofascore_event_id == GAME["id"]
    assert out.fixture.match_rule == "SHORT_NAME:BOTH"
    assert out.fixture.identity == "FUZZY"
