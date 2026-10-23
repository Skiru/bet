"""Coverage audit 2026-10-23, wiring of P7 / P8 into SPORT_CONFIDENCE
(scripts/sofa/run_sport_confidence.py DbForecaster): the CS2 ratings are built
with the lineup rating of unrated pairs (epochs.CS2_LINEUP_ELO_UNRATED) and the
engine reads a player's nickname by prefix (epochs.NAME_RULES_1023), each by
the built day and the build clock. Off: the old calls exactly (no new
argument passed)."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from bet.sofa import epochs
from scripts.sofa import run_sport_confidence as rsc

ON = datetime(2026, 10, 24, 0, 0, tzinfo=UTC)
DAY_BEFORE_AT = datetime(2026, 10, 23, 9, tzinfo=UTC)
DAY_ON_AT = datetime(2026, 10, 24, 9, tzinfo=UTC)
# a 10-24 day built before the switch's clock (a dry run the evening before)
DAY_ON_EARLY = datetime(2026, 10, 23, 22, tzinfo=UTC)


def _ratings_calls(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Any, ...]]:
    seen: list[tuple[Any, ...]] = []
    monkeypatch.setattr(epochs, "CS2_LINEUP_ELO_UNRATED_FROM_UTC", ON)
    monkeypatch.setattr(rsc.scf, "load_cs2", lambda db, ts: ([], {}))

    def fake(*a: Any, **kw: Any) -> Any:
        seen.append(a[1:] + tuple(sorted(kw.items())))
        return SimpleNamespace()

    monkeypatch.setattr(rsc.cs2_engine, "build_ratings", fake)
    return seen


def test_lineup_unrated_ratings_by_the_day_and_the_build_clock(
        monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _ratings_calls(monkeypatch)
    for date, at in (("2026-10-23", DAY_BEFORE_AT), ("2026-10-24", DAY_ON_EARLY),
                     ("2026-10-24", DAY_ON_AT)):
        rsc.DbForecaster("unused.db", at, date)._cs2_model()
    terms = (rsc.cs2_engine.MAP_TERMS
             if epochs.cs2_map_identity("2026-10-24", DAY_ON_AT) else ())
    # off: build_ratings(maps, terms) - the old call; on: lineup_unrated True
    assert seen == [(terms,), (terms,), (terms, True)]


def test_lineup_unrated_switch_none_is_the_old_call(
        monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _ratings_calls(monkeypatch)
    monkeypatch.setattr(epochs, "CS2_LINEUP_ELO_UNRATED_FROM_UTC", None)
    rsc.DbForecaster("unused.db", DAY_ON_AT, "2026-10-24")._cs2_model()
    assert seen == [(rsc.cs2_engine.MAP_TERMS
                     if epochs.cs2_map_identity("2026-10-24", DAY_ON_AT) else (),)]


def test_name_rules_reach_the_engine_by_the_day_and_the_build_clock(
        monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(epochs, "NAME_RULES_1023_FROM_UTC", ON)
    seen: list[Any] = []

    def fake(*a: Any, **kw: Any) -> Any:
        seen.append(kw.get("name_rules", "absent"))
        return SimpleNamespace(p=0.6)

    monkeypatch.setattr(rsc.cs2_engine, "model_probability", fake)
    fixture = {"home_id": 1, "away_id": 2, "home_is_team1": True, "best_of": 3}
    ev = SimpleNamespace(team1="a", team2="b")
    for date, at in (("2026-10-23", DAY_BEFORE_AT), ("2026-10-24", DAY_ON_EARLY),
                     ("2026-10-24", DAY_ON_AT)):
        fc = rsc.DbForecaster("unused.db", at, date)
        fc._cs2 = ([], {}, None)  # type: ignore[assignment]
        assert fc.probability("cs2", fixture, ev, SimpleNamespace()) == 0.6
    # off: the argument is not passed at all (the old call)
    assert seen == ["absent", "absent", True]
    monkeypatch.setattr(epochs, "NAME_RULES_1023_FROM_UTC", None)
    fc = rsc.DbForecaster("unused.db", DAY_ON_AT, "2026-10-24")
    fc._cs2 = ([], {}, None)  # type: ignore[assignment]
    fc.probability("cs2", fixture, ev, SimpleNamespace())
    assert seen[-1] == "absent"


def test_a_forecaster_without_a_day_reads_the_build_clocks_day() -> None:
    # str(None) = "None" compares above every date; the day falls back to
    # the build clock's.
    assert rsc.DbForecaster("unused.db", DAY_BEFORE_AT)._day == "2026-10-23"
    assert rsc.DbForecaster("unused.db", DAY_ON_AT, "2026-10-23")._day == "2026-10-23"
