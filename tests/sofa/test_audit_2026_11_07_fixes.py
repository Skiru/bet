"""Audit 2026-11-07 of the 11-06 changes: the small correctness fixes."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from bet.sofa import tennis_point_sheet as tps
from scripts.sofa.day_status import NOT_CHECKED, OK, WARN, line_evidence_check


def _evidence(tmp_path: Path, before: str) -> Path:
    path = tmp_path / "sofa_superbet_line_evidence.json"
    path.write_text(json.dumps({"fitted_from": {
        "before": before, "fitted_at_utc": f"{before}T07:40:43+00:00"}}))
    return path


def test_day_status_warns_on_line_evidence_of_an_earlier_day(tmp_path: Path) -> None:
    fresh = line_evidence_check("2026-11-07", _evidence(tmp_path, "2026-11-07"))
    assert fresh.status == OK
    stale = line_evidence_check("2026-11-07", _evidence(tmp_path, "2026-11-06"))
    assert stale.status == WARN and "--before 2026-11-07" in stale.detail
    assert line_evidence_check(
        "2026-11-05", _evidence(tmp_path, "2026-11-07")).status == NOT_CHECKED
    assert line_evidence_check("2026-11-07", tmp_path / "missing.json").status == WARN


def test_tennis_point_model_never_guesses_an_unstated_format() -> None:
    args = (999, datetime(2026, 11, 7, 12, tzinfo=UTC), 1, 2, "ATP",
            "Hardcourt outdoor", 7)
    assert tps.fixture_match(*args, 3, {1: False}) is not None
    assert tps.fixture_match(*args, 5, {1: False}) is None
    assert tps.fixture_match(*args, None, {1: False}) is None
