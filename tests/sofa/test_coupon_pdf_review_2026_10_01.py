"""Review 2026-10-01 of SHEET -> COUPON -> CONFIDENCE -> PDF: atomic writes,
one ladder bought twice is marked, no product-of-legs price on the page, a
leg that has started by render time is marked."""

from __future__ import annotations

import datetime
import importlib.util
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import atomic
from bet.sofa.confidence import DEFAULT_CALIBRATION, ladder_key, ladder_leg_counts

SCRIPT = Path(__file__).parents[2] / "scripts" / "sofa" / "build_coupon_pdf.py"


def _pdf_module() -> Any:
    spec = importlib.util.spec_from_file_location("build_coupon_pdf", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_atomic_write_keeps_the_old_file_when_the_write_dies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "08_confidence.json"
    target.write_text("old", encoding="utf-8")

    def boom(src: object, dst: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(atomic.os, "replace", boom)
    with pytest.raises(OSError):
        atomic.write_atomic(target, "new")
    assert target.read_text(encoding="utf-8") == "old"


def test_atomic_write_replaces_and_leaves_no_tmp(tmp_path: Path) -> None:
    target = tmp_path / "a" / "x.json"
    atomic.write_atomic(target, "{}")
    assert target.read_text(encoding="utf-8") == "{}"
    assert not atomic.tmp_path(target).exists()


def test_rungs_of_one_ladder_are_counted_together() -> None:
    # 2026-09-30, event 16494359: 12.5 UNDER, 11.5 UNDER, 7.5 OVER corners.
    legs = [
        {"sofascore_event_id": 16494359, "market": "corners_total", "subject": None,
         "line": 12.5, "direction": "UNDER"},
        {"sofascore_event_id": 16494359, "market": "corners_total", "subject": None,
         "line": 11.5, "direction": "UNDER"},
        {"sofascore_event_id": 16494359, "market": "corners_total", "subject": None,
         "line": 7.5, "direction": "OVER"},
        {"sofascore_event_id": 16494359, "market": "cards_total", "subject": None,
         "line": 3.5, "direction": "OVER"},
        {"sofascore_event_id": 1, "market": "games_won_for", "subject": "A",
         "line": 10.5, "direction": "OVER"},
        {"sofascore_event_id": 1, "market": "games_won_for", "subject": "B",
         "line": 10.5, "direction": "OVER"},
    ]
    counts = ladder_leg_counts(legs)
    assert counts[ladder_key(legs[0])] == 3
    assert counts[ladder_key(legs[3])] == 1
    # Two players' games won are two ladders, not one.
    assert counts[ladder_key(legs[4])] == 1


def test_the_page_prints_no_product_of_leg_prices() -> None:
    src = SCRIPT.read_text(encoding="utf-8")
    assert "odds_if_product']}" not in src
    assert "iloczyn {b" not in src


def test_a_leg_inside_the_kickoff_margin_at_render_is_marked() -> None:
    pdf = _pdf_module()
    now = datetime.datetime(2026, 10, 1, 12, 0, tzinfo=datetime.UTC)
    assert pdf.started_at_render({"kickoff_utc": "2026-10-01T12:10:00Z"}, now)
    assert pdf.started_at_render({"kickoff_utc": "2026-10-01T11:00:00+00:00"}, now)
    assert not pdf.started_at_render({"kickoff_utc": "2026-10-01T12:30:00Z"}, now)
    assert pdf.started_at_render({}, now)


def test_calibration_path_does_not_depend_on_the_working_directory() -> None:
    assert DEFAULT_CALIBRATION.is_absolute()
    assert DEFAULT_CALIBRATION.exists()
