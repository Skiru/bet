"""Coverage audit 2026-10-23, wiring of P8 (CS2 names) into SPORT_IDENTITY:
sport_identity.identify reads epochs.NAME_RULES_1023 by the day and the build
clock and match_cs2 / match_cs2_anchored / _cs2_same_roster pass it to
cs2.pick_event / esports_score / _roster - Privateer - Inner Circle Prospects
(Superbet) is Sofascore's "Inner Circle Prospect" only under the rule. Also
the P4 veto passed explicitly by run_sport_identity (resolver.query_ids)."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import epochs
from bet.sofa import sport_identity as si
from tests.sofa.test_sport_identity import FakeClient, _listed

KICK = datetime(2026, 10, 24, 15, 0, tzinfo=UTC)
ON = datetime(2026, 10, 24, 0, 0, tzinfo=UTC)
PRIVATEER, ICP = 900001, 900002


def _ev(day: str) -> si.BoardEvent:
    kick = KICK if day == "2026-10-24" else KICK - timedelta(days=1)
    return si.BoardEvent("cs2", "77", "Privateer·Inner Circle Prospects",
                         "Privateer", "Inner Circle Prospects",
                         kick.isoformat().replace("+00:00", "Z"), "CCT", day)


def _series(kick: datetime) -> dict[str, Any]:
    e = _listed(7, (PRIVATEER, "Privateer"), (ICP, "Inner Circle Prospect"),
                kick, slug="esports", category="Counter Strike")
    e["status"] = {"type": "notstarted"}
    return e


def _identify(day: str, at: datetime, ids: dict[str, int],
              monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    monkeypatch.setattr(epochs, "NAME_RULES_1023_FROM_UTC", ON)
    # P2 / P4 out of the way: only the name rule differs between the runs
    monkeypatch.setattr(epochs, "IDENTITY_FRESH_RECHECK_ALL_FROM_UTC", None)
    monkeypatch.setattr(epochs, "SPORT_QUERY_ANCHOR_FROM_UTC", None)
    ev = _ev(day)
    client = FakeClient({PRIVATEER: [_series(ev.kickoff)]})
    (r,), _ = si.identify([ev], client, None, lambda s, n: ids.get(n), at, day)
    return r


def test_the_prospect_series_is_pinned_only_under_the_rule(
        monkeypatch: pytest.MonkeyPatch) -> None:
    ids = {"Privateer": PRIVATEER}  # ICP has no resolved id (10-22)
    off = _identify("2026-10-23", KICK - timedelta(days=1, hours=2), ids,
                    monkeypatch)
    early = _identify("2026-10-24", datetime(2026, 10, 23, 22, tzinfo=UTC), ids,
                      monkeypatch)
    on = _identify("2026-10-24", KICK - timedelta(hours=2), ids, monkeypatch)
    assert off["status"] == si.NOT_IDENTIFIED
    assert early["status"] == si.NOT_IDENTIFIED  # the day on, the clock not yet
    assert on["status"] == si.IDENTIFIED and on["sofascore_event_id"] == 7
    assert on["home_is_team1"] is True
    assert on["match_method"] == "CS2_PICK_EVENT"


def test_match_cs2_and_the_anchored_path_pass_the_rule() -> None:
    ev = _ev("2026-10-24")
    rows = [_series(KICK)]
    assert si.match_cs2(ev, rows, PRIVATEER, None)["status"] == si.NOT_IDENTIFIED
    hit = si.match_cs2(ev, rows, PRIVATEER, None, True)
    assert hit["status"] == si.IDENTIFIED and hit["name_scores"]["team2"] > 0
    # the anchored rule's roster gate: "prospects" vs "prospect"
    assert not si._cs2_same_roster("inner circle prospects", "inner circle prospect")
    assert si._cs2_same_roster("inner circle prospects", "inner circle prospect",
                               True)
    assert not si._cs2_same_roster("inner circle", "inner circle prospect", True)


def test_run_sport_identity_passes_the_query_anchor_veto(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from scripts.sofa import run_sport_identity as rsi

    seen: dict[str, Any] = {}

    class Resolver:
        def __init__(self, *a: Any, **k: Any) -> None:
            pass

        def team_id(self, sport: str, name: str) -> int | None:
            return None

        def query_id(self, sport: str, name: str) -> int | None:
            return None

        def query_ids(self, sport: str, name: str) -> frozenset[int]:
            return frozenset()

    def identify(events: Any, client: Any, cache: Any, teams: Any, at: Any,
                 date: str, pinned: Any = None, query_teams: Any = None,
                 **kw: Any) -> tuple[list[Any], dict[str, Any]]:
        seen.update(kw)
        seen["query_teams"] = query_teams
        return [], {"aborted": None, "sports": {}}

    monkeypatch.setattr(rsi.si, "board_events",
                        lambda runs, sport, date, at: [_ev("2026-10-24")])
    monkeypatch.setattr(rsi.si, "TeamResolver", Resolver)
    monkeypatch.setattr(rsi.si, "identify", identify)
    monkeypatch.setattr(rsi.entity_map, "learned_reads", lambda d, at: None)
    rsi.run("2026-10-24", ["cs2"], str(tmp_path), FakeClient({}), None,
            sqlite3.connect(":memory:"))
    veto = seen["anchor_opponents"]
    assert veto.__func__ is Resolver.query_ids
    assert seen["query_teams"].__self__ is veto.__self__
