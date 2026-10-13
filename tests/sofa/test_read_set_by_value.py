"""The analysts' 30 matches are those of the best value - confidence x odds of
the match's best unlocked leg, a football / tennis confidence capped at
1/odds + price_gap.GAP - from epochs.READ_BY_VALUE_FROM_UTC (operator,
2026-10-13: "i prawdopodobieństwo i cenę najlepszą z danego dnia")."""

from __future__ import annotations

import datetime
from typing import Any

import pytest

from bet.sofa import epochs, price_gap
from bet.sofa.confidence import READ_REQUIRED_EVENTS, legs_requiring_read, read_value
from scripts.sofa.build_coupon import assemble

UTC = datetime.UTC


def leg(eid: int, conf: float, odds: float, sport: str = "football") -> dict[str, Any]:
    return {"sofascore_event_id": eid, "confidence": conf, "sport": sport,
            "kickoff_utc": "2026-10-14T20:00:00Z", "market": "corners_total",
            "subject": "", "line": 5.5, "direction": "OVER",
            "offered_odds": odds, "match": f"M{eid}", "display_market": "c"}


def build(singles: list[dict[str, Any]], by_value: bool) -> dict[str, Any]:
    conf = {"profile": "standard", "epoch": "stats_only", "created_at_utc": "x",
            "singles": singles, "legs": singles, "builders": []}
    return assemble(conf, None, [], {}, "now", "2026-10-14", read_events=True,
                    read_value_order=by_value)


def test_the_switch_is_the_next_days_midnight() -> None:
    at = epochs.READ_BY_VALUE_FROM_UTC
    assert at == datetime.datetime(2026, 10, 14, 0, 0, tzinfo=UTC)
    assert not epochs.read_by_value("2026-10-13", at)
    assert not epochs.read_by_value("2026-10-14", at - datetime.timedelta(seconds=1))
    assert epochs.read_by_value("2026-10-14", at)


def test_read_value_caps_a_confidence_above_its_price() -> None:
    assert read_value(leg(1, 0.80, 1.20)) == pytest.approx(0.96)
    # 0.90 at 1.50 is 0.233 above the price: read at 1/1.5 + GAP
    assert read_value(leg(1, 0.90, 1.50)) == pytest.approx(1.0 + price_gap.GAP * 1.5)
    # a measured sport carries no price_gap: its confidence as it is
    assert read_value(leg(1, 0.90, 1.50, sport="hockey")) == pytest.approx(1.35)
    assert read_value({"confidence": 0.9}) == 0.0


def test_matches_ranked_by_value_not_by_confidence() -> None:
    # 35 sure, short-priced matches (0.93 x 1.05 = 0.98) and one less sure
    # match at a fair price (0.72 x 1.40 = 1.008): first by value, last by
    # confidence
    singles = [leg(e, 0.93 - e * 0.0001, 1.05) for e in range(1, 36)]
    singles.append(leg(99, 0.72, 1.40))
    by_conf = build(singles, by_value=False)
    by_val = build(singles, by_value=True)
    assert by_conf["read_order"] == "coupon" and by_val["read_order"] == "value"
    conf_ids = {s["sofascore_event_id"] for s in legs_requiring_read(by_conf)}
    val_ids = {s["sofascore_event_id"] for s in legs_requiring_read(by_val)}
    assert 99 not in conf_ids and 99 in val_ids
    assert len(val_ids) == READ_REQUIRED_EVENTS
    # every leg still prints, in the same coupon order
    assert [s["position"] for s in by_conf["singles"]] == [s["position"] for s in by_val["singles"]]
