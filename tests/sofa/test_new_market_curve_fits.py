"""scripts/sofa/fit_double_chance_curve.py and fit_shot_detail.py - the
replays behind the new markets' curves price as SHEET does and read only the
past (offline, synthetic)."""

from __future__ import annotations

import csv
import gzip
import json
from typing import Any

import pytest

from bet.sofa import football_rating as fr
from bet.sofa import football_result as res
from bet.sofa import shot_detail as sd
from scripts.sofa import fit_double_chance_curve as dc
from scripts.sofa import fit_shot_detail as fsd


def _m(eid: int, link: str, ts: int = 0, women: bool = False,
       x: int = 1, y: int = 0) -> dc.Match:
    return dc.Match(ts, eid, women, link, 1.6, 1.1, x, y)


def test_dc_prices_every_selection_as_sheet_and_leaves_unlinked_out() -> None:
    priced = dc.price([_m(1, fr.LINKED), _m(2, fr.UNLINKED)], 7.586)
    assert {p.match.event_id for p in priced} == {1}
    want = res.result_probs(1.6, 1.1, 7.586)
    got = {p.selection: p for p in priced}
    assert set(got) == {"1X", "X2", "12"}
    for sel, p in got.items():
        assert p.p == pytest.approx(want[sel], abs=1e-9)
    assert (got["1X"].y, got["X2"].y, got["12"].y) == (1, 0, 1)


def test_dc_run_gates_men_and_women_apart() -> None:
    day = 86400
    train = [dc.Priced(_m(i, fr.LINKED, ts=i), "1X", 0.72, int(i % 4 != 0))
             for i in range(2000)]
    hold = [dc.Priced(_m(10_000 + i, fr.LINKED, ts=10 * day + i), "1X", 0.72,
                      int(i % 4 != 0)) for i in range(400)]
    out = dc.run(train + hold, 10 * day, 20 * day, 30 * day)
    assert out["gate"][dc.KEY]["n"] == 400
    assert out["gate"][dc.WOMEN_KEY]["n"] == 0
    assert not out["gate"][dc.WOMEN_KEY]["pass"]
    assert out["counts"] == {"train": 2000, "holdout": 400, "final": 2400}


def test_shot_forecasts_read_only_earlier_starts() -> None:
    fitted = {"metrics": {m: {"k": 2, "pool": {"F": 1.0}, "pool_all": 0.5}
                          for m in sd.METRICS}}
    counts = {m: 0 for m in sd.METRICS}
    big = {m: 9 for m in sd.METRICS}
    rows = [(t, t, 7, "F", counts) for t in range(sd.MIN_STARTS)]
    rows.append((100, 100, 7, "F", big))
    fc = fsd.forecasts(rows, fitted, 0, 10**9)
    m = sd.METRICS[0]
    assert len(fc[m]) == len(fsd.LINES)  # only the sixth start is priced
    p, y, eid, *_ = fc[m][0]
    assert eid == 100 and y == 1
    assert p == pytest.approx(sd.forecast([0.0] * sd.MIN_STARTS, "F", m, 0.5,
                                          fitted))


def test_shot_regate_rereads_holdout_rows_one_sided(tmp_path: Any) -> None:
    """--regate: saved holdout rows through the saved training curve; a curve
    that understates now passes and its saved final curve is staged."""
    key = "player_left_foot_shots_for|OVER"
    train = {key: {"0.750-0.800": {"n": 900, "realised": 0.74, "realised_lo95": 0.71}}}
    final = {key: {"0.750-0.800": {"n": 1200, "realised": 0.76, "realised_lo95": 0.74}}}
    doc = {"target": fsd.TARGET, "group": "shot_detail",
           "fitted_from": {"holdout": {"holdout_window": ["a", "b"]}},
           "by_market_direction": {},
           "gate": {key: {"pass": False}}, "training_curves": train,
           "final_curves_all_keys": final}
    (tmp_path / "curves.json").write_text(json.dumps(doc))
    with gzip.open(tmp_path / "rows_holdout.csv.gz", "wt", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["key", "line", "start_ts", "event_id", "player_id", "p", "y",
                    "curve_value"])
        for i in range(400):
            w.writerow([key, 0.5, i, i, 7, 0.77, int(i % 5 != 0), 0.71])
    out = fsd.regate(tmp_path)
    g = out["gate"][key]
    assert g["n"] == 400 and g["gap"] == pytest.approx(0.09)
    assert g["pass"] and not g["two_sided_pass"]
    assert out["by_market_direction"] == final
    assert out["fitted_from"]["regated"]["rule"] == "one_sided"
    assert "two-sided rule" in (tmp_path / "gate_report.md").read_text()


def test_dc_run_regates_with_saved_curves() -> None:
    day = 86400
    hold = [dc.Priced(_m(10_000 + i, fr.LINKED, ts=10 * day + i), "1X", 0.72,
                      int(i % 10 != 0)) for i in range(400)]  # realised 0.90
    curve = {"0.700-0.750": {"n": 900, "realised": 0.72, "realised_lo95": 0.70}}
    saved = {"training": {dc.KEY: curve, dc.WOMEN_KEY: {}},
             "final": {dc.KEY: curve, dc.WOMEN_KEY: {}}}
    out = dc.run(hold, 10 * day, 20 * day, 30 * day, saved)
    assert out["training"][dc.KEY] == curve
    assert out["gate"][dc.KEY]["pass"] and not out["gate"][dc.KEY]["two_sided_pass"]
