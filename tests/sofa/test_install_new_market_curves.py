"""scripts/sofa/install_new_market_curves.py and scripts/sofa/new_market_gate.py
- the new markets' curves install only where their holdout gate passed, never
over an existing curve, with a backup and a restore (offline, tmp configs)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from scripts.sofa import install_new_market_curves as inst
from scripts.sofa import new_market_gate as g

CURVE = {"0.700-0.750": {"n": 500, "realised": 0.74, "realised_lo95": 0.70},
         "0.750-0.800": {"n": 450, "realised": 0.79, "realised_lo95": 0.75}}
OK = f"{sys.executable} -c pass"
FAIL = f"{sys.executable} -c 'raise SystemExit(1)'"


def _write(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc), encoding="utf-8")


def _setup(tmp_path: Path) -> tuple[Path, Path]:
    cfg = tmp_path / "config"
    _write(cfg / inst.FOOTBALL_TARGET, {
        "by_market": {"goals_for": CURVE},
        "by_market_direction": {"goals_for|OVER": CURVE},
        "by_class": {"women": {"by_market_direction": {}}}})
    _write(cfg / inst.SPORT_TARGET, {"sports": {"hockey": {
        "curves": {"total|OVER": CURVE}, "curve_source": {}}}})
    runs = tmp_path / "refit"
    _write(runs / "double_chance" / "curves.json", {
        "target": "config/sofa_confidence_calibration.json",
        "fitted_from": {"before": "2026-10-15"},
        "by_market_direction": {"double_chance|OVER": CURVE},
        "by_class": {"women": {"by_market_direction": {"double_chance|OVER": CURVE}}},
        "gate": {"double_chance|OVER": {"pass": True},
                 "women:double_chance|OVER": {"pass": False}}})
    _write(runs / "shot_detail" / "curves.json", {
        "by_market_direction": {"player_headed_shots_for|OVER": CURVE},
        "gate": {"player_headed_shots_for|OVER": {"pass": False}}})
    _write(runs / "sport_derived" / "curves.json", {
        "fitted_from": {"before": "2026-10-15"},
        "sports": {"hockey": {"curves": {"double_chance|TEAM": CURVE}}},
        "gate": {"hockey:double_chance|TEAM": {"pass": True}}})
    return cfg, runs


def _run(cfg: Path, runs: Path, tmp_path: Path, *extra: str) -> int:
    return inst.main(["--dir", str(runs), "--config-dir", str(cfg),
                      "--backup-dir", str(tmp_path / "backup"), *extra])


def _load(path: Path) -> dict[str, Any]:
    doc: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return doc


def test_only_passing_keys_install_with_backup_and_fitted_from(tmp_path: Path) -> None:
    cfg, runs = _setup(tmp_path)
    assert _run(cfg, runs, tmp_path, "--confirm", "--test-cmd", OK) == 0
    fb = _load(cfg / inst.FOOTBALL_TARGET)
    assert fb["by_market_direction"]["double_chance|OVER"] == CURVE
    assert "player_headed_shots_for|OVER" not in fb["by_market_direction"]
    assert fb["by_class"]["women"]["by_market_direction"] == {}
    assert fb[inst.FITTED_FROM_KEY]["double_chance|OVER"]["group"] == "double_chance"
    sp = _load(cfg / inst.SPORT_TARGET)["sports"]["hockey"]
    assert sp["curves"]["double_chance|TEAM"] == CURVE
    assert sp["curve_source"]["double_chance|TEAM"] == "history"
    backup = tmp_path / "backup"
    assert "double_chance|OVER" not in _load(
        backup / inst.FOOTBALL_TARGET)["by_market_direction"]
    assert (backup / inst.SPORT_TARGET).is_file()


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    cfg, runs = _setup(tmp_path)
    before = (cfg / inst.FOOTBALL_TARGET).read_text()
    assert _run(cfg, runs, tmp_path, "--dry-run") == 0
    assert (cfg / inst.FOOTBALL_TARGET).read_text() == before
    assert not (tmp_path / "backup").exists()


def test_failed_tests_restore_the_backup(tmp_path: Path) -> None:
    cfg, runs = _setup(tmp_path)
    before = {p: (cfg / p).read_text() for p in (inst.FOOTBALL_TARGET,
                                                 inst.SPORT_TARGET)}
    assert _run(cfg, runs, tmp_path, "--confirm", "--test-cmd", FAIL) == 2
    for p, text in before.items():
        assert (cfg / p).read_text() == text


def test_an_existing_curve_is_never_overwritten(tmp_path: Path) -> None:
    cfg, runs = _setup(tmp_path)
    _write(runs / "football_incidents" / "curves.json", {
        "by_market_direction": {"goals_for|OVER": CURVE},
        "gate": {"goals_for|OVER": {"pass": True}}})
    before = (cfg / inst.FOOTBALL_TARGET).read_text()
    assert _run(cfg, runs, tmp_path, "--confirm", "--test-cmd", OK) == 2
    assert (cfg / inst.FOOTBALL_TARGET).read_text() == before
    assert not (tmp_path / "backup").exists()


def test_a_key_without_a_gate_does_not_install(tmp_path: Path) -> None:
    cfg, runs = _setup(tmp_path)
    _write(runs / "tennis_sets" / "curves.json",
           {"by_market_direction": {"set_score|OVER": CURVE}})
    assert _run(cfg, runs, tmp_path, "--confirm", "--test-cmd", OK) == 0
    assert "set_score|OVER" not in _load(
        cfg / inst.FOOTBALL_TARGET)["by_market_direction"]


def test_a_staged_next_file_is_merged_too(tmp_path: Path) -> None:
    cfg, runs = _setup(tmp_path)
    _write(cfg / "sofa_sport_confidence_calibration.next.json", {
        "effective_from": "2026-10-14",
        "sports": {"hockey": {"curves": {}}}})
    assert _run(cfg, runs, tmp_path, "--confirm", "--test-cmd", OK) == 0
    nxt = _load(cfg / "sofa_sport_confidence_calibration.next.json")
    assert nxt["sports"]["hockey"]["curves"]["double_chance|TEAM"] == CURVE


def test_a_malformed_curve_is_refused(tmp_path: Path) -> None:
    cfg, runs = _setup(tmp_path)
    _write(runs / "double_chance" / "curves.json", {
        "by_market_direction": {"double_chance|OVER": {"0.7-0.75": {"n": 0}}},
        "gate": {"double_chance|OVER": {"pass": True}}})
    assert _run(cfg, runs, tmp_path, "--dry-run") == 2


def test_an_existing_backup_dir_refuses(tmp_path: Path) -> None:
    cfg, runs = _setup(tmp_path)
    (tmp_path / "backup").mkdir()
    assert _run(cfg, runs, tmp_path, "--confirm", "--test-cmd", OK) == 2
    assert "double_chance|OVER" not in _load(
        cfg / inst.FOOTBALL_TARGET)["by_market_direction"]


def test_mode_is_required() -> None:
    with pytest.raises(SystemExit):
        inst.main(["--dir", "x"])


# --- new_market_gate --------------------------------------------------------


def test_fit_curve_keeps_only_buckets_with_enough_rows() -> None:
    rows = [(0.72, 1)] * 300 + [(0.72, 0)] * 100 + [(0.86, 1)] * 10
    c = g.fit_curve(rows)
    assert list(c) == ["0.700-0.750"]
    assert c["0.700-0.750"]["n"] == 400
    assert c["0.700-0.750"]["realised"] == 0.75
    assert c["0.700-0.750"]["realised_lo95"] < 0.75
    assert g.curve_value(c, 0.74) == c["0.700-0.750"]["realised_lo95"]
    assert g.curve_value(c, 0.80) is None


def test_gate_passes_a_calibrated_curve_and_fails_a_thin_or_off_one() -> None:
    curve = {"0.700-0.750": {"n": 1000, "realised": 0.75, "realised_lo95": 0.75}}
    good = [(0.72, int(i % 4 != 0), i) for i in range(400)]  # realised 0.75
    v = g.gate(curve, good, reps=50)
    assert v["pass"] and v["n"] == 400 and v["gap"] == 0.0
    thin = g.gate(curve, good[:200], reps=50)
    assert not thin["pass"] and "n 200" in thin["why"]
    off = g.gate(curve, [(0.72, int(i % 2 == 0), i) for i in range(400)], reps=50)
    assert not off["pass"] and off["gap"] == pytest.approx(-0.25)
    below = g.gate({"0.600-0.700": {"n": 900, "realised": 0.65,
                                    "realised_lo95": 0.64}},
                   [(0.65, 1, i) for i in range(500)], reps=50)
    assert not below["pass"] and below["n"] == 0


def test_gate_is_one_sided_an_understating_curve_passes() -> None:
    """Operator 2026-10-14 ~18:55Z: only an overstating curve fails."""
    curve = {"0.700-0.750": {"n": 1000, "realised": 0.75, "realised_lo95": 0.70}}
    under = g.gate(curve, [(0.72, int(i % 10 != 0), i) for i in range(400)], reps=50)
    assert under["gap"] == pytest.approx(0.20)  # realised 0.90 vs curve 0.70
    assert under["pass"] and not under["two_sided_pass"] and under["why"] == ""
    assert under["rule"] == "one_sided"
    over = g.gate({"0.700-0.750": {"n": 1000, "realised": 0.75,
                                   "realised_lo95": 0.725}},
                  [(0.72, int(i % 10 < 7), i) for i in range(400)], reps=50)
    assert over["gap"] == pytest.approx(-0.025)
    assert not over["pass"] and over["why"].startswith("overstates")


@pytest.mark.parametrize(("n", "gap", "one", "two"), [
    (300, -0.02, True, True), (300, 0.02, True, True), (300, 0.05, True, False),
    (300, -0.0201, False, False), (299, 0.0, False, False), (500, None, False, False),
])
def test_one_and_two_sided_rules(n: int, gap: float | None, one: bool,
                                 two: bool) -> None:
    assert g.one_sided_pass(n, gap) is one
    assert g.two_sided_pass(n, gap) is two


def test_a_final_curve_below_the_floor_fails_the_key() -> None:
    ok = {"pass": True, "why": ""}
    assert g.require_final(dict(ok), {"0.700-0.750": {"realised_lo95": 0.71}})["pass"]
    v = g.require_final(dict(ok), {"0.700-0.750": {"realised_lo95": 0.69}})
    assert not v["pass"] and "final curve" in v["why"]
    assert not g.require_final({"pass": False, "why": "n"}, {})["pass"]
