# ruff: noqa: E501  - test tables and fixtures read as one line.
"""The tennis serve curves (2026-10-17): install_new_market_curves.py's
replacing group `tennis_serve`, the curves fit_tennis_serve_curves.py builds,
and prepare_refit.install refusing a refit whose replay drops a rule those
curves were fitted on. Offline, tmp configs."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from scripts.sofa import fit_tennis_serve_curves as fit
from scripts.sofa import install_new_market_curves as inst
from scripts.sofa.prepare_refit import dropped_replay_rules

CURVE = {"0.700-0.750": {"n": 500, "realised": 0.74, "realised_lo95": 0.70},
         "0.750-0.800": {"n": 450, "realised": 0.79, "realised_lo95": 0.75}}
OLD = {"0.700-0.750": {"n": 900, "realised": 0.73, "realised_lo95": 0.71}}
THIN = {"0.800-0.825": {"n": 150, "realised": 0.80, "realised_lo95": 0.73}}
OK = f"{sys.executable} -c pass"


def _write(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc), encoding="utf-8")


def _setup(tmp_path: Path, under_passes: bool = True) -> tuple[Path, Path]:
    cfg = tmp_path / "config"
    _write(cfg / inst.FOOTBALL_TARGET, {
        "by_market": {"aces_for": OLD, "games_total": OLD,
                      "aces_set1_for": OLD},
        "by_market_direction": {"aces_for|OVER": OLD, "aces_for|UNDER": OLD,
                                "games_total|OVER": OLD},
        "thin_by_market_direction": {"aces_set1_for|OVER": OLD},
        "by_class": {"tennis_women": {
            "by_market_direction": {"aces_for|OVER": OLD},
            "thin_by_market_direction": {"aces_for|UNDER": OLD}},
            "tennis_team_cup": {"by_market": {"aces_for": OLD}}}})
    runs = tmp_path / "refit"
    _write(runs / "tennis_serve" / "curves.json", {
        "target": "sofa_confidence_calibration.json",
        "replace_markets": ["aces_for", "aces_set1_for"],
        "fitted_from": {"before": "2026-10-17",
                        "requires_replay_flags": ["tennis_aces_opponent"]},
        "by_market": {"aces_for": CURVE, "aces_set1_for": CURVE},
        "by_market_direction": {"aces_for|OVER": CURVE, "aces_for|UNDER": CURVE,
                                "aces_set1_for|OVER": CURVE},
        "thin_by_market_direction": {"aces_set1_for|UNDER": THIN},
        "by_class": {"tennis_women": {
            "by_market": {"aces_for": CURVE},
            "by_market_direction": {"aces_for|OVER": CURVE},
            "thin_by_market_direction": {}}},
        "gate": {"aces_for|OVER": {"pass": True},
                 "aces_for|UNDER": {"pass": under_passes},
                 "aces_set1_for|OVER": {"pass": True},
                 "tennis_women:aces_for|OVER": {"pass": False}}})
    return cfg, runs


def _run(cfg: Path, runs: Path, tmp_path: Path) -> int:
    return inst.main(["--dir", str(runs), "--config-dir", str(cfg),
                      "--backup-dir", str(tmp_path / "backup"), "--confirm",
                      "--test-cmd", OK])


def _load(path: Path) -> dict[str, Any]:
    doc: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return doc


def test_a_replacing_group_replaces_every_curve_of_its_markets(tmp_path: Path) -> None:
    cfg, runs = _setup(tmp_path)
    assert _run(cfg, runs, tmp_path) == 0
    doc = _load(cfg / inst.FOOTBALL_TARGET)
    assert doc["by_market_direction"]["aces_for|OVER"] == CURVE
    assert doc["by_market_direction"]["aces_for|UNDER"] == CURVE
    assert doc["by_market"]["aces_for"] == CURVE
    # untouched market stays
    assert doc["by_market_direction"]["games_total|OVER"] == OLD
    assert doc["by_market"]["games_total"] == OLD
    # the old thin bucket of a replaced market is gone, the group's is in
    assert "aces_set1_for|OVER" not in doc["thin_by_market_direction"]
    assert doc["thin_by_market_direction"]["aces_set1_for|UNDER"] == THIN
    women = doc["by_class"]["tennis_women"]
    # the women's key failed: the old one is purged, nothing installed, and
    # no by_market stands in for it
    assert "aces_for|OVER" not in women["by_market_direction"]
    assert "aces_for" not in women.get("by_market", {})
    assert "aces_for|UNDER" not in women["thin_by_market_direction"]
    assert "aces_for" not in doc["by_class"]["tennis_team_cup"]["by_market"]
    rec = doc[inst.FITTED_FROM_KEY]
    assert set(rec) == {"aces_for|OVER", "aces_for|UNDER", "aces_set1_for|OVER"}
    assert rec["aces_for|OVER"]["requires_replay_flags"] == ["tennis_aces_opponent"]


def test_a_market_with_a_failed_direction_is_left_whole(tmp_path: Path) -> None:
    cfg, runs = _setup(tmp_path, under_passes=False)
    before = _load(cfg / inst.FOOTBALL_TARGET)
    assert _run(cfg, runs, tmp_path) == 0
    doc = _load(cfg / inst.FOOTBALL_TARGET)
    for field in ("by_market", "by_market_direction"):
        for key, curve in before[field].items():
            if key.startswith("aces_for"):
                assert doc[field][key] == curve
    assert doc["by_class"]["tennis_women"] == before["by_class"]["tennis_women"]
    # the other replaced market still goes in
    assert doc["by_market_direction"]["aces_set1_for|OVER"] == CURVE


def test_a_refit_dropping_a_required_replay_rule_is_refused() -> None:
    live = {inst.FITTED_FROM_KEY: {
        "aces_for|OVER": {"requires_replay_flags": ["tennis_aces_opponent"]},
        "double_chance|OVER": {"group": "double_chance"}}}
    without = {"fitted_from": {"replay_rules": {"flags": {"tennis_aces_opponent": False}}}}
    assert dropped_replay_rules(live, without) == ["aces_for|OVER: tennis_aces_opponent"]
    assert dropped_replay_rules(live, {}) == ["aces_for|OVER: tennis_aces_opponent"]
    with_it = {"fitted_from": {"replay_rules": {"flags": {"tennis_aces_opponent": True}}}}
    assert dropped_replay_rules(live, with_it) == []
    assert dropped_replay_rules({}, without) == []


def test_the_fit_writes_fit_confidences_sections_with_classes() -> None:
    rows: list[fit.Row] = []
    for i in range(500):
        rows.append((0.72, int(i % 4 != 0), i, i, None, "aces_for", "OVER"))
        rows.append((0.72, int(i % 4 != 0), 10_000 + i, i, "tennis_women",
                     "aces_for", "OVER"))
    for i in range(150):
        rows.append((0.81, 1, 20_000 + i, i, None, "serve_points_for", "UNDER"))
    out = fit.sections(rows)
    assert out["by_market_direction"]["aces_for|OVER"]["0.700-0.750"]["n"] == 1000
    assert out["by_market"]["aces_for"]["0.700-0.750"]["n"] == 1000
    women = out["by_class"]["tennis_women"]
    assert women["by_market_direction"]["aces_for|OVER"]["0.700-0.750"]["n"] == 500
    assert "serve_points_for|UNDER" not in out["by_market_direction"]
    assert out["thin_by_market_direction"]["serve_points_for|UNDER"][
        "0.800-0.825"]["n"] == 150
    assert fit.MARKETS >= {"aces_for", "serve_points_set2_total",
                           "double_faults_set1_for"}
    assert not any(m in fit.MARKETS for m in ("double_faults_for",
                                              "double_faults_total"))


def test_a_direction_that_never_prints_does_not_block_a_refused_market(
        tmp_path: Path) -> None:
    cfg = tmp_path / "config"
    _write(cfg / inst.FOOTBALL_TARGET, {
        "by_market": {"serve_points_total": OLD, "aces_total": OLD},
        "by_market_direction": {"aces_total|OVER": OLD}})
    runs = tmp_path / "refit"
    never = {"pass": False, "why": "no holdout forecast reads a curve value >= 0.7"}
    _write(runs / "tennis_serve" / "curves.json", {
        "replace_markets": ["serve_points_total", "aces_total"],
        "by_market": {"serve_points_total": CURVE, "aces_total": CURVE},
        "by_market_direction": {"serve_points_total|OVER": CURVE,
                                "serve_points_total|UNDER": CURVE,
                                "aces_total|OVER": CURVE,
                                "aces_total|UNDER": CURVE},
        "gate": {"serve_points_total|OVER": never,
                 "serve_points_total|UNDER": {"pass": True},
                 # a full-match market a pool could read: never-printing blocks
                 "aces_total|OVER": never, "aces_total|UNDER": {"pass": True}}})
    assert _run(cfg, runs, tmp_path) == 0
    doc = _load(cfg / inst.FOOTBALL_TARGET)
    # serve points (AWAITING_OWN_CURVE): UNDER in, OVER and by_market out
    assert doc["by_market_direction"]["serve_points_total|UNDER"] == CURVE
    assert "serve_points_total|OVER" not in doc["by_market_direction"]
    assert "serve_points_total" not in doc["by_market"]
    # aces_total: left whole
    assert doc["by_market"]["aces_total"] == OLD
    assert doc["by_market_direction"]["aces_total|OVER"] == OLD
