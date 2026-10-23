"""Coverage audit 2026-10-23 P4 (B3; epochs.SPORT_QUERY_ANCHOR_FROM_UTC):
a volleyball event no side of which has a resolved id is the query-only
team's ONE game at Superbet's start, named as the searched side, with the
opponent agreeing weakly and not vetoed by its own query (QUERY_ANCHOR,
sport_identity.match_query_anchor). Off: match_shadow's refusal stands.

10-23 OK Maribor - ACH Lublana (18:30Z): the cached page of OK i-Vent
Maribor (276327) held 17267345 "OK i-Vent Maribor - ACH Volley Ljubljana" at
the exact hour; names 100 / 71 ("Lublana" is the Polish name) - refused
NO_MATCH_IN_LISTING."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from bet.sofa import entity_map, epochs
from bet.sofa import sport_identity as si
from tests.sofa.test_sport_identity import KICK, FakeClient, _ev, _listed

AT = KICK - timedelta(hours=6)
ON = datetime(2026, 10, 6, 0, 0, tzinfo=UTC)
MARIBOR, LJUBLJANA, KRANJ = 276327, 25986, 267659


def _game(eid: int, home: tuple[int, str], away: tuple[int, str],
          start: datetime = KICK) -> dict[str, Any]:
    return _listed(eid, home, away, start, slug="volleyball")


THE_GAME = _game(17267345, (MARIBOR, "OK i-Vent Maribor"),
                 (LJUBLJANA, "ACH Volley Ljubljana"))
LATER = _game(17267351, (KRANJ, "Triglav Kranj"), (MARIBOR, "OK i-Vent Maribor"),
              KICK + timedelta(days=8))


def _run(listing: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch,
         switch: datetime | None = ON, t1: str = "OK Maribor",
         t2: str = "ACH Lublana", sport: str = "volleyball",
         query: dict[str, int] | None = None,
         opponents: dict[str, frozenset[int]] | None = None) -> dict[str, Any]:
    monkeypatch.setattr(epochs, "SPORT_QUERY_ANCHOR_FROM_UTC", switch)
    q = {"OK Maribor": MARIBOR} if query is None else query
    opp = opponents or {}
    (r,), _ = si.identify([_ev("1", t1, t2, sport=sport)],
                          FakeClient({MARIBOR: listing}), None,
                          lambda s, n: None, AT, "2026-10-06",
                          query_teams=lambda s, n: q.get(n),
                          anchor_opponents=lambda s, n: opp.get(n, frozenset()))
    return r


def test_off_maribor_lublana_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    r = _run([THE_GAME, LATER], monkeypatch, switch=None)
    assert r["status"] == si.NOT_IDENTIFIED
    assert r["reason"] == "NO_MATCH_IN_LISTING" and r["query_only"] is True


def test_on_maribor_lublana_is_identified(monkeypatch: pytest.MonkeyPatch) -> None:
    r = _run([THE_GAME, LATER], monkeypatch)
    assert r["status"] == si.IDENTIFIED and r["sofascore_event_id"] == 17267345
    assert r["match_method"] == si.QUERY_ANCHOR
    assert r["query_anchor_rule"] == "NAME" and r["home_is_team1"] is True
    assert r["name_scores"] == {"team1": 100.0, "team2": 71.0}


def test_on_two_games_at_the_hour_refuse(monkeypatch: pytest.MonkeyPatch) -> None:
    twin = _game(17267399, (MARIBOR, "OK i-Vent Maribor"), (43052, "Calcit Kamnik"))
    r = _run([THE_GAME, twin], monkeypatch)
    assert r["status"] == si.NOT_IDENTIFIED
    assert r["query_anchor_reason"] == "AMBIGUOUS"


def test_on_the_opponents_own_query_naming_another_team_vetoes(
        monkeypatch: pytest.MonkeyPatch) -> None:
    r = _run([THE_GAME], monkeypatch,
             opponents={"ACH Lublana": frozenset({999})})
    assert r["status"] == si.NOT_IDENTIFIED
    assert r["query_anchor_reason"] == "QUERY_ANCHOR_VETO"
    mutual = _run([THE_GAME], monkeypatch,
                  opponents={"ACH Lublana": frozenset({LJUBLJANA})})
    assert mutual["status"] == si.IDENTIFIED
    assert mutual["query_anchor_rule"] == "MUTUAL"


def test_on_a_weak_opponent_with_no_shared_word_refuses(
        monkeypatch: pytest.MonkeyPatch) -> None:
    other = _game(1, (MARIBOR, "OK i-Vent Maribor"), (77, "Calcit Kamnik"))
    r = _run([other], monkeypatch)
    assert r["status"] == si.NOT_IDENTIFIED
    assert r["query_anchor_reason"] == "QUERY_ANCHOR_OPPONENT"


def test_on_the_start_must_be_exact(monkeypatch: pytest.MonkeyPatch) -> None:
    moved = _game(17267345, (MARIBOR, "OK i-Vent Maribor"),
                  (LJUBLJANA, "ACH Volley Ljubljana"), KICK + timedelta(minutes=30))
    r = _run([moved], monkeypatch)
    assert r["status"] == si.NOT_IDENTIFIED
    assert r["query_anchor_reason"] == "QUERY_ANCHOR_NO_GAME"


def test_on_the_searched_sides_own_name_must_score_90(
        monkeypatch: pytest.MonkeyPatch) -> None:
    # The query id reached a team whose game-side name reads weakly.
    weak = _game(5, (MARIBOR, "Branik Volley"), (LJUBLJANA, "ACH Volley Ljubljana"))
    r = _run([weak], monkeypatch)
    assert r["status"] == si.NOT_IDENTIFIED
    assert r["query_anchor_reason"] == "QUERY_ANCHOR_OWN_NAME"


def test_on_team2_as_the_query_reads_the_order(
        monkeypatch: pytest.MonkeyPatch) -> None:
    r = _run([THE_GAME], monkeypatch, t1="ACH Lublana", t2="OK Maribor")
    assert r["status"] == si.IDENTIFIED and r["home_is_team1"] is False
    assert r["name_scores"] == {"team1": 71.0, "team2": 100.0}


def test_on_hockey_is_not_a_query_anchor_sport(
        monkeypatch: pytest.MonkeyPatch) -> None:
    game = _listed(3, (MARIBOR, "OK i-Vent Maribor"),
                   (LJUBLJANA, "ACH Volley Ljubljana"))
    r = _run([game], monkeypatch, sport="hockey")
    assert "hockey" not in si.QUERY_ANCHOR_SPORTS
    assert r["status"] == si.NOT_IDENTIFIED and "query_anchor_reason" not in r


def test_an_anchor_match_is_never_a_verified_name() -> None:
    rec = {"sport": "volleyball", "status": si.IDENTIFIED,
           "sofascore_event_id": 17267345, "home_id": MARIBOR,
           "away_id": LJUBLJANA, "home_is_team1": True,
           "team1": "OK Maribor", "team2": "ACH Lublana",
           "sofascore_home": "OK i-Vent Maribor",
           "sofascore_away": "ACH Volley Ljubljana",
           "name_scores": {"team1": 100.0, "team2": 71.0},
           "match_method": si.QUERY_ANCHOR, "team1_id": None, "team2_id": None}
    sides = entity_map.record_sides(rec)
    assert len(sides) == 2
    assert not any(entity_map.name_confirmed(s) for s in sides)
    assert not any(s.method in entity_map.OPPONENT_METHODS for s in sides)


def test_query_ids_is_query_id_unfolded() -> None:
    class R(si.TeamResolver):
        def _index(self, slug: str) -> dict[str, set[int]]:
            return {"ok i-vent maribor": {MARIBOR}, "ok maribor": {MARIBOR},
                    "calcit kamnik": {5}}

    r = R(None, 0)  # type: ignore[arg-type]
    assert r.query_ids("volleyball", "OK Maribor") == frozenset({MARIBOR})
    assert r.query_id("volleyball", "OK Maribor") == MARIBOR
    assert r.query_ids("volleyball", "Calcit Kamnik") == frozenset({5})
    assert r.query_ids("cs2", "OK Maribor") == frozenset()


def test_the_switch_reads_the_day_and_the_build_clock(
        monkeypatch: pytest.MonkeyPatch) -> None:
    at = datetime(2026, 10, 24, 0, 0, tzinfo=UTC)
    monkeypatch.setattr(epochs, "SPORT_QUERY_ANCHOR_FROM_UTC", at)
    assert not epochs.sport_query_anchor("2026-10-23", at)
    assert not epochs.sport_query_anchor("2026-10-24", at - timedelta(seconds=1))
    assert epochs.sport_query_anchor("2026-10-24", at)
