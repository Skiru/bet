"""gap_shrink_k: the anti-selection shrink of the confidence (2026-10-04 night).

The curve is fitted on rows that mostly carry no price, while the coupon prints
only legs whose model sits above the devigged price; there the curve
over-states (priced live settled rows 09-17..10-02: printed 0.805, realised
0.745, devigged price 0.742). The shrink is built OFF: a calibration file
without the key - the installed one - reads exactly as before.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from bet.sofa.confidence import Calibration
from bet.sofa.fit_meta import OPERATOR_KEYS, carry_operator_keys
from tests.sofa.confidence_day import (  # noqa: F401
    DAY,
    _run,
    day,
)

REPO = Path(__file__).resolve().parents[2]


def _cal(tmp_path: Path, extra: dict[str, Any]) -> Calibration:
    path = tmp_path / "cal.json"
    path.write_text(json.dumps({"pooled": {}, "by_market": {}, **extra}))
    return Calibration.load(path)


def test_off_by_default_and_in_the_installed_file(tmp_path: Path) -> None:
    assert _cal(tmp_path, {}).gap_shrink_k == 0.0
    assert _cal(tmp_path, {"gap_shrink_k": None}).gap_shrink_k == 0.0
    installed = Calibration.load()
    assert installed.gap_shrink_k == 0.0
    assert installed.shrink_for_gap(0.81, 0.90, 0.70) == 0.81


def test_lowers_by_k_times_the_gap_above_the_price(tmp_path: Path) -> None:
    cal = _cal(tmp_path, {"gap_shrink_k": 0.85})
    # model 0.85 vs price 0.77: gap 0.08, 0.83 - 0.85 x 0.08 = 0.762
    assert cal.shrink_for_gap(0.83, 0.85, 0.77) == pytest.approx(0.762)


def test_never_raises_and_leaves_an_unpriced_rung_alone(tmp_path: Path) -> None:
    cal = _cal(tmp_path, {"gap_shrink_k": 0.85})
    assert cal.shrink_for_gap(0.80, 0.75, 0.82) == 0.80  # model below the price
    assert cal.shrink_for_gap(0.80, 0.95, None) == 0.80  # one-sided rung
    assert cal.shrink_for_gap(0.10, 1.0, 0.0) == 0.0  # floored at zero


@pytest.mark.parametrize("bad", ["0.8", -0.1, 2.5, True, [0.8]])
def test_a_malformed_value_is_refused(tmp_path: Path, bad: object) -> None:
    with pytest.raises(ValueError):
        _cal(tmp_path, {"gap_shrink_k": bad})


def test_it_is_an_operator_key_a_refit_carries() -> None:
    assert "gap_shrink_k" in OPERATOR_KEYS
    new: dict[str, Any] = {"by_market": {}}
    carry_operator_keys(new, {"gap_shrink_k": 0.85})
    assert new["gap_shrink_k"] == 0.85


def test_run_confidence_shrinks_before_the_floor_and_the_price_gate() -> None:
    source = (REPO / "scripts/sofa/run_confidence.py").read_text()
    i = source.index("realised_lo = cal.shrink_for_gap(")
    assert source.index("realised_lo, source, n_cal = hit") < i
    assert i < source.index("if realised_lo < floor:")
    assert i < source.index("if not profile.clears_price(realised_lo, odds):")


def test_end_to_end_off_and_on(day: Path, tmp_path: Path) -> None:  # noqa: F811
    """The fixture day: both legs print with the shrink off; with k on, each
    loses k x its gap (model - price = 0.03), and a large k drops them."""
    run = day / DAY
    off = _run("run_confidence.py", day, "--runs-dir", str(day))
    assert off.returncode == 0, off.stderr
    doc_off = json.loads((run / "08_confidence.json").read_text())
    assert {s["sofascore_event_id"] for s in doc_off["singles"]} == {1, 2}
    assert "gap_shrink_k" not in doc_off
    assert all("confidence_curve" not in leg for leg in doc_off["legs"])

    def with_k(k: float) -> dict[str, Any]:
        scratch = tmp_path / f"cal_k{k}.json"
        shutil.copy(REPO / "config/sofa_confidence_calibration.json", scratch)
        cal_doc = json.loads(scratch.read_text())
        cal_doc["gap_shrink_k"] = k
        scratch.write_text(json.dumps(cal_doc))
        on = _run("run_confidence.py", day, "--runs-dir", str(day),
                  "--calibration", str(scratch))
        assert on.returncode == 0, on.stderr
        doc: dict[str, Any] = json.loads(
            (run / "08_confidence.json").read_text())
        assert doc["gap_shrink_k"] == k
        return doc

    # k = 0.3: 0.3 x 0.03 = 0.009 off each leg; both still clear the
    # floor (0.70) and the price tolerance (x >= 0.90).
    small = with_k(0.3)
    assert {s["sofascore_event_id"] for s in small["singles"]} == {1, 2}
    curve = {leg["sofascore_event_id"]: leg["confidence"] for leg in doc_off["legs"]}
    assert len(small["legs"]) == 2
    for leg in small["legs"]:
        assert leg["confidence_curve"] == curve[leg["sofascore_event_id"]]
        assert leg["confidence"] == pytest.approx(leg["confidence_curve"] - 0.009)
    # k = 2.0: 0.06 off each leg; A falls under the floor, B under x = 0.90.
    assert with_k(2.0)["singles"] == []


def test_a_scratch_calibration_refuses_the_real_runs_dir(day: Path, tmp_path: Path) -> None:  # noqa: F811
    """--calibration writes the same artifact names as the real run, so it
    refuses runs/sofa itself (night review 2026-10-04); before any read."""
    scratch = tmp_path / "cal.json"
    shutil.copy(REPO / "config/sofa_confidence_calibration.json", scratch)
    out = _run("run_confidence.py", day, "--runs-dir", str(REPO / "runs" / "sofa"),
               "--calibration", str(scratch))
    assert out.returncode == 2
    assert "REFUSED" in out.stderr


def test_measure_disagreement_applies_the_shrink_like_run_confidence() -> None:
    source = (REPO / "scripts/sofa/measure_disagreement.py").read_text()
    assert "cal.shrink_for_gap(" in source
