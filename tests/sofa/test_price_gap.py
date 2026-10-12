"""A confidence above the price (operator, 2026-10-12): bet.sofa.price_gap, its
place in the coupon (annotation only), the epoch switch, the PDF / HTML / md
sentence, and the pure parts of the measurement behind it."""

from __future__ import annotations

import datetime
from typing import Any

from bet.sofa import coupon_html as ch
from bet.sofa import epochs, price_gap
from bet.sofa import line_evidence as le
from scripts.sofa import measure_price_gap as mpg
from scripts.sofa.build_coupon import assemble, render_md
from scripts.sofa.build_coupon_pdf import price_gap_label

UTC = datetime.UTC
KO = "2026-10-13T18:00:00Z"


def leg(eid: int, conf: float, odds: float, sport: str = "football",
        market: str = "corners_total", line: float = 8.5) -> dict[str, Any]:
    return {
        "sofascore_event_id": eid, "confidence": conf, "kickoff_utc": KO,
        "market": market, "subject": "", "line": line, "direction": "OVER",
        "offered_odds": odds, "match": f"M{eid}", "sport": sport,
        "group_key": f"sofa:{eid}", "overround": 0.05,
    }


def _conf(singles: list[dict[str, Any]]) -> dict[str, Any]:
    return {"profile": "standard", "epoch": "stats_only", "created_at_utc": "x",
            "singles": singles, "legs": singles, "builders": []}


# --------------------------------------------------------------- the flag


def test_a_leg_more_than_three_points_above_its_price_is_flagged() -> None:
    # Pachuca - Necaxa 10-11: 0.7213 at 1.55 (1/1.55 = 0.645)
    pg = price_gap.annotate(leg(1, 0.7213, 1.55))
    assert pg is not None
    assert pg["flag"] == price_gap.FLAG
    assert pg["over_price"] == round(0.7213 - 1 / 1.55, 4)
    assert pg["measured_gap_pp"] == -6.8


def test_a_leg_at_or_under_the_threshold_is_not() -> None:
    # Bahia - Mirassol 10-11: 0.7756 at 1.29 (0.775): no gap
    assert price_gap.annotate(leg(1, 0.7756, 1.29)) is None
    # exactly GAP above the price: not flagged (strictly above)
    assert price_gap.annotate(leg(1, 0.80 + price_gap.GAP, 1.25)) is None


def test_tennis_reads_its_own_measurement() -> None:
    pg = price_gap.annotate(leg(1, 0.7632, 1.47, sport="tennis",
                                market="games_won_set1_for", line=3.5))
    assert pg is not None and pg["measured_gap_pp"] == -18.6
    assert "tenis" in price_gap.label({**leg(1, 0.7632, 1.47, sport="tennis"),
                                       "price_gap": pg})


def test_unmeasured_sports_and_missing_prices_carry_no_flag() -> None:
    assert price_gap.annotate(leg(1, 0.82, 1.54, sport="hockey")) is None
    assert price_gap.annotate({**leg(1, 0.82, 1.54), "offered_odds": None}) is None
    assert price_gap.label(leg(1, 0.82, 1.54)) == ""


# ------------------------------------------------------------- the coupon


def _day() -> list[dict[str, Any]]:
    return [leg(1, 0.7213, 1.55), leg(2, 0.7756, 1.29),
            leg(3, 0.82, 1.54, sport="hockey")]


def test_the_coupon_is_the_same_with_and_without_the_flag() -> None:
    off = assemble(_conf(_day()), None, [], {}, "now", "2026-10-13")
    on = assemble(_conf(_day()), None, [], {}, "now", "2026-10-13",
                  price_gap_active=True)

    def key(d: dict[str, Any]) -> list[tuple[Any, ...]]:
        return [(s["sofascore_event_id"], s["market"], s["line"], s["direction"],
                 s["position"], s["confidence"]) for s in d["singles"]]

    assert key(on) == key(off)
    assert all("price_gap" not in s for s in off["singles"])
    flagged = [s["sofascore_event_id"] for s in on["singles"] if s.get("price_gap")]
    assert flagged == [1]
    assert on["price_gap"]["legs"] == 1 and off["price_gap"]["active"] is False


def test_a_stale_flag_is_dropped_when_the_switch_is_off() -> None:
    stale = {**leg(1, 0.7213, 1.55), "price_gap": {"over_price": 0.9}}
    doc = assemble(_conf([stale]), None, [], {}, "now", "2026-10-13")
    assert "price_gap" not in doc["singles"][0]


def test_the_switch_starts_on_2026_10_12_at_11_51z() -> None:
    # the operator moved it to the rebuild of 10-12 (a mixed day)
    at = datetime.datetime(2026, 10, 12, 11, 51, tzinfo=UTC)
    assert epochs.price_gap_flag("2026-10-12", at) is True
    assert epochs.price_gap_flag("2026-10-13", at) is True
    assert epochs.price_gap_flag("2026-10-11", at) is False
    before = at - datetime.timedelta(minutes=1)
    assert epochs.price_gap_flag("2026-10-12", before) is False


# --------------------------------------------------------------- the page


def test_the_pdf_html_and_md_say_it() -> None:
    doc = assemble(_conf(_day()), None, [], {}, "now", "2026-10-13",
                   price_gap_active=True)
    by_ev = {s["sofascore_event_id"]: s for s in doc["singles"]}
    assert "ponad cenę" in price_gap_label(by_ev[1])
    assert price_gap_label(by_ev[2]) == "" and price_gap_label(by_ev[3]) == ""
    rows = {r["match"]: r for r in ch.build_view(doc, "2026-10-13", None)["rows"]}
    assert "ponad cenę" in rows["M1"]["price_gap"] and rows["M2"]["price_gap"] == ""
    assert "ponad cenę" in render_md(doc, "2026-10-13")


# ---------------------------------------------------- the measurement's parts


def test_disagreement_bins() -> None:
    assert [mpg.bin_of(d) for d in (-0.2, 0.03, 0.031, 0.06, 0.08, 0.2)] == \
        [0, 0, 1, 1, 2, 3]


def test_the_strict_cap_lowers_wherever_the_cell_realised_lower() -> None:
    cell = {"0.800-0.825": {"n": 40, "k": 31}}
    doc = {"bands": {"football": {"k": {"1.30-1.60": cell}}}, "min_cap_cell": 20}
    # 31/40 = 0.775 under 0.80: the current rule keeps it (Wilson upper 0.88)
    assert le.LineEvidence(doc).band_cap("football", "k", 0.81, 1.40, 0.80) is None
    assert mpg.StrictCap(doc).band_cap("football", "k", 0.81, 1.40, 0.80) == \
        (0.775, "k@1.30-1.60:0.800-0.825")
    assert mpg.StrictCap(doc).band_cap("football", "k", 0.81, 1.40, 0.77) is None


def test_prints_is_the_coupon_rule() -> None:
    assert mpg.prints(0.75, 1.20) is True   # x = 0.90 exactly
    assert mpg.prints(0.69, 1.50) is False  # under the floor
    assert mpg.prints(0.72, 1.20) is False  # x 0.864
    assert mpg.prints(None, 1.20) is False
