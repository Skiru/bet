"""fit_line_evidence: the pooled fit leaves out tennis lines priced by the
point model (audit 2026-11-07, TENNIS_POINT_POOL_SPLIT_FROM_DATE). Offline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from bet.sofa import epochs
from bet.sofa.confidence import Calibration
from scripts.sofa import fit_line_evidence as fle


class _NoCurve:
    def realised(self, *args: Any, **kwargs: Any) -> None:
        return None


def _row(market: str, sport: str = "tennis", eid: int = 1) -> dict[str, Any]:
    return {"sport": sport, "market": market, "sofascore_event_id": eid,
            "subject": "", "line": 1.5, "direction": "OVER",
            "p_central": 0.7, "offered_odds": 1.4, "outcome": "WIN"}


ROWS = [_row("aces_total"), _row("handicap_games_won_set1"),
        _row("games_total"), _row("corners_total", sport="football", eid=2)]


def _day(runs: Path, day: str, sheet: list[dict[str, Any]] | None = None) -> None:
    d = runs / day
    d.mkdir(parents=True)
    (d / "02_fixtures.json").write_text(json.dumps(
        [{"sofascore_event_id": 1}, {"sofascore_event_id": 2}]))
    (d / "07_settled.json").write_text(json.dumps(ROWS))
    if sheet is not None:
        (d / "05_sheet.json").write_text(json.dumps(sheet))


def _markets(runs: Path, days: list[str], exclude: bool) -> list[tuple[str, str]]:
    cal = cast(Calibration, _NoCurve())
    return [(str(r["game"]).split(":")[0], str(r["key"]).split("|")[0])
            for r in fle.sheet_rows(runs, days, cal, exclude_point_priced=exclude)]


def test_the_split_is_gated_by_the_day_fitted_for() -> None:
    assert fle.TENNIS_POINT_POOL_SPLIT_FROM_DATE == "2026-11-08"
    assert not fle.tennis_point_pool_split("2026-11-07")
    assert fle.tennis_point_pool_split("2026-11-08")


def test_point_priced_rows_leave_the_pool_by_day_and_marker(tmp_path: Path) -> None:
    field, rule, _ = epochs.TENNIS_POINT_MODEL_MARKER
    hfield, hrule, _ = epochs.TENNIS_HANDICAP_POINT_MODEL_MARKER
    _day(tmp_path, "2026-11-05")
    # 11-06: the handicap switch at 17:30Z - the day's sheet carries both markers
    _day(tmp_path, "2026-11-06", [{"sport": "tennis", field: rule, hfield: hrule}])
    _day(tmp_path, "2026-11-07")
    days = ["2026-11-05", "2026-11-06", "2026-11-07"]
    old = _markets(tmp_path, days, exclude=False)
    assert len(old) == 12  # without the split every row stays (the old file)
    new = _markets(tmp_path, days, exclude=True)
    assert new == [
        ("2026-11-05", "aces_total"), ("2026-11-05", "handicap_games_won_set1"),
        ("2026-11-05", "games_total"), ("2026-11-05", "corners_total"),
        ("2026-11-06", "games_total"), ("2026-11-06", "corners_total"),
        ("2026-11-07", "games_total"), ("2026-11-07", "corners_total")]


def test_a_mixed_day_without_the_late_marker_keeps_its_rows(tmp_path: Path) -> None:
    field, rule, _ = epochs.TENNIS_POINT_MODEL_MARKER
    _day(tmp_path, "2026-11-06", [{"sport": "tennis", field: rule}])
    assert fle.point_priced_markets(tmp_path / "2026-11-06", "2026-11-06") == \
        epochs.TENNIS_POINT_MODEL_MARKETS
    assert ("2026-11-06", "handicap_games_won_set1") in _markets(
        tmp_path, ["2026-11-06"], exclude=True)
    # no sheet on the mixed day: only what was on from 00:00Z
    assert fle.point_priced_markets(tmp_path / "missing", "2026-11-06") == \
        epochs.TENNIS_POINT_MODEL_MARKETS
    # before the point model nothing is excluded and no sheet is read
    assert fle.point_priced_markets(tmp_path / "missing", "2026-11-05") == frozenset()
