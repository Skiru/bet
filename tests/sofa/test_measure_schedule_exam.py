"""scripts/sofa/measure_schedule_exam.py - the one exam of the schedule term:
Holm, the one-sided bootstrap p, the pigeonhole bootstrap, P4, the verdict and
the exam log's refusal (G2)."""

from pathlib import Path

import numpy as np
import pytest

from scripts.sofa import measure_schedule_exam as mse


def test_holm_steps_down_and_stops_at_the_first_failure():
    out = mse.holm({"a": 0.001, "b": 0.02, "c": 0.03, "d": 0.04})
    # K = 4: levels 0.0125, 0.01667, 0.025, 0.05
    assert out["a"]["reject"] and out["a"]["level"] == pytest.approx(0.0125)
    assert not out["b"]["reject"]  # 0.02 > 0.05 / 3
    assert (
        not out["c"]["reject"] and not out["d"]["reject"]
    )  # stopped, though 0.04 <= 0.05


def test_holm_rejects_all_when_every_p_is_small():
    out = mse.holm({"a": 0.0005, "b": 0.0005, "c": 0.0005})
    assert all(v["reject"] for v in out.values())


def test_one_sided_p_is_floored_at_one_over_reps():
    assert mse.one_sided_p(np.full(2000, -1.0)) == pytest.approx(1 / 2000)
    assert mse.one_sided_p(np.array([-1.0, 0.0, 1.0, -2.0])) == pytest.approx(0.5)


def test_cluster_boot_is_seeded_and_centred_on_the_mean():
    rng = np.random.default_rng(0)
    num = rng.normal(-0.1, 1.0, 500)
    h = rng.integers(0, 50, 500)
    a = rng.integers(0, 50, 500)
    f = [(50, [h]), (50, [a])]
    b1 = mse.cluster_boot(num, np.ones(500), f, reps=300, seed=3)
    b2 = mse.cluster_boot(num, np.ones(500), f, reps=300, seed=3)
    assert np.array_equal(b1, b2)
    assert abs(b1.mean() - num.mean()) < 0.05


def test_cluster_boot_with_one_cluster_per_unit_is_the_plain_bootstrap_scale():
    num = np.r_[np.zeros(100), np.ones(100)]
    idx = np.arange(200)
    b = mse.cluster_boot(num, np.ones(200), [(200, [idx])], reps=2000, seed=1)
    assert b.std() == pytest.approx(0.5 / np.sqrt(200), rel=0.15)


def test_p4_compares_the_gaps_on_baseline_selected_rows():
    cb = np.array([0.80, 0.80, 0.50, 0.90])
    ct = np.array([0.75, 0.75, 0.95, 0.85])
    y = np.array([1.0, 0.0, 1.0, 1.0])
    out = mse.p4_check(cb, ct, y)
    # selected rows 0, 1, 3: realised 2/3, mean cb 0.8333, mean ct 0.7833
    assert out["rows"] == 3
    assert out["gap_base"] == pytest.approx(abs(2 / 3 - 0.8333333), abs=1e-6)
    assert out["gap_treat"] == pytest.approx(abs(2 / 3 - 0.7833333), abs=1e-6)
    assert out["pass"]


def test_verdict_needs_every_gate_and_an_exam_refit_sign():
    assert mse.verdict(True, True, True, True, True, True) == "PASS"
    assert mse.verdict(True, True, True, True, True, None) == "NOT_PASSED"
    assert mse.verdict(True, False, True, True, True, True) == "NOT_PASSED"


def test_the_exam_log_refuses_a_second_run(tmp_path: Path):
    log = tmp_path / "log.md"
    assert not mse.exam_already_run(log)
    log.write_text("| UTC | badanie |\n|---|---|\n")
    assert not mse.exam_already_run(log)
    log.write_text(f"| 2026-11-09T10:00:00+00:00 | {mse.STUDY} | abc | ... |\n")
    assert mse.exam_already_run(log)


def test_row_bound_is_the_per_row_mean():
    rm = np.array([0, 0, 1, 2])
    v = np.array([1.0, 3.0, 2.0, -6.0])
    b = mse.row_bound(
        rm, v, np.array([True, True, True, False]), 3, [(3, [np.arange(3)])], seed=1
    )
    assert b.point == pytest.approx(2.0)
    assert b.n == 3
