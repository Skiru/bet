"""Coverage audit 2026-10-23, wiring of P13 (model side) and P11 into
SPORT_CONFIDENCE: sport_confidence.parse_history / TeamGames.build pass
`golden_set` / `halves` to score_model.parse_event, and
run_sport_confidence.DbForecaster turns them on by the built day and the
build clock (epochs.VB_GOLDEN_SET / BB_HALVES_LEAGUES). Off: the old calls."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from bet.sofa import epochs, shadow
from bet.sofa import score_model as sm
from bet.sofa import sport_confidence as scf
from scripts.sofa import run_sport_confidence as rsc

ON = datetime(2026, 10, 24, 0, 0, tzinfo=UTC)
VB = shadow.SPORTS["volleyball"]


def _golden_set_match() -> dict[str, Any]:
    # 12193496-like: the match 3-1 on sets, the tie's golden set under
    # overtime, winnerCode naming the golden set's winner (2).
    return {
        "id": 12193496, "startTimestamp": 1790000000,
        "status": {"type": "finished", "description": "AGS"},
        "winnerCode": 2,
        "tournament": {"id": 1, "uniqueTournament": {"id": 1},
                       "category": {"sport": {"slug": "volleyball"}}},
        "homeTeam": {"id": 10, "name": "Home"},
        "awayTeam": {"id": 20, "name": "Away"},
        "homeScore": {"current": 3, "period1": 25, "period2": 25,
                      "period3": 23, "period4": 25, "overtime": 16},
        "awayScore": {"current": 1, "period1": 20, "period2": 22,
                      "period3": 25, "period4": 21, "overtime": 18},
    }


def test_parse_history_and_team_games_read_a_golden_set_match_only_when_asked(
        ) -> None:
    e = _golden_set_match()
    assert sm.parse_event(e, VB) is None
    assert sm.parse_event(e, VB, golden_set=True) is not None
    events = {int(e["id"]): e}
    assert scf.parse_history(events, VB) == []
    got = scf.parse_history(events, VB, golden_set=True)
    assert [g.rating.event_id for g in got] == [12193496]
    off = scf.TeamGames.build(events.values(), VB)
    on = scf.TeamGames.build(events.values(), VB, golden_set=True)
    assert off.by_team == {}
    assert sorted(on.by_team) == [10, 20]


def _capture(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, dict[str, Any]]]:
    seen: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(sm, "load_events", lambda db, sp: {})
    monkeypatch.setattr(sm, "build_model", lambda *a, **k: SimpleNamespace())

    def parse(events: Any, sp: Any, box: Any = None, **kw: Any) -> list[Any]:
        seen.append(("history", kw))
        return []

    def build(events: Any, sp: Any, **kw: Any) -> None:
        seen.append(("games", kw))

    monkeypatch.setattr(rsc.scf, "parse_history", parse)
    monkeypatch.setattr(rsc.scf.TeamGames, "build", staticmethod(build))
    return seen


def test_volleyball_golden_set_by_the_day_and_the_build_clock(
        monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(epochs, "VB_GOLDEN_SET_FROM_UTC", ON)
    seen = _capture(monkeypatch)
    for date, at in (("2026-10-23", datetime(2026, 10, 23, 9, tzinfo=UTC)),
                     ("2026-10-24", datetime(2026, 10, 23, 22, tzinfo=UTC)),
                     ("2026-10-24", datetime(2026, 10, 24, 9, tzinfo=UTC))):
        rsc.DbForecaster("unused.db", at, date)._shadow_model("volleyball")
    on = {"golden_set": True}
    assert seen == [("history", {}), ("games", {}), ("history", {}), ("games", {}),
                    ("history", on), ("games", on)]


def test_golden_set_never_reaches_hockey_or_basketball(
        monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(epochs, "VB_GOLDEN_SET_FROM_UTC", ON)
    seen = _capture(monkeypatch)
    at = datetime(2026, 10, 24, 9, tzinfo=UTC)
    for sport in ("hockey", "basketball"):
        rsc.DbForecaster("unused.db", at, "2026-10-24")._shadow_model(sport)
    assert all(kw == {} for _, kw in seen) and len(seen) == 4


def test_basketball_halves_only_under_its_switch(
        monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _capture(monkeypatch)
    at = datetime(2026, 10, 24, 9, tzinfo=UTC)
    monkeypatch.setattr(epochs, "BB_HALVES_LEAGUES_FROM_UTC", None)
    rsc.DbForecaster("unused.db", at, "2026-10-24")._shadow_model("basketball")
    monkeypatch.setattr(epochs, "BB_HALVES_LEAGUES_FROM_UTC", ON)
    fc = rsc.DbForecaster("unused.db", at, "2026-10-24")
    fc._shadow_model("basketball")
    fc._shadow_model("volleyball")
    monkeypatch.setattr(epochs, "VB_GOLDEN_SET_FROM_UTC", None)
    halves = {"halves": True}
    assert seen[:2] == [("history", {}), ("games", {})]
    assert seen[2:4] == [("history", halves), ("games", halves)]
    assert all("halves" not in kw for _, kw in seen[4:])
