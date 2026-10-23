"""No curve from our settled days alone (bet.sofa.live_only_curves,
epochs.LIVE_ONLY_CURVE_REFUSED_FROM_UTC).

* fit_confidence leaves a key reached only by live SETTLE rows without a
  curve and lists it under `live_only_refused`; a key the replay reached
  keeps its curve (live rows still count in it).
* The installed curves: the keys of config/sofa_live_only_curves.json are
  read as markets without a curve from 2026-10-24 00:00Z - no pool stands
  in - and a day before it (10-23) reads exactly what it read.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import live_only_curves as loc
from bet.sofa.confidence import Calibration
from bet.sofa.config import config_path
from bet.sofa.db import migrate
from scripts.sofa import fit_confidence

N = 450
REPLAY = loc.REPLAY_RUN_DATE


def _insert(conn: sqlite3.Connection, run_date: str, sport: str, market: str,
            line: float, wins: int, n: int, p: float, start: int) -> None:
    for i in range(n):
        conn.execute(
            "INSERT INTO sofa_settled_row (run_date, sofascore_event_id, sport, "
            "competition_id, market, subject, line, direction, sample_size, "
            "sample_mean, sample_sd, p_central, p_bar, market_p, actual_value, "
            "outcome, settled_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (run_date, start + i, sport, 1, market, "", line, "UNDER", 10,
             1.0, 1.0, p, p, None, 0.0 if i < wins else line + 5.0,
             "WIN" if i < wins else "LOSS", "2026-10-20T00:00:00"))


def _fit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
         rows: list[tuple[str, str, str, float, int, int]]) -> dict[str, Any]:
    db = tmp_path / "s.db"
    migrate(str(db))
    conn = sqlite3.connect(db)
    for i, (run_date, sport, market, line, wins, n) in enumerate(rows):
        _insert(conn, run_date, sport, market, line, wins, n, 0.80,
                1 + i * 10_000)
    conn.commit()
    conn.close()
    out = tmp_path / "cal.json"
    monkeypatch.setattr(sys, "argv", ["fit_confidence", "--db-path", str(db),
                                      "--out", str(out)])
    assert fit_confidence.main() == 0
    doc: dict[str, Any] = json.loads(out.read_text(encoding="utf-8"))
    return doc


def test_a_key_of_live_rows_only_gets_no_curve_and_is_listed(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    doc = _fit(tmp_path, monkeypatch, [
        (REPLAY, "tennis", "aces_for", 2.5, 360, N),           # history
        ("2026-10-20", "tennis", "aces_for", 2.5, 0, N),       # + live
        ("2026-10-20", "tennis", "serve_points_total", 60.5, 400, N),  # live only
    ])
    # the replayed key keeps its curve, live rows counted in it
    cell = doc["by_market_direction"]["aces_for|UNDER"]["0.800-0.825"]
    assert cell["n"] == 2 * N
    assert "aces_for" in doc["by_market"]
    # the live-only key has no curve anywhere and is listed
    for section in ("by_market", "by_market_direction",
                    "thin_by_market_direction"):
        assert not any(k.startswith("serve_points_total")
                       for k in doc[section])
    assert "by_market:serve_points_total" in doc[loc.REFUSED_FIELD]
    assert ("by_market_direction:serve_points_total|UNDER"
            in doc[loc.REFUSED_FIELD])
    assert not any("aces_for" in e for e in doc[loc.REFUSED_FIELD])
    # the sport pool had replayed rows: kept
    assert doc["pooled_by_sport"]["tennis"]


def test_only_live_rows_leave_no_pool_either(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    doc = _fit(tmp_path, monkeypatch, [
        ("2026-10-20", "tennis", "aces_for", 2.5, 360, N),
    ])
    assert doc["by_market"] == {} and doc["pooled"] == {}
    assert doc["pooled_by_sport"] == {}
    assert "pooled:all" in doc[loc.REFUSED_FIELD]
    assert "pooled_by_sport:tennis" in doc[loc.REFUSED_FIELD]


def test_a_line_curve_of_live_rows_only_is_refused(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    doc = _fit(tmp_path, monkeypatch, [
        (REPLAY, "football", "goals_for", 1.5, 360, N),
        ("2026-10-20", "football", "goals_for", 3.5, 360, N),
    ])
    lines = doc["by_market_direction_line"]["goals_for|UNDER"]
    assert "1.5" in lines and "3.5" not in lines
    assert ("by_market_direction_line:goals_for|UNDER@3.5"
            in doc[loc.REFUSED_FIELD])


def test_a_separately_fitted_curve_carried_in_is_not_listed(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    curve = {"0.800-0.825": {"n": 999, "realised": 0.9, "realised_lo95": 0.88}}
    (tmp_path / "cal.json").write_text(json.dumps({
        "by_market_direction": {"serve_points_total|UNDER": curve},
        "new_market_curves_fitted_from": {
            "serve_points_total|UNDER": {"group": "x", "script": "own_fit"}},
    }))
    doc = _fit(tmp_path, monkeypatch, [
        (REPLAY, "tennis", "aces_for", 2.5, 360, N),
        ("2026-10-20", "tennis", "serve_points_total", 60.5, 400, N),
    ])
    assert doc["by_market_direction"]["serve_points_total|UNDER"] == curve
    assert ("by_market_direction:serve_points_total|UNDER"
            not in doc[loc.REFUSED_FIELD])
    assert "by_market:serve_points_total" in doc[loc.REFUSED_FIELD]


# --- the installed curves under the switch ----------------------------------

def _cal() -> Calibration:
    bucket = {"0.800-0.825": {"n": 900, "realised": 0.85,
                              "realised_lo95": 0.82}}
    return Calibration(
        pooled={},
        by_market={"tiebreaks_total": bucket, "aces_for": bucket},
        pooled_by_sport={"tennis": {"0.800-0.825": {
            "n": 9000, "realised": 0.84, "realised_lo95": 0.83}}},
        by_market_direction={"tiebreaks_total|UNDER": bucket,
                             "aces_for|UNDER": bucket},
        by_class={"tennis_women": {
            "by_market": {"tiebreaks_total": bucket},
            "by_market_direction": {"tiebreaks_total|UNDER": bucket},
            "pooled_by_sport": {"tennis": bucket}}},
    )


ENTRIES = ["by_market:tiebreaks_total",
           "by_market_direction:tiebreaks_total|UNDER",
           "tennis_women.by_market:tiebreaks_total",
           "tennis_women.by_market_direction:tiebreaks_total|UNDER"]


def test_strip_reads_a_listed_key_as_a_market_without_a_curve() -> None:
    cal = _cal()
    assert cal.realised("tiebreaks_total", 0.81, "tennis", "UNDER") is not None
    out = loc.strip(cal, ENTRIES)
    # no curve and no pool standing in: line evidence's base is None
    assert out.realised("tiebreaks_total", 0.81, "tennis", "UNDER") is None
    assert out.realised("tiebreaks_total", 0.81, "tennis", "UNDER",
                        klass="tennis_women") is None
    # every other key reads exactly as before
    for market in ("aces_for",):
        assert (out.realised(market, 0.81, "tennis", "UNDER")
                == cal.realised(market, 0.81, "tennis", "UNDER"))
    assert out.unproven_ceiling_value() == cal.unproven_ceiling_value()
    assert loc.strip(cal, []) is cal


def _write_entries(tmp_path: Path) -> Path:
    path = tmp_path / loc.FILE
    path.write_text(json.dumps({"entries": ENTRIES}))
    return path


def test_the_switch_leaves_10_23_alone_and_changes_10_24(tmp_path: Path) -> None:
    path = _write_entries(tmp_path)
    cal = _cal()
    on = datetime(2026, 10, 24, 0, 0, 1, tzinfo=UTC)
    before = datetime(2026, 10, 23, 23, 59, tzinfo=UTC)
    # 10-23, built that day or rebuilt later: unchanged
    for at in (datetime(2026, 10, 23, 8, 0, tzinfo=UTC), on):
        same = loc.for_day(cal, "2026-10-23", at, path)
        assert same is cal
        assert same.realised("tiebreaks_total", 0.81, "tennis",
                             "UNDER") == (0.82, "market:tiebreaks_total|UNDER", 900)
    # 10-24 built before the moment (a planning pass): unchanged
    assert loc.for_day(cal, "2026-10-24", before, path) is cal
    # 10-24 from 00:00Z: the live-only key has no curve
    changed = loc.for_day(cal, "2026-10-24", on, path)
    assert changed.realised("tiebreaks_total", 0.81, "tennis", "UNDER") is None
    assert (changed.realised("aces_for", 0.81, "tennis", "UNDER")
            == cal.realised("aces_for", 0.81, "tennis", "UNDER"))


def test_the_installed_list_names_installed_fit_confidence_curves_only() -> None:
    entries = loc.load_entries()
    assert entries, "config/sofa_live_only_curves.json lists the measured keys"
    doc = json.loads(config_path("sofa_confidence_calibration.json")
                     .read_text(encoding="utf-8"))
    separate = set(doc.get("new_market_curves_fitted_from") or {})
    for raw in entries:
        assert loc.present(doc, raw), raw
        klass, section, key = loc.parse(raw)
        assert section != "pooled_by_sport" and section != "pooled", raw
        assert (f"{klass}:{key}" if klass else key) not in separate, raw
