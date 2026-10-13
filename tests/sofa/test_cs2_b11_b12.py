"""Audit 2026-10-13 B11 / B12: CS2 map identity and count exposure (offline)."""

from __future__ import annotations

import math
from datetime import UTC, datetime

from bet.sofa import cs2_engine as eng
from bet.sofa import epochs


def test_map_identity_stays_off() -> None:
    assert epochs.CS2_MAP_IDENTITY_FROM_UTC is None
    assert not epochs.cs2_map_identity("2030-01-01",
                                       datetime(2030, 1, 1, tzinfo=UTC))


def test_order_key_cells() -> None:
    assert eng.map_order_key(1, 1) == "bo1"
    assert eng.map_order_key(3, 2) == "bo3m2"
    assert eng.map_order_key(5, 2) == "other"
    assert eng.map_order_key(None, 1) == "other"


def test_p_map_nr_equals_p_map_without_terms() -> None:
    book = eng.EloBook()
    for _ in range(eng.MIN_MAPS_RATED + 2):
        book.update(1, 2)
    model = eng.RatingModel(book)
    assert model.p_map_nr(1, 2, True, 3, 2) == model.p_map(1, 2, True)


def test_order_term_moves_only_its_cell() -> None:
    book = eng.EloBook()
    for _ in range(eng.MIN_MAPS_RATED + 2):
        book.update(1, 2)
    model = eng.RatingModel(book, order_delta={"bo3m1": 0.4})
    base = model.p_map(1, 2, True)
    assert base is not None
    p1 = model.p_map_nr(1, 2, True, 3, 1)
    assert p1 is not None and p1 > base
    assert model.p_map_nr(1, 2, True, 3, 2) == base


def test_fit_offsets_recovers_a_shift() -> None:
    rows = [(0.0, [1.0], 1.0)] * 70 + [(0.0, [1.0], 0.0)] * 30
    beta = eng.fit_offsets(rows, 1, ridge=0.01)
    assert abs(beta[0] - math.log(70 / 30)) < 0.05


def test_pool_delta_is_zero_without_names() -> None:
    assert eng.MapPoolBook().delta(1, 2) == 0.0


def test_race_cells_are_a_distribution() -> None:
    cells = eng.race_cells(0.6, 0)
    assert abs(sum(q for q, _, _ in cells) - 1.0) < 0.01


def test_exposure_sides_orders_lines() -> None:
    cells = [(0.5, 15.0), (0.5, 20.0)]
    s = eng.exposure_sides(cells, 1.5, [10.5, 17.5, 25.5])
    overs = [s[ln][0] for ln in (10.5, 17.5, 25.5)]
    assert overs[0] > overs[1] > overs[2]
    for ln in s:
        assert abs(s[ln][0] + s[ln][1] - 1.0) < 1e-6


def test_exposure_p_needs_rates() -> None:
    assert eng.exposure_p(eng.ExposureBook(), 0.5, 1, 2, "kills", None, 20.5,
                          True) is None


def test_exposure_covers_the_measured_families_only() -> None:
    assert "player_headshots" not in eng.EXPOSURE_FAMILIES
    assert {"player_kills", "player_deaths", "player_assists",
            "team_kills"} <= eng.EXPOSURE_FAMILIES


def test_exposure_switch_from_next_day() -> None:
    at = datetime(2026, 10, 14, 0, 1, tzinfo=UTC)
    assert epochs.cs2_count_exposure("2026-10-14", at)
    assert not epochs.cs2_count_exposure("2026-10-13", at)
    assert not epochs.cs2_count_exposure(
        "2026-10-14", datetime(2026, 10, 13, 23, 0, tzinfo=UTC))
