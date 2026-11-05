"""The refit-readiness audit of 2026-11-05 (scripts/sofa/measure_refit_readiness.py):
keys group into their market family, a cell's interval resamples games (not
lines), and a cell is flagged only when its interval excludes zero."""

from __future__ import annotations

import numpy as np

from scripts.sofa import measure_refit_readiness as mr


def test_family_strips_period_and_side_and_keeps_the_class() -> None:
    assert mr.family("corners_1h_for|OVER") == "corners"
    assert mr.family("women:goals_total|UNDER") == "women:goals"
    assert mr.family("tennis_women:games_won_set2_for|OVER") == \
        "tennis_women:games_won_set2"
    assert mr.family("double_chance|OVER") == "double_chance"


def test_band_edges() -> None:
    assert mr.band_of(0.5999) is None
    assert mr.band_of(0.60) == "0.60-0.70"
    assert mr.band_of(0.70) == ">=0.70"
    assert mr.band_of(0.99) == ">=0.70"


def test_interval_resamples_games_so_one_big_game_widens_it() -> None:
    # the same 200 lines: one line a game vs packed into 4 games of 50
    resid = np.array([0.3] * 100 + [-0.7] * 100)
    spread = mr.boot_gap([str(i) for i in range(200)], resid)
    packed = mr.boot_gap([str(i // 50) for i in range(200)], resid)
    assert spread[0] == packed[0]
    assert packed[2] - packed[1] > 3 * (spread[2] - spread[1])


def test_flag_only_when_the_interval_excludes_zero() -> None:
    over = [(str(i), 0.80, 1 if i % 2 else 0) for i in range(400)]  # 0.50 vs 0.80
    assert mr.cell(over)["flag"] == "OVER_PROMISE"
    fair = [(str(i), 0.50, 1 if i % 2 else 0) for i in range(400)]
    assert mr.cell(fair)["flag"] == ""
    small = over[:50]
    assert mr.cell(small)["flag"] == "SMALL"


def test_cells_group_key_family_and_sport() -> None:
    items = [("football", "corners_for|OVER", f"d:{i}", 0.75, 1) for i in range(5)]
    got = mr.cells(items)
    assert set(got) == {"football|key|corners_for|OVER|>=0.70",
                        "football|family|corners|>=0.70",
                        "football|sport|ALL|>=0.70"}
