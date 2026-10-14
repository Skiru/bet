"""scripts/sofa/fit_sport_derived.py: the gate of the measured sports'
derived-market curves and the shape it stages for the installer. Offline."""

from __future__ import annotations

import argparse
import importlib
from typing import Any

import pytest

from bet.sofa import sport_confidence as scf

fsd = importlib.import_module("scripts.sofa.fit_sport_derived")


def _check(n: int, conf: float, realised: float) -> dict[str, Any]:
    return {"n": n, "uncovered": 0, "buckets": {},
            "printable": {"n": n, "games": n // 3, "confidence": conf,
                          "realised": realised,
                          "realised_minus_confidence": [
                              round(realised - conf, 4),
                              round(realised - conf - 0.01, 4),
                              round(realised - conf + 0.01, 4)]}}


SKILL = {"logloss_model": 0.5, "logloss_base": 0.55, "diff": -0.05,
         "diff_lo": -0.06, "diff_hi": -0.04, "n": 900, "games": 300}
NO_SKILL = {**SKILL, "diff": 0.0, "diff_lo": -0.002, "diff_hi": 0.002}


def test_gate_passes_within_two_points_at_n_300() -> None:
    g = fsd.gate_key("double_chance|TEAM", _check(300, 0.75, 0.765), None, SKILL)
    assert g["pass"] and g["reasons"] == []


@pytest.mark.parametrize(("n", "realised", "why"), [
    (299, 0.76, "HOLDOUT_PRINTABLE_N<300"),
    (500, 0.725, "HOLDOUT_OVERSTATES>0.02"),   # overstates by 2.5 pp
])
def test_gate_fails_thin_or_overstating_holdout(n: int, realised: float,
                                                why: str) -> None:
    g = fsd.gate_key("double_chance|TEAM", _check(n, 0.75, realised), None, SKILL)
    assert not g["pass"] and g["reasons"][0].startswith(why)


def test_gate_is_one_sided_an_understating_curve_passes() -> None:
    """Operator 2026-10-14 ~18:55Z: realised above the curve by any amount
    passes; the old two-sided verdict stays for reference."""
    g = fsd.gate_key("double_chance|TEAM", _check(500, 0.75, 0.85), None, SKILL)
    assert g["pass"] and g["reasons"] == [] and g["two_sided_pass"] is False


def test_gate_follows_the_sport_admission() -> None:
    g = fsd.gate_key("double_chance|TEAM", _check(500, 0.75, 0.75),
                     "OVERSTATES: history_holdout bucket x", SKILL)
    assert not g["pass"]
    assert g["reasons"] == ["SPORT_ADMISSION: OVERSTATES: history_holdout bucket x"]


def test_no_draw_key_fails_by_policy() -> None:
    calibrated = _check(900, 0.80, 0.805)
    assert not fsd.gate_key("double_chance|12", calibrated, None, NO_SKILL)["pass"]
    assert not fsd.gate_key("double_chance|12", calibrated, None, None)["pass"]
    g = fsd.gate_key("double_chance|12", calibrated, None, SKILL)
    assert not g["pass"] and g["reasons"][0].startswith("NO_DRAW_POLICY")
    # a team key is not held to it
    assert fsd.gate_key("double_chance|TEAM", calibrated, None, NO_SKILL)["pass"]


def test_assembled_shape_is_read_by_the_sport_calibration() -> None:
    curve = {"0.750-0.800": {"n": 400, "realised": 0.79, "realised_lo95": 0.747}}
    partial = {
        "sport": "hockey", "switches": {}, "max_games": {"final": 4000},
        "windows_utc": {k: ["a", "b"] for k in ("fit", "holdout", "final")},
        "gate": {"double_chance|TEAM": {"pass": True, "final_curve": curve},
                 "double_chance|12": {"pass": False, "final_curve": curve}}}
    args = argparse.Namespace(db_path="copy.db", final_before="2026-10-15",
                              fit_before="2026-09-01", holdout_end="2026-10-14",
                              sims=1000)
    doc = fsd.assemble([partial], args)
    assert doc["target"] == "config/sofa_sport_confidence_calibration.json"
    sec = doc["sports"]["hockey"]
    assert set(sec["curves"]) == {"double_chance|TEAM"}  # a FAIL never enters
    assert sec["admitted"] == ["double_chance|TEAM"]
    assert set(doc["gate"]) == {"hockey:double_chance|TEAM", "hockey:double_chance|12"}
    assert doc["edges"] == scf.EDGES and doc["min_bucket"] == scf.MIN_BUCKET
    # merged into a calibration document, the live lookup reads it (1X side)
    cal = scf.SportCalibration({"min_bucket": doc["min_bucket"],
                                "sports": {"hockey": {"curves": sec["curves"],
                                                      "admitted": []}}})
    got = cal.lookup("hockey", "double_chance", "1X", 0.77, require_admitted=False)
    assert got is not None and got.value == pytest.approx(0.747)
    assert cal.lookup("hockey", "double_chance", "12", 0.77,
                      require_admitted=False) is None


def test_refuses_the_live_database(tmp_path: Any) -> None:
    with pytest.raises(SystemExit):
        fsd.main(["--db-path", str(fsd._REPO / "data" / "sofa.db"),
                  "--out-dir", str(tmp_path), "--assemble"])


def _rows(n: int, p: float, hit_every: int, ts0: int, prefix: str) -> list[Any]:
    return [{"key": "double_chance|TEAM", "p": p, "y": int(i % hit_every != 0),
             "game": f"{prefix}{i // 2}", "ts": ts0 + i} for i in range(n)]


def test_judge_fails_a_final_curve_that_never_reaches_the_floor() -> None:
    fit = _rows(800, 0.78, 5, 0, "f")            # realised 0.80
    hold = _rows(400, 0.78, 5, 10_000, "h")
    low = _rows(800, 0.78, 2, 20_000, "z")       # final realised 0.50
    ok = fsd.judge({"fit": fit, "holdout": hold, "final": fit}, {})
    assert ok["double_chance|TEAM"]["pass"]
    bad = fsd.judge({"fit": fit, "holdout": hold, "final": low}, {})
    assert not bad["double_chance|TEAM"]["pass"]
    assert bad["double_chance|TEAM"]["reasons"][0].startswith("FINAL_CURVE_BELOW")


def test_regate_reads_the_saved_rows(tmp_path: Any) -> None:
    import json
    fit = _rows(800, 0.78, 5, 0, "f")
    hold = _rows(400, 0.78, 5, 10_000, "h")
    (tmp_path / "rows").mkdir()
    for name, rs in (("fit", fit), ("holdout", hold), ("final", fit)):
        (tmp_path / "rows" / f"hockey_{name}.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in rs))
    (tmp_path / "partial_hockey.json").write_text(json.dumps(
        {"sport": "hockey", "gate": {"double_chance|TEAM": {"pass": False}}}))
    part = fsd.regate_sport("hockey", tmp_path)
    assert part["gate"] == fsd.judge({"fit": fit, "holdout": hold, "final": fit}, {})
    assert part["regated"]["previous_pass"] == []
