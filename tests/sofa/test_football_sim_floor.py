"""epochs.FOOTBALL_SIM_FLOOR (operator 2026-11-06 "TAK!", from 2026-11-07
00:00Z with FOOTBALL_SIM): the four football simulator keys that passed their
own 0.60-0.70 band (docs/sofa/evidence/football_sim_floor_2026-11-06.md) pass
the floor at 0.60, carry the leg's own floor and stay out of builders."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from bet.sofa import epochs
from scripts.sofa import audit_variants
from tests.sofa.coupon_fixtures import AT, DATE, official_single, write_official

ON = datetime(2026, 11, 7, 0, 0, tzinfo=UTC)


def test_the_switch_is_from_2026_11_07_and_needs_the_simulator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert epochs.FOOTBALL_SIM_FLOOR_FROM_UTC == ON
    assert epochs.FOOTBALL_SIM_FLOOR == 0.60
    assert not epochs.football_sim_floor("2026-11-06", ON - timedelta(minutes=1))
    assert epochs.football_sim_floor("2026-11-07", ON)
    monkeypatch.setattr(epochs, "FOOTBALL_SIM_FROM_UTC", None)
    assert not epochs.football_sim_floor("2026-11-07", ON)


def test_exactly_the_four_measured_keys() -> None:
    assert epochs.FOOTBALL_SIM_FLOOR_KEYS == {
        ("team_scores_both_halves", "UNDER"), ("half_goals_combo", "OVER"),
        ("btts_any_half", "UNDER"), ("btts_halves", "OVER")}
    assert all(m in epochs.FOOTBALL_SIM_MARKETS
               for m, _ in epochs.FOOTBALL_SIM_FLOOR_KEYS)


@pytest.mark.parametrize(("leg", "floor"), [
    ({"sport": "football", "market": "team_scores_both_halves",
      "direction": "UNDER"}, 0.60),
    ({"sport": "football", "market": "half_goals_combo", "direction": "OVER"}, 0.60),
    ({"sport": "football", "market": "btts_any_half", "direction": "UNDER"}, 0.60),
    ({"sport": "football", "market": "btts_halves", "direction": "OVER"}, 0.60),
    # failed their band (too few legs) or the other direction
    ({"sport": "football", "market": "team_scores_both_halves",
      "direction": "OVER"}, 0.70),
    ({"sport": "football", "market": "btts_any_half", "direction": "OVER"}, 0.70),
    ({"sport": "football", "market": "htft", "direction": "OVER"}, 0.70),
    ({"sport": "football", "market": "result_1h", "direction": "OVER"}, 0.70),
    ({"sport": "football", "market": "first_goal_1h", "direction": "OVER"}, 0.70),
    # every other football market and sport keeps the profile's floor
    ({"sport": "football", "market": "goals_total", "direction": "OVER"}, 0.70),
    ({"sport": "football", "market": "corners_total", "direction": "UNDER"}, 0.70),
    ({"sport": "tennis", "market": "half_goals_combo", "direction": "OVER"}, 0.70),
])
def test_only_the_passing_simulator_keys_read_the_lower_floor(
    leg: dict[str, str], floor: float
) -> None:
    assert epochs.leg_floor(leg, "2026-11-07", 0.70, ON) == floor
    assert epochs.leg_floor(leg, "2026-11-06", 0.70, ON - timedelta(hours=1)) == 0.70


def test_a_stricter_profile_keeps_its_own_floor() -> None:
    leg = {"sport": "football", "market": "half_goals_combo", "direction": "OVER"}
    assert epochs.leg_floor(leg, "2026-11-07", 0.55, ON) == 0.55


def test_tennis_totals_floor_unchanged() -> None:
    leg = {"sport": "tennis", "market": "games_total", "direction": "OVER"}
    assert epochs.leg_floor(leg, "2026-11-07", 0.70, ON) == epochs.TENNIS_TOTALS_FLOOR


def _sim_leg(conf: float, odds: float, marker: float | None) -> dict[str, object]:
    leg = official_single(1, "half_goals_combo", odds, conf)
    leg.update(sport="football", direction="OVER", subject="O0.5/O0.5")
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


def test_c2_reads_the_legs_own_floor_when_the_switch_admits_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(epochs, "FOOTBALL_SIM_FROM_UTC", AT - timedelta(days=1))
    monkeypatch.setattr(epochs, "FOOTBALL_SIM_FLOOR_FROM_UTC", AT - timedelta(days=1))
    assert _audit(tmp_path, _sim_leg(0.62, 1.70, 0.60)) == []


def test_c2_flags_the_floor_when_the_switch_is_off(tmp_path: Path) -> None:
    # the fixture day is before the switch: 0.62 is below 0.70
    got = _audit(tmp_path, _sim_leg(0.62, 1.70, 0.60))
    assert any("not admitted" in f for f in got)
    assert any("below floor 0.7" in f for f in got)


def test_c2_flags_a_key_that_did_not_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(epochs, "FOOTBALL_SIM_FROM_UTC", AT - timedelta(days=1))
    monkeypatch.setattr(epochs, "FOOTBALL_SIM_FLOOR_FROM_UTC", AT - timedelta(days=1))
    leg = _sim_leg(0.62, 1.70, 0.60)
    leg.update(market="htft", subject="1/1")
    got = _audit(tmp_path, leg)
    assert any("not admitted" in f for f in got)
