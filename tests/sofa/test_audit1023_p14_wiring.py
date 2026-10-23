"""P14 wiring: SHEET's load_tennis_rating reads the tennis history with the
set-score winner rule exactly when epochs.TENNIS_RATING_SCORE_WINNER is on for
the day being built and the build clock; off, the one-argument call as before.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from bet.sofa import epochs
from bet.sofa.config import SofaConfig
from scripts.sofa import run_sheet as rs

ON = datetime(2026, 10, 24, 0, 0, 0, tzinfo=UTC)


def _calls(monkeypatch: pytest.MonkeyPatch, day: str,
           clock: datetime) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def history(db: Any, **kw: Any) -> list[Any]:
        calls.append(kw)
        return []

    monkeypatch.setattr(rs, "load_history", history)
    monkeypatch.setattr(rs, "load_coefficients",
                        lambda: ({}, {"features": ["d"]}))
    monkeypatch.setattr(rs, "build_model", lambda *a, **k: object())
    monkeypatch.setattr(epochs.timeutil, "now", lambda: clock)
    fixtures: Any = [SimpleNamespace(sport="tennis")]
    rs.load_tennis_rating(SofaConfig(), fixtures, day, scoped=False)
    return calls


def test_on_for_the_day_and_the_clock_reads_the_rule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(epochs, "TENNIS_RATING_SCORE_WINNER_FROM_UTC", ON)
    assert _calls(monkeypatch, "2026-10-24", ON) == [{"score_winner": True}]


def test_a_day_before_or_a_clock_before_keeps_the_old_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(epochs, "TENNIS_RATING_SCORE_WINNER_FROM_UTC", ON)
    late = datetime(2026, 10, 24, 6, tzinfo=UTC)
    assert _calls(monkeypatch, "2026-10-23", late) == [{}]
    early = datetime(2026, 10, 23, 23, tzinfo=UTC)
    assert _calls(monkeypatch, "2026-10-24", early) == [{}]


def test_switch_none_keeps_the_old_call(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(epochs, "TENNIS_RATING_SCORE_WINNER_FROM_UTC", None)
    assert _calls(monkeypatch, "2026-10-30", ON) == [{}]
