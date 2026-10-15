"""Basketball A7 hybrid (operator 2026-10-15, "WŁĄCZ JUŻ DZISIAJ"): the staged
sport calibration's basketball section carries the A7 families' curves
(total, handicap, team total - lines where the market stood) refitted on the
full odds cache, every other key from the 2026-10-14 A7 fit. Measured on
Superbet lines 10-05..10-14: log-loss -0.00123 [-0.00151, -0.00096], the
printable lines unchanged (docs/sofa/evidence/basketball_a7_full_2026-10-16.md).
At the market's line the model never earns 0.70 on these families: no bucket
of theirs may read a printable confidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from bet.sofa import sport_confidence as scf
from bet.sofa.config import config_path

A7_KEYS = ("total|OVER", "total|UNDER", "handicap|TEAM", "team_total|OVER",
           "team_total|UNDER")


def _section() -> dict[str, Any]:
    path = config_path(scf.NEXT_CALIBRATION_FILE)
    doc: dict[str, Any] = json.loads(Path(path).read_text(encoding="utf-8"))
    sec: dict[str, Any] = doc["sports"]["basketball"]
    return sec


def test_days_from_10_14_read_the_staged_file() -> None:
    assert scf.calibration_path_for("2026-10-15").name == scf.NEXT_CALIBRATION_FILE
    assert scf.calibration_path_for("2026-10-16").name == scf.NEXT_CALIBRATION_FILE


def test_a7_families_come_from_the_full_cache_fit() -> None:
    sec = _section()
    refit = sec["fitted_from"]["a7_families_refit"]
    assert tuple(refit["keys"]) == A7_KEYS
    assert refit["before"] == "2026-10-16"
    assert refit["market_positioned_lines"]["games_with_lines"] == 5910
    # every other key stays the 2026-10-14 fit's
    assert sec["fitted_from"]["before"] == "2026-10-14"
    assert sec["fitted_from"]["market_positioned_lines"]["games_with_lines"] == 2661
    assert "double_chance|TEAM" in sec["curves"]


def test_a7_families_never_read_a_printable_confidence() -> None:
    sec = _section()
    for key in A7_KEYS:
        curve = sec["curves"][key]
        assert curve, key
        assert all(b["realised_lo95"] < scf.PRINTABLE_FROM for b in curve.values()), key
