"""scripts/sofa/fit_incident_set_curves.py - the staged history curves of the
football incident and tennis set markets (plan PLAN_KRZYWE_NOWE_RYNKI_
2026-10-14, steps 1-4). Offline and fast."""

from __future__ import annotations

from typing import Any

import pytest

from bet.sofa import football_rating as fr
from bet.sofa.confidence import Calibration
from bet.sofa.football_incidents import (
    FIRST_GOAL_NONE,
    RED_CARDS,
    IncidentRates,
    IncidentRecord,
    rates_from_records,
)
from scripts.sofa import fit_incident_set_curves as fit

DAY = 86400
T0 = 1_780_000_000 - 1_780_000_000 % DAY


def _rec(reds: int) -> IncidentRecord:
    return IncidentRecord(FIRST_GOAL_NONE, None, (0, 0), (), True, (reds, 0), (0, 0))


def test_incremental_rates_equal_the_batch_rates() -> None:
    recs = [(9, False, _rec(1 if i % 4 == 0 else 0)) for i in range(250)]
    recs.append((3, True, IncidentRecord(FIRST_GOAL_NONE, None, (0, 0), (), False,
                                         None, None)))
    inc = IncidentRates({}, {}, {})
    for comp, women, rec in recs:
        inc.add(comp, women, rec)
    batch = rates_from_records(recs)
    assert inc.women_comp == batch.women_comp
    for comp in (9, 3, 77):
        for line in (0.5, 1.5):
            assert inc.p_over(RED_CARDS, comp, line) == batch.p_over(
                RED_CARDS, comp, line)


def _result(eid: int, ts: int, comp: int = 9) -> fr.FootballResult:
    return fr.FootballResult(eid, ts, comp, 1000 + eid, 2000 + eid,
                             {"goals_for": (0.0, 0.0)})


def test_football_replay_prices_a_day_from_the_days_before() -> None:
    """SHEET cuts the history at the day: a match of the day never sees an
    earlier match of the same day."""
    history = [_result(i, T0 + i) for i in range(220)]  # day 0: a red in 1 of 4
    history += [_result(500, T0 + DAY + 10), _result(501, T0 + DAY + 20)]
    records = {r.event_id: _rec(1 if r.event_id % 4 == 0 else 0) for r in history}
    records[500] = _rec(3)  # a red-card riot early on day 1
    rows = fit.replay_football(history, records, T0 + 2 * DAY, 7.0)
    over = {r["event_id"]: r["p"] for r in rows
            if r["key"] == "red_cards_total|OVER" and r["line"] == 0.5}
    assert set(over) == {500, 501}  # day 0 had no gender rate yet (< 200)
    assert over[500] == pytest.approx(over[501])
    under = [r for r in rows if r["event_id"] == 500
             and r["key"] == "red_cards_total|UNDER" and r["line"] == 0.5]
    assert under and under[0]["y"] == 0


def test_curve_buckets_floor_and_wilson() -> None:
    sel = [(0.72, 1)] * 300 + [(0.72, 0)] * 100 + [(0.81, 1)] * 399
    curve = fit.fit_curve(sel)
    assert list(curve) == ["0.700-0.750"]  # 0.80-0.825 holds 399 < 400
    e = curve["0.700-0.750"]
    assert e["n"] == 400 and e["realised"] == 0.75
    assert e["realised_lo95"] < 0.75
    assert fit.curve_at(curve, 0.70) == e["realised_lo95"]
    assert fit.curve_at(curve, 0.75) is None


def test_a_symmetric_market_fits_both_directions_on_both_selections() -> None:
    rows: list[dict[str, Any]] = [
        {"key": "set1_won_for|OVER", "market": "set1_won_for", "p": 0.8, "y": 1},
        {"key": "set1_won_for|UNDER", "market": "set1_won_for", "p": 0.2, "y": 0},
        {"key": "set_score|OVER", "market": "set_score", "p": 0.4, "y": 0},
    ]
    assert fit.selections(rows, "set1_won_for|OVER") == [(0.8, 1), (0.2, 0)]
    assert fit.selections(rows, "set1_won_for|UNDER") == [(0.8, 1), (0.2, 0)]
    assert fit.selections(rows, "set_score|OVER") == [(0.4, 0)]


def test_gate_passes_a_calibrated_key_and_fails_a_short_or_off_one() -> None:
    train = [(0.82, 1)] * 850 + [(0.82, 0)] * 150
    lo = fit.fit_curve(train)["0.800-0.825"]["realised_lo95"]
    good = [(0.81, 1)] * 330 + [(0.81, 0)] * 70  # realised 0.825
    g = fit.gate(train, good)
    assert g["ge_070"]["n"] == 400
    assert g["pass"] is (0.825 - lo >= -0.02)
    bad = [(0.81, 1)] * 280 + [(0.81, 0)] * 120  # realised 0.70: overstated
    assert fit.gate(train, bad)["pass"] is False
    assert fit.gate(train, bad)["reason"].startswith("overstates")
    # one-sided (operator 2026-10-14): realised far above the curve passes,
    # the old two-sided verdict is kept for reference
    under = fit.gate(train, [(0.81, 1)] * 400)
    assert under["pass"] is True and under["two_sided_pass"] is False
    short = good[:299]
    assert fit.gate(train, short)["reason"].startswith("n <")
    # a holdout row whose bucket has no train curve is not read
    assert fit.gate(train, [(0.95, 1)] * 500)["ge_070"] is None


def test_staged_curves_read_through_calibration() -> None:
    """The shape the installer merges is the one CONFIDENCE reads."""
    curve = fit.fit_curve([(0.82, 1)] * 850 + [(0.82, 0)] * 150)
    cal = Calibration(pooled={}, by_market={},
                      by_market_direction={"first_goal|OVER": curve},
                      by_class={"women": {"by_market_direction": {
                          "red_cards_total|UNDER": curve}}})
    hit = cal.realised("first_goal", 0.81, "football", "OVER")
    assert hit is not None and hit[1] == "market:first_goal|OVER"
    assert cal.realised("first_goal", 0.81, "football", "OVER", "women") is None
    assert cal.realised("red_cards_total", 0.81, "football", "UNDER",
                        "women") is not None


def test_regate_from_rows_csv_reproduces_the_build(tmp_path: Any) -> None:
    """--regate re-reads rows.csv and decides as the replay run did."""
    rows = []
    for i in range(1600):
        ts = T0 + (i % 40) * DAY
        rows.append(fit._row("red_cards_total", "UNDER", "", 0.5, 0.82,
                             int(i % 10 < 9), 1000 + i, ts, "", fr.LINKED, 1))
    stamp = {"train_before": fit.iso_day(T0 + 20 * DAY),
             "holdout_to": fit.iso_day(T0 + 40 * DAY),
             "final_before": fit.iso_day(T0 + 41 * DAY), "rows": len(rows),
             "curve_rows": len(rows)}
    keys, classes = fit.GROUP_KEYS["football_incidents"]
    built = fit.build(rows, keys, classes, fit.day_ts(stamp["train_before"]),
                      fit.day_ts(stamp["holdout_to"]),
                      fit.day_ts(stamp["final_before"]), fit.football_usable)
    out = tmp_path / "football_incidents"
    out.mkdir()
    fit.write_group(out, "football_incidents", rows, built, stamp)
    doc = fit.regate(tmp_path, "football_incidents")
    assert doc["gate"] == built["gate"]
    assert doc["by_market_direction"] == built["by_market_direction"]
    assert doc["gate"]["red_cards_total|UNDER"]["pass"] is True
    assert doc["fitted_from"]["regated"]["rule"] == "one_sided"
