"""K13b: a pool filling a hole in a market's own curve is capped by the
market's own nearest bucket below p.

The curves are the installed 10-05 refit's goals_1h_total buckets (config/
sofa_confidence_calibration.json, 6fea99fd) and pooled:football's 0.80-0.825,
so the first test is Moss - Kongsvinger G1H O0.5 (p 0.803) of 2026-10-05.
"""

from __future__ import annotations

import dataclasses
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from bet.sofa import epochs
from bet.sofa.confidence import Calibration


def _b(n: int, lo95: float) -> dict[str, float]:
    return {"n": n, "realised": lo95 + 0.04, "realised_lo95": lo95}


POOL = {"0.700-0.750": _b(900_000, 0.738), "0.800-0.825": _b(1_314_715, 0.815),
        "0.825-0.850": _b(1_312_297, 0.8416)}


def _cal(**kw: bool) -> Calibration:
    return Calibration(
        pooled={},
        pooled_by_sport={"football": POOL},
        by_market={"goals_1h_total": {
            "0.700-0.750": _b(1142, 0.6912), "0.750-0.800": _b(476, 0.7312),
            "0.825-0.850": _b(462, 0.8153)}},
        by_market_direction={
            "goals_1h_total|OVER": {"0.700-0.750": _b(681, 0.6892)},
            "goals_1h_total|UNDER": {"0.825-0.850": _b(444, 0.8153)}},
        thin_by_market_direction={
            "goals_1h_total|OVER": {"0.750-0.800": _b(163, 0.7094)},
            "goals_1h_total|UNDER": {"0.750-0.800": _b(313, 0.7169),
                                     "0.800-0.825": _b(284, 0.7489)}},
        cap_market_by_thin=True,
        **kw,
    )


def test_moss_g1h_over_reads_its_own_bucket_below_not_the_pool() -> None:
    assert _cal().realised("goals_1h_total", 0.803, "football", "OVER") == (
        0.815, "pooled:football", 1_314_715)
    assert _cal(cap_pool_by_neighbour=True).realised(
        "goals_1h_total", 0.803, "football", "OVER"
    ) == (0.7094, "market_below:goals_1h_total|OVER", 163)


def test_a_thin_bucket_at_p_is_the_markets_own_evidence_and_stays_in_charge() -> None:
    # UNDER has a thin bucket at 0.80-0.825: the K13 cap reads it, and the
    # neighbour below (0.7169) does not override the market's own rows at p.
    for cal in (_cal(), _cal(cap_pool_by_neighbour=True)):
        assert cal.realised("goals_1h_total", 0.81, "football", "UNDER") == (
            0.7489, "market_thin:goals_1h_total|UNDER", 284)


def test_a_bucket_of_the_market_itself_is_never_touched() -> None:
    on = _cal(cap_pool_by_neighbour=True)
    assert on.realised("goals_1h_total", 0.83, "football", "OVER") == (
        0.8153, "market:goals_1h_total", 462)


def test_a_pool_already_below_the_neighbour_is_kept() -> None:
    cal = dataclasses.replace(
        _cal(cap_pool_by_neighbour=True),
        pooled_by_sport={"football": {**POOL, "0.800-0.825": _b(10, 0.70)}})
    assert cal.realised("goals_1h_total", 0.803, "football", "OVER") == (
        0.70, "pooled:football", 10)


def test_a_hole_with_nothing_below_is_left_to_the_pool() -> None:
    cal = Calibration(
        pooled={}, pooled_by_sport={"football": POOL},
        by_market={"corners_total": {"0.825-0.850": _b(500, 0.83)}},
        cap_market_by_thin=True, cap_pool_by_neighbour=True)
    assert cal.realised("corners_total", 0.71, "football", "OVER") == (
        0.738, "pooled:football", 900_000)


def test_the_catch_all_bottom_bucket_caps_nothing() -> None:
    # goals_2h_for OVER 0.70-0.75 on the settled rows: its only bucket below
    # was 0.00-0.60 (~0.24), which says nothing about a 0.70+ claim.
    cal = Calibration(
        pooled={}, pooled_by_sport={"football": POOL},
        by_market={"goals_2h_for": {"0.000-0.600": _b(9000, 0.24),
                                    "0.825-0.850": _b(500, 0.83)}},
        cap_market_by_thin=True, cap_pool_by_neighbour=True)
    assert cal.realised("goals_2h_for", 0.72, "football", "OVER") == (
        0.738, "pooled:football", 900_000)


def test_the_class_curves_carry_the_flag() -> None:
    section = {
        "by_market": {"goals_total": {"0.700-0.750": _b(500, 0.70),
                                      "0.825-0.850": _b(500, 0.82)}},
        "pooled_by_sport": {"football": POOL},
    }
    cal = Calibration(pooled={}, by_market={}, by_class={"women": section},
                      cap_pool_by_neighbour=True)
    assert cal.realised("goals_total", 0.81, "football", "OVER", "women") == (
        0.70, "women:market_below:goals_total", 500)


def test_the_epoch_starts_on_10_06_and_leaves_10_05_alone() -> None:
    late = datetime(2026, 10, 5, 23, 59, tzinfo=UTC)
    first = datetime(2026, 10, 6, 0, 0, tzinfo=UTC)
    assert not epochs.pool_neighbour_cap("2026-10-05", late)
    assert not epochs.pool_neighbour_cap("2026-10-05", first)
    assert not epochs.pool_neighbour_cap("2026-10-06", late)
    assert epochs.pool_neighbour_cap("2026-10-06", first)


def test_measure_pool_holes_scores_a_hole_row_against_both_claims(
    tmp_path: Path,
) -> None:
    import json

    from scripts.sofa import measure_pool_holes

    cal_path = tmp_path / "cal.json"
    c = _cal()
    cal_path.write_text(json.dumps({
        "pooled": {}, "pooled_by_sport": c.pooled_by_sport,
        "by_market": c.by_market, "by_market_direction": c.by_market_direction,
        "thin_by_market_direction": c.thin_by_market_direction,
    }))
    db = tmp_path / "s.db"
    con = sqlite3.connect(db)
    con.execute(
        "create table sofa_settled_row (market text, line real, direction text,"
        " actual_value real, p_central real, sport text, sofascore_event_id int,"
        " run_date text, offered_odds real, sample_mean real, sample_sd real,"
        " sample_size int, competition_id int)")
    rows = [("goals_1h_total", 0.5, "OVER", 1.0 if i % 2 else 0.0, 0.803,
             "football", i, "2026-10-01", 1.4, 1.0, 1.0, 10, 1) for i in range(10)]
    # A row the market's own bucket serves - not a pooled read, not counted.
    rows.append(("goals_1h_total", 0.5, "OVER", 1.0, 0.83, "football", 99,
                 "2026-10-01", 1.2, 1.0, 1.0, 10, 1))
    con.executemany("insert into sofa_settled_row values (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    rows)
    con.commit()
    con.close()
    out = tmp_path / "out.json"
    assert measure_pool_holes.main([
        "--db-path", str(db), "--calibration", str(cal_path), "--no-classes",
        "--bootstrap", "50", "--out", str(out)]) == 0
    report = json.loads(out.read_text())
    group = report["groups"]["hole_below"]
    assert group["rows"] == 10 and group["matches"] == 10
    assert group["claimed_pool"] == 0.815 and group["claimed_capped"] == 0.7094
    assert group["realised"] == 0.5
    assert group["realised_minus_pool"] == round(0.5 - 0.815, 4)
    assert report["groups"]["cap_acts"]["rows"] == 10
    assert report["groups"]["cap_acts:live"]["rows"] == 10
    # x = 0.815 x 1.4 = 1.14 and 0.7094 x 1.4 = 0.99: both admit all ten.
    assert group["would_stake_pool"]["rows"] == 10
    assert group["would_stake_capped"]["roi"] == round((5 * 0.4 - 5) / 10, 4)
