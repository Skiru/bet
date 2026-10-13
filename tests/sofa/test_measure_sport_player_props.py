"""scripts/sofa/measure_sport_player_props.py - the pure helpers of the
player-line measurement (pre-registered in
docs/sofa/evidence/sport_player_props_2026-10-13.md)."""

import pytest

from bet.sofa import line_evidence as le
from scripts.sofa.measure_sport_player_props import (
    DownOnlyEvidence,
    appearances_in,
    boot_contrast,
    boot_mean,
    career_counts,
    cmh_difference,
    is_moved,
    player_line,
    pooled,
    prints,
    side_ids,
    verdict_m2,
    verdict_q1,
)

DAY = 86400


def _graded(**kw: object) -> dict[str, object]:
    g: dict[str, object] = {
        "family": "player_pp_points", "side": "UNDER", "model_source": "pregame",
        "model_p": 0.81, "outcome": "WIN", "odds": 1.43, "overround": 0.07,
        "model_n": 6, "model_player_id": 7}
    g.update(kw)
    return g


def test_player_line_keeps_only_pregame_graded_priced_player_sides():
    row = player_line("hockey", "2026-10-10", "15", _graded())
    assert row is not None
    assert row["key"] == "player_pp_points|UNDER"
    assert row["game"] == "s:2026-10-10:15"
    assert (row["y"], row["n_team"], row["p"]) == (1, 6, 0.81)
    assert player_line("hockey", "d", "1", _graded(model_source="settle")) is None
    assert player_line("hockey", "d", "1", _graded(outcome="VOID")) is None
    assert player_line("hockey", "d", "1", _graded(model_p=None)) is None
    assert player_line("hockey", "d", "1", _graded(odds=None)) is None
    assert player_line("hockey", "d", "1", _graded(family="total")) is None


def _entry(pid: int, team: int, seconds: int = 900) -> dict[str, object]:
    return {"player": {"id": pid, "name": "x"}, "teamId": team,
            "statistics": {"secondsPlayed": seconds}}


def test_appearances_read_the_team_from_the_side_not_the_entry_team_id():
    # Player 1 was traded: his entry carries the new team's id (9) in a game
    # he played for the home side (3).
    lineups = {"home": {"players": [_entry(1, 9), _entry(2, 3, seconds=0)]},
               "away": {"players": [_entry(4, 5)]}}
    got = appearances_in(lineups, {1, 2, 4}, 3, 5)
    assert sorted(got) == [(1, 3, 9), (4, 5, 5)]  # 2 did not play
    assert side_ids({"homeTeam": {"id": 3}, "awayTeam": {}}) == (3, None)


def test_career_counts_window_current_team_and_mislabels():
    k = 1000 * DAY
    apps = [(k - 400 * DAY, 1, 2),      # outside the window
            (k - 300 * DAY, 1, 2), (k - 200 * DAY, 1, 2),   # old team, new id
            (k - 10 * DAY, 2, 2), (k - 5 * DAY, 2, 2),
            (k + DAY, 2, 2)]           # after the kickoff
    assert career_counts(apps, k) == (4, 2, 2)
    assert career_counts([], k) == (0, 0, 0)


def test_moved_needs_other_team_games_and_a_thin_team_sample():
    assert is_moved(6, 80)
    assert not is_moved(25, 80)
    assert not is_moved(6, 3)
    assert not is_moved(6, None)


def test_boot_contrast_is_deterministic_and_signs_the_difference():
    items = [(f"g{i}", i % 2 == 0, (-0.2 if i % 2 == 0 else 0.0) + 0.01 * (i % 5))
             for i in range(60)]
    a = boot_contrast(items, reps=200)
    b = boot_contrast(items, reps=200)
    assert a == b
    assert a["diff"] < 0
    assert a["diff_ci"][0] <= a["diff"] <= a["diff_ci"][1]
    assert (a["a_lines"], a["b_lines"]) == (30, 30)
    assert "diff" not in boot_contrast([("g", True, 1.0)], reps=10)


def test_boot_mean_counts_lines_and_games():
    got = boot_mean([("a", 1.0), ("a", 0.0), ("b", 1.0)], reps=100)
    assert (got["lines"], got["games"]) == (3, 2)
    assert got["mean"] == pytest.approx(2 / 3, abs=1e-4)
    assert boot_mean([], reps=10)["mean"] is None


def test_cmh_difference_compares_bands_inside_a_stratum_only():
    # Stratum A: low band 8/10, high band 5/10 (-0.3); stratum B: only low.
    items = [(f"a{i}", "A", False, 1 if i < 8 else 0) for i in range(10)]
    items += [(f"h{i}", "A", True, 1 if i < 5 else 0) for i in range(10)]
    items += [(f"b{i}", "B", False, 1) for i in range(10)]
    got = cmh_difference(items, reps=100)
    assert got["diff"] == pytest.approx(-0.3)
    assert (got["strata"], got["lo_lines"], got["hi_lines"]) == (1, 10, 10)
    assert verdict_m2({"hi_games": 5, "diff_ci": [-0.5, -0.1]}) == "N_TOO_SMALL"
    assert verdict_m2({"hi_games": 40, "diff_ci": [-0.5, -0.1]}) == "CONFIRMED"
    assert verdict_m2({"hi_games": 40, "diff_ci": [-0.5, 0.1]}) == "NOT_CONFIRMED"


def test_verdict_q1_needs_the_thin_group_size_first():
    small = {"K1_thin_vs_rest": {"a_lines": 99, "a_games": 40, "diff_ci": [-1, -0.1]}}
    assert verdict_q1(small) == "N_TOO_SMALL"
    ok = {"K1_thin_vs_rest": {"a_lines": 100, "a_games": 30, "diff_ci": [-1, -0.1]}}
    assert verdict_q1(ok) == "CONFIRMED"
    ok["K1_thin_vs_rest"]["diff_ci"] = [-1, 0.1]
    assert verdict_q1(ok) == "NOT_CONFIRMED"


def test_pooled_sums_bucket_cells_between_two_edges():
    cells = {"0.750-0.800": {"n": 73, "k": 44}, "0.800-0.825": {"n": 14, "k": 8},
             "0.825-0.850": {"n": 17, "k": 12}}
    assert pooled(cells, 0.75, 0.80) == (87, 52)
    assert pooled(cells, 0.80, 0.80) == (14, 8)


def _doc() -> dict[str, object]:
    key = "player_pp_points|UNDER"
    band = {"0.750-0.800": {"n": 73, "k": 44}, "0.800-0.825": {"n": 14, "k": 8},
            "0.825-0.850": {"n": 17, "k": 12}, "0.850-0.875": {"n": 3, "k": 3},
            "0.875-0.900": {"n": 5, "k": 5}, "0.900-0.925": {"n": 3, "k": 3},
            "0.925-0.950": {"n": 1, "k": 1}, "0.950-1.010": {"n": 2, "k": 1}}
    return {"keys": {"hockey": {key: {"n": 905, "games": 68, "buckets": {
        "0.800-0.825": {"n": 87, "k": 73, "games": 45, "deff": 1.0}}}}},
        "bands": {"hockey": {key: {"1.30-1.60": band}}},
        "design_effect": {"hockey": 1.842}}


def test_down_only_cell_never_reaches_into_higher_p_buckets():
    # The 2026-10-13 case: p 0.807 at 1.43, 14 lines in its own cell.
    key = "player_pp_points|UNDER"
    cur = le.LineEvidence(_doc(), v2=True).band_cell("hockey", key, 0.807, 1.43)
    down = DownOnlyEvidence(_doc(), v2=True).band_cell("hockey", key, 0.807, 1.43)
    assert cur is not None and cur[:2] == (45, 33)       # its bucket and up
    assert down is not None and down[:2] == (87, 52)     # its bucket and down
    assert DownOnlyEvidence(_doc(), v2=True).band_cell("hockey", key, 0.807,
                                                       None) is None
    read = DownOnlyEvidence(_doc(), v2=True).read("hockey", key, 0.807, None, 1.43)
    assert read is not None and read.band_cap == pytest.approx(52 / 87, abs=1e-4)


def test_prints_applies_floor_value_and_margin():
    assert prints(0.72, 1.43, 0.07)
    assert not prints(0.69, 1.60, None)
    assert not prints(0.72, 1.20, None)
    assert not prints(0.72, 1.43, 0.16)
    assert not prints(None, 1.43, None)
