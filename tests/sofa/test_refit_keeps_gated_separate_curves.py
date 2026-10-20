"""Audit 2026-10-21 D6: a full refit never replaces a separately fitted curve
installed after the one-sided holdout gate when its p comes from an estimator
the cache replay does not run (fit_meta.PRIOR_WINS_GROUPS: card_halves,
player_props_v2, shot_detail). Before the fix fit_confidence kept its own
curve of any key it held - player_fouls_drawn_for OVER from replayed
plain-sample player rows (printed_player_ladder lets the market into
build_player_rows), the card halves from live SETTLE rows - ungated.
Offline and fast."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

from bet.sofa.config import config_path
from bet.sofa.fit_meta import (
    PRIOR_WINS_GROUPS,
    carry_separately_fitted_curves,
    prior_curve_wins,
)

REPO = Path(__file__).resolve().parents[2]
GATED = {"0.900-0.925": {"n": 777, "realised": 0.91, "realised_lo95": 0.89}}
OTHER = {"0.800-0.825": {"n": 50, "realised": 0.5, "realised_lo95": 0.4}}


def _db(path: Path) -> None:
    con = sqlite3.connect(path)
    con.execute("""create table sofa_settled_row (market text, line real,
        direction text, sample_size int, sample_mean real, sample_sd real,
        actual_value real, p_central real, sport text, sofascore_event_id int)""")
    con.execute("create table sofa_entity_events (kind text, events_json text)")
    rows: list[tuple[Any, ...]] = []
    # 1,200 rows at p 0.90 realising 0.50 per key: the fit makes its own curve
    for k, (market, line, direction) in enumerate((
            ("player_fouls_drawn_for", 0.5, "OVER"),
            ("cards_points_1h_for", 25.0, "UNDER"),
            ("goals_total", 4.5, "UNDER"))):
        for i in range(1200):
            hit = i % 2 == 0
            actual = (line + 1 if hit else line - 1) if direction == "OVER" \
                else (line - 1 if hit else line + 1)
            rows.append((market, line, direction, 10, 1.0, 1.0, actual, 0.91,
                         "football", 10_000 * k + i))
    con.executemany("insert into sofa_settled_row values (?,?,?,?,?,?,?,?,?,?)",
                    rows)
    con.commit()
    con.close()


def _prior() -> dict[str, Any]:
    return {
        "by_market_direction": {"player_fouls_drawn_for|OVER": GATED,
                                "cards_points_1h_for|UNDER": GATED,
                                "goals_total|UNDER": GATED},
        "new_market_curves_fitted_from": {
            "player_fouls_drawn_for|OVER": {"group": "player_props_v2"},
            "cards_points_1h_for|UNDER": {"group": "card_halves"},
        },
    }


def test_a_full_fit_keeps_the_gated_curves_it_also_fitted(tmp_path: Path) -> None:
    db = tmp_path / "sofa.db"
    _db(db)
    out = tmp_path / "cal.json"
    out.write_text(json.dumps(_prior()))
    proc = subprocess.run(
        [sys.executable, "scripts/sofa/fit_confidence.py", "--db-path", str(db),
         "--out", str(out)],
        cwd=REPO, capture_output=True, text=True,
        env={"PYTHONPATH": "src:.", "PATH": "/usr/bin:/bin"},
    )
    assert proc.returncode == 0, proc.stderr
    doc = json.loads(out.read_text())
    bmd = doc["by_market_direction"]
    assert bmd["player_fouls_drawn_for|OVER"] == GATED
    assert bmd["cards_points_1h_for|UNDER"] == GATED
    # a key the fit owns (no separate entry) is the fit's own
    assert bmd["goals_total|UNDER"] != GATED
    assert bmd["goals_total|UNDER"]["0.900-0.925"]["realised"] == 0.5


def test_only_the_gated_groups_win_over_the_fit() -> None:
    new: dict[str, Any] = {"by_market_direction": {
        "player_fouls_drawn_for|OVER": OTHER,
        "result_or_over@X@2.5|OVER": OTHER,
        "aces_for|OVER": OTHER}}
    prior = {
        "by_market_direction": {"player_fouls_drawn_for|OVER": GATED,
                                "result_or_over@X@2.5|OVER": GATED,
                                "aces_for|OVER": GATED},
        "new_market_curves_fitted_from": {
            "player_fouls_drawn_for|OVER": {"group": "player_props_v2"},
            "result_or_over@X@2.5|OVER": {"group": "football_score_markets"},
            # a curve that needs a replay flag is the fit's to replace
            "aces_for|OVER": {"group": "shot_detail",
                              "requires_replay_flags": ["tennis_aces_opponent"]},
        },
    }
    carried = carry_separately_fitted_curves(new, prior)
    assert carried == ["player_fouls_drawn_for|OVER"]
    assert new["by_market_direction"]["player_fouls_drawn_for|OVER"] == GATED
    assert new["by_market_direction"]["result_or_over@X@2.5|OVER"] == OTHER
    assert new["by_market_direction"]["aces_for|OVER"] == OTHER
    assert not prior_curve_wins(None)


def test_the_installed_gated_curves_survive_a_fit_that_holds_them() -> None:
    """player_fouls_drawn_for|OVER and the 20 card_halves keys of the
    installed calibration (class keys too) come through a fit that produced
    every one of them with another curve."""
    live = json.loads(config_path("sofa_confidence_calibration.json").read_text())
    listed = live["new_market_curves_fitted_from"]
    gated = {k for k, v in listed.items() if v.get("group") in PRIOR_WINS_GROUPS
             and v.get("group") != "shot_detail"}
    assert "player_fouls_drawn_for|OVER" in gated
    assert len([k for k in gated if listed[k]["group"] == "card_halves"]) == 20
    new: dict[str, Any] = {"by_market_direction": {}, "by_class": {}}
    for key in gated:
        klass, _, mk = key.rpartition(":")
        sect = (new["by_class"].setdefault(klass, {}) if klass else new)
        sect.setdefault("by_market_direction", {})[mk] = OTHER
    carry_separately_fitted_curves(new, live)
    for key in gated:
        klass, _, mk = key.rpartition(":")
        got = (new["by_class"][klass] if klass else new)["by_market_direction"][mk]
        want = (live["by_class"][klass] if klass else live)[
            "by_market_direction"][mk]
        assert got == want, key
