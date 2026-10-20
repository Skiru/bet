"""CS2 confidence above the price (operator, 2026-10-20): bet.sofa.price_gap's
later sport, its switch (epochs.CS2_PRICE_GAP_FROM_UTC), the coupon (annotation
only), the analysts' read order, and the pure parts of the measurement
(scripts/sofa/measure_cs2_price_gap.py)."""

from __future__ import annotations

import datetime
import random
from typing import Any

from bet.sofa import epochs, price_gap
from bet.sofa.confidence import read_value
from bet.sofa.sport_confidence import SportCalibration
from scripts.sofa import measure_cs2_price_gap as m
from scripts.sofa.build_coupon import assemble
from scripts.sofa.build_coupon_pdf import price_gap_label

UTC = datetime.UTC
KO = "2026-10-21T18:00:00Z"
CS2 = frozenset({"cs2"})


def leg(eid: int, conf: float, odds: float, sport: str = "cs2") -> dict[str, Any]:
    return {
        "sofascore_event_id": eid, "confidence": conf, "kickoff_utc": KO,
        "market": "team_maps", "family": "team_maps", "subject": "T", "line": 0.5,
        "direction": "OVER", "side": "OVER", "offered_odds": odds,
        "match": f"M{eid}", "sport": sport, "group_key": f"sofa:{eid}",
        "overround": 0.08,
    }


def _conf() -> dict[str, Any]:
    return {"profile": "standard", "epoch": "stats_only", "created_at_utc": "x",
            "singles": [], "legs": [], "builders": []}


def _sports(legs: list[dict[str, Any]]) -> dict[str, Any]:
    return {"legs": legs}


# --------------------------------------------------------------- the flag


def test_a_cs2_leg_is_flagged_only_when_the_build_names_cs2() -> None:
    above = leg(1, 0.78, 1.40)  # 1/1.40 = 0.714, 0.066 above
    assert price_gap.annotate(above) is None
    pg = price_gap.annotate(above, CS2)
    assert pg is not None and pg["measured_gap_pp"] == -18.6
    assert "lines" in pg["measured_on"] and "series" in pg["measured_on"]
    text = price_gap.label({**above, "price_gap": pg})
    assert "CS2" in text and "238 linii Superbetu" in text and "09-28..10-19" in text


def test_the_bbl_leg_of_10_20_stays_unflagged() -> None:
    # "BBL liczba map: powyżej 0.5" 0.7179 at 1.44: 0.024 above 1/odds
    assert price_gap.annotate(leg(1, 0.7179, 1.44), CS2) is None


def test_other_measured_sports_stay_unflagged() -> None:
    assert price_gap.annotate(leg(1, 0.82, 1.54, sport="hockey"), CS2) is None
    assert price_gap.annotate(leg(1, 0.82, 1.54, sport="basketball"), CS2) is None


def test_football_and_tennis_unchanged() -> None:
    pg = price_gap.annotate(leg(1, 0.7213, 1.55, sport="football"))
    assert pg is not None and pg["measured_gap_pp"] == -6.8
    assert pg["measured_on"] == "football 458 legs / 269 matches, 10-09..10-11"
    assert "458 nóg 10-09..10-11" in price_gap.label(
        {**leg(1, 0.7213, 1.55, sport="football"), "price_gap": pg})


def test_the_switch_starts_on_2026_10_21_at_00z() -> None:
    at = datetime.datetime(2026, 10, 21, 0, 0, tzinfo=UTC)
    assert epochs.price_gap_sports("2026-10-21", at) == CS2
    assert epochs.price_gap_sports("2026-10-20", at) == frozenset()
    before = datetime.datetime(2026, 10, 20, 23, 59, tzinfo=UTC)
    assert epochs.price_gap_sports("2026-10-21", before) == frozenset()


# ------------------------------------------------------------- the coupon


def test_the_coupon_is_the_same_and_only_the_flag_differs() -> None:
    day = [leg(1, 0.78, 1.40), leg(2, 0.7179, 1.44)]
    off = assemble(_conf(), _sports([dict(x) for x in day]), [], {}, "now",
                   "2026-10-21", price_gap_active=True)
    on = assemble(_conf(), _sports([dict(x) for x in day]), [], {}, "now",
                  "2026-10-21", price_gap_active=True, price_gap_extra=CS2)
    key = [(s["sofascore_event_id"], s["position"], s["confidence"])
           for s in off["singles"]]
    assert key == [(s["sofascore_event_id"], s["position"], s["confidence"])
                   for s in on["singles"]]
    by_ev = {s["sofascore_event_id"]: s for s in on["singles"]}
    assert by_ev[1].get("price_gap") and not by_ev[2].get("price_gap")
    assert not any(s.get("price_gap") for s in off["singles"])
    assert on["price_gap"]["later_sports"] == ["cs2"] and on["price_gap"]["legs"] == 1
    assert off["price_gap"]["later_sports"] == []
    assert "ponad cenę" in price_gap_label(by_ev[1])


def test_read_value_caps_a_flagged_cs2_leg_only() -> None:
    x = leg(1, 0.78, 1.40)
    assert read_value(x) == 0.78 * 1.40  # built before the switch: as it was
    flagged = {**x, "price_gap": price_gap.annotate(x, CS2)}
    assert abs(read_value(flagged) - (1 / 1.40 + price_gap.GAP) * 1.40) < 1e-12


# ---------------------------------------------------- the measurement's parts


CAL = SportCalibration({"min_bucket": 1, "sports": {"cs2": {"curves": {
    "team_maps|OVER": {"0.70-0.80": {"n": 500, "realised_lo95": 0.76}}}}}})


def _settled(lines: list[tuple[float, float, float, str]]) -> dict[str, Any]:
    return {"events": {"1": {"state": "SETTLED", "sofascore_event_id": 9, "graded": [
        {"family": "team_maps", "side": "OVER", "model_p": mp, "fair_p": fair,
         "odds": odds, "outcome": out} for mp, fair, odds, out in lines]},
        "2": {"state": "NOT_ON_SOFASCORE", "graded": [
            {"family": "team_maps", "side": "OVER", "model_p": 0.75, "fair_p": 0.6,
             "odds": 1.5, "outcome": "WIN"}]}}}


def test_lines_read_the_curve_and_skip_what_cannot_be_judged() -> None:
    doc = _settled([(0.75, 0.62, 1.50, "WIN"), (0.75, 0.62, 1.50, "VOID"),
                    (0.95, 0.62, 1.50, "LOSS")])  # 0.95: no bucket
    lines = m.lines_of(doc, "2026-10-19", CAL)
    assert len(lines) == 1
    x = lines[0]
    assert (x.conf, x.fair, x.odds, x.won) == (0.76, 0.62, 1.50, 1)
    assert x.game == "2026-10-19:9"


def test_printable_and_flag_follow_the_coupon_rule() -> None:
    a = m.Line("g", "team_maps", 0.76, 0.6, 1.50, 1)   # 0.093 above, x 1.14
    b = m.Line("g", "team_maps", 0.76, 0.7, 1.30, 1)   # 0.0 above, x 0.988
    c = m.Line("g", "team_maps", 0.76, 0.8, 1.15, 1)   # x 0.874: does not print
    d = m.Line("g", "team_maps", 0.69, 0.6, 1.60, 1)   # under the floor
    assert m.printable([a, b, c, d]) == [a, b]
    assert m.flagged(a) and not m.flagged(b)


def test_summary_resamples_series() -> None:
    lines = [m.Line("g1", "team_maps", 0.75, 0.6, 1.5, 1),
             m.Line("g1", "team_maps", 0.75, 0.6, 1.5, 0),
             m.Line("g2", "team_maps", 0.75, 0.6, 1.5, 1)]
    s = m.summary(lines, random.Random(1), boot=200)
    assert (s["n"], s["games"]) == (3, 2)
    assert abs(s["hit_minus_conf"] - (2 / 3 - 0.75)) < 1e-4
    assert abs(s["roi"] - (2 * 1.5 - 3) / 3) < 1e-4
    assert s["roi_ci"][0] <= s["roi"] <= s["roi_ci"][1]
    assert m.summary([], random.Random(1)) == {"n": 0}
