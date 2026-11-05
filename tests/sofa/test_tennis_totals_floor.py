"""epochs.TENNIS_TOTALS_FLOOR (operator 2026-11-05, from 2026-11-06 00:00Z):
tennis games_total / sets_total pass the floor at 0.60, carry their own
floor on the leg, are audited on it and never join a builder."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from bet.sofa import epochs
from scripts.sofa import audit_variants
from tests.sofa.coupon_fixtures import AT, DATE, official_single, write_official

ON = datetime(2026, 11, 6, 0, 0, tzinfo=UTC)


def test_the_switch_is_from_the_next_day_and_by_the_build_clock() -> None:
    assert epochs.TENNIS_TOTALS_FLOOR_FROM_UTC == ON
    assert epochs.TENNIS_TOTALS_FLOOR == 0.60
    assert not epochs.tennis_totals_floor("2026-11-05", ON + timedelta(hours=5))
    assert not epochs.tennis_totals_floor("2026-11-06", ON - timedelta(minutes=1))
    assert epochs.tennis_totals_floor("2026-11-06", ON)


@pytest.mark.parametrize(("leg", "floor"), [
    ({"sport": "tennis", "market": "games_total"}, 0.60),
    ({"sport": "tennis", "market": "sets_total"}, 0.60),
    ({"sport": "tennis", "market": "games_set1_total"}, 0.70),
    ({"sport": "tennis", "market": "aces_total"}, 0.70),
    ({"sport": "football", "market": "games_total"}, 0.70),
    ({"sport": "basketball", "market": "sets_total"}, 0.70),
])
def test_only_tennis_games_and_sets_total_read_the_lower_floor(
    leg: dict[str, str], floor: float
) -> None:
    assert epochs.leg_floor(leg, "2026-11-06", 0.70, ON) == floor
    # before the switch every leg reads the profile's floor
    assert epochs.leg_floor(leg, "2026-11-05", 0.70, ON) == 0.70


def test_a_stricter_profile_keeps_its_own_floor() -> None:
    leg = {"sport": "tennis", "market": "games_total"}
    assert epochs.leg_floor(leg, "2026-11-06", 0.55, ON) == 0.55


def _tennis_leg(conf: float, odds: float, marker: float | None) -> dict[str, object]:
    leg = official_single(1, "games_total", odds, conf)
    leg["sport"] = "tennis"
    if marker is not None:
        leg[epochs.TENNIS_TOTALS_FLOOR_MARKER] = marker
    return leg


def _audit(tmp_path: Path, leg: dict[str, object]) -> list[str]:
    run = write_official(tmp_path, [leg])
    conf = run / "08_confidence.json"
    doc = json.loads(conf.read_text(encoding="utf-8"))
    doc.update(confidence_floor=0.70)
    t = conf.stat().st_mtime
    conf.write_text(json.dumps(doc), encoding="utf-8")
    os.utime(conf, (t, t))
    return [f for f in audit_variants.audit_confidence(str(tmp_path), DATE)
            if f.startswith("C2")]


def test_the_audit_reads_the_legs_own_floor_when_the_switch_admits_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(epochs, "TENNIS_TOTALS_FLOOR_FROM_UTC",
                        AT - timedelta(days=1))
    assert _audit(tmp_path, _tennis_leg(0.62, 1.70, 0.60)) == []


def test_the_audit_flags_a_lower_floor_the_switch_does_not_admit(
    tmp_path: Path,
) -> None:
    # the fixture day 2026-09-30 is before the switch: 0.62 is below 0.70
    got = _audit(tmp_path, _tennis_leg(0.62, 1.70, 0.60))
    assert any("not admitted" in f for f in got)
    assert any("below floor 0.7" in f for f in got)


def test_a_leg_without_the_marker_is_audited_on_the_profile_floor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(epochs, "TENNIS_TOTALS_FLOOR_FROM_UTC",
                        AT - timedelta(days=1))
    # CONFIDENCE always marks a leg it printed below the profile's floor, so
    # an unmarked 0.62 leg is a defect even while the switch is on
    got = _audit(tmp_path, _tennis_leg(0.62, 1.70, None))
    assert any("below floor 0.7" in f for f in got)
    got = _audit(tmp_path, _tennis_leg(0.58, 1.80, 0.60))
    assert any("below floor 0.6" in f for f in got)


def test_confidence_marks_the_leg_and_keeps_it_out_of_builders() -> None:
    src = (Path(__file__).resolve().parents[2]
           / "scripts/sofa/run_confidence.py").read_text(encoding="utf-8")
    assert "row_floor = leg_floor(row, args.date, floor, now)" in src
    assert "if realised_lo < row_floor:" in src
    assert "{TENNIS_TOTALS_FLOOR_MARKER: row_floor}" in src
    assert ("if leg.get(TENNIS_TOTALS_FLOOR_MARKER) is not None:\n"
            "            continue") in src
