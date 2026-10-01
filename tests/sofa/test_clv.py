"""Closing line value (bet.sofa.clv, capture_closing.py, audit_clv.py).

The measurement practitioners rank first and sofa did not have: was the
printed price better than the close? These tests pin the arithmetic, that a
close is only a price taken shortly before the start, that legs of one match
are resampled together, and that the capture reads the same rung the leg was
printed from.
"""

import json
from datetime import UTC, datetime, timedelta

import pytest

from bet.sofa import clv
from bet.sofa.contracts import FixtureOffer, PricedRung
from scripts.sofa import capture_closing as cc


def test_clv_is_the_return_at_the_closing_probability():
    r = clv.ClvRow("official", "1", "x", odds_taken=2.10, odds_close=1.90, p_close=0.5)
    assert r.clv_ev == pytest.approx(0.05) and r.beat
    worse = clv.ClvRow("official", "1", "x", 1.80, 1.90, 0.5)
    assert worse.clv_ev == pytest.approx(-0.10) and not worse.beat


def test_a_close_is_a_price_shortly_before_the_start():
    assert clv.is_close(12)
    assert not clv.is_close(1) and not clv.is_close(240) and not clv.is_close(None)


def test_the_interval_resamples_matches_not_legs():
    rows = [clv.ClvRow("v", "a", str(i), 2.0, 2.0, 0.6) for i in range(10)]
    rows += [clv.ClvRow("v", "b", "z", 2.0, 2.0, 0.4)]
    s = clv.summarize(rows, "v", n_boot=300)
    assert s is not None and s.games == 2 and s.legs == 11
    assert s.ci95[0] <= -0.2 + 1e-9 and s.ci95[1] >= 0.2 - 1e-9


def test_sport_coupon_legs_match_their_graded_close():
    keys = ("superbet_event_id", "market_id", "period", "subject", "line", "side")
    leg = {"superbet_event_id": "9", "market_id": 1, "period": 0, "subject": "",
           "line": 5.5, "side": "OVER", "odds": 1.95, "label": "total"}
    graded = [{**{k: leg[k] for k in keys}, "odds": 1.80, "partner_odds": 2.0,
               "minutes_before_kickoff": 10}]
    rows = clv.sport_coupon_rows({"legs": [leg]}, graded, "sport:hockey", keys)
    assert len(rows) == 1 and rows[0].odds_close == 1.80 and rows[0].beat
    stale = [{**graded[0], "minutes_before_kickoff": 300}]
    assert clv.sport_coupon_rows({"legs": [leg]}, stale, "sport:hockey", keys) == []


def _leg(minutes, now):
    return {"sofascore_event_id": 7, "market": "goals_total", "subject": "",
            "line": 2.5, "direction": "OVER", "offered_odds": 1.90,
            "kickoff_utc": (now + timedelta(minutes=minutes)).isoformat()}


def test_the_capture_reads_the_printed_rung_and_its_partner():
    now = datetime(2026, 10, 1, 12, tzinfo=UTC)
    offer = FixtureOffer(sofascore_event_id=7, status="PRICED", unmapped_markets=[],
                         rungs=[PricedRung(market="goals_total", subject="", line=2.5,
                                           over_odds=1.80, under_odds=2.05,
                                           fetched_at_utc=now)])
    rec = cc.close_record("official", _leg(10, now), offer, now)
    assert rec is not None and rec["odds_close"] == 1.80
    assert rec["partner_close"] == 2.05 and rec["minutes_before"] == 10.0
    assert cc.due([("official", _leg(10, now)), ("official", _leg(90, now))], now) == [
        ("official", _leg(10, now))]


def test_audit_reads_the_latest_close_per_leg(tmp_path):
    from scripts.sofa.audit_clv import closing_rows

    day = tmp_path / "2026-10-01"
    day.mkdir()
    recs = [
        {"variant": "official", "leg_key": "k", "sofascore_event_id": 7,
         "odds_taken": 1.9, "odds_close": 1.85, "partner_close": 2.0,
         "fetched_at_utc": "2026-10-01T11:40:00", "minutes_before": 20},
        {"variant": "official", "leg_key": "k", "sofascore_event_id": 7,
         "odds_taken": 1.9, "odds_close": 1.75, "partner_close": 2.15,
         "fetched_at_utc": "2026-10-01T11:50:00", "minutes_before": 10},
    ]
    (day / "closing.jsonl").write_text("".join(json.dumps(r) + "\n" for r in recs))
    rows = closing_rows(tmp_path, "2026-10-01")
    assert len(rows) == 1 and rows[0].odds_close == 1.75
