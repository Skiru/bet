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
    # two matches are two pieces of evidence, not an interval
    assert s.ci95 is None
    many = [clv.ClvRow("v", f"g{g}", str(i), 2.0, 2.0, 0.6 if g % 2 else 0.4)
            for g in range(30) for i in range(1 + 9 * (g == 0))]
    s = clv.summarize(many, "v", n_boot=300)
    assert s is not None and s.games == 30 and s.legs == 39
    assert s.ci95 is not None
    # by match, the ten legs of g0 move the interval as one draw, not ten
    assert -0.2 < s.ci95[0] < s.ci95[1] < 0.2


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


def test_the_capture_reads_what_the_pdf_prints_and_builder_legs_apart(tmp_path):
    day = tmp_path
    single = {"sofascore_event_id": 1, "market": "goals_total", "subject": "",
              "line": 2.5, "direction": "OVER", "offered_odds": 1.9,
              "kickoff_utc": "2026-10-01T12:00:00Z"}
    builder = {"sofascore_event_id": 2, "kickoff_utc": "2026-10-01T13:00:00Z",
               "best_for_fixture": True, "ev_after_haircut": 0.05,
               "legs": [{"market": "corners_total", "subject": "", "line": 9.5,
                         "direction": "OVER", "odds": 1.5}]}
    doc = {"profile": "standard", "pdf_max_singles": 30, "prints_builders": True,
           "singles": [single], "builders": [builder]}
    (day / "08_confidence.json").write_text(json.dumps(doc))
    legs = cc.printed_legs(day)
    variants = sorted(v for v, _ in legs)
    assert variants == ["official", "official:builder_leg"]
    leg = next(leg for v, leg in legs if v == "official:builder_leg")
    assert leg["offered_odds"] == 1.5 and leg["sofascore_event_id"] == 2


def test_a_sport_leg_after_midnight_is_found_in_the_next_days_settle(tmp_path):
    from scripts.sofa.audit_clv import sport_rows

    leg = {"superbet_event_id": "9", "market_id": 1, "period": 0, "subject": "",
           "line": 5.5, "side": "OVER", "odds": 1.95, "label": "total",
           "kickoff_utc": "2026-10-02T01:00:00Z"}
    d1 = tmp_path / "shadow" / "hockey" / "2026-10-01"
    d2 = tmp_path / "shadow" / "hockey" / "2026-10-02"
    d1.mkdir(parents=True)
    d2.mkdir(parents=True)
    (d1 / "sport_coupon.json").write_text(json.dumps({"legs": [leg]}))
    graded = {**{k: leg[k] for k in ("superbet_event_id", "market_id", "period",
                                     "subject", "line", "side")},
              "odds": 1.80, "partner_odds": 2.0, "minutes_before_kickoff": 10}
    (d2 / "settled.json").write_text(json.dumps(
        {"events": {"9": {"graded": [graded]}}}))
    rows = sport_rows(tmp_path, "2026-10-01")
    assert len(rows) == 1 and rows[0].odds_close == 1.80



def test_a_failed_fetch_records_the_leg_as_missing_and_goes_on(tmp_path):
    now = datetime.now(UTC)
    leg = {"sofascore_event_id": 7, "market": "goals_total", "subject": "",
           "line": 2.5, "direction": "OVER", "offered_odds": 1.9,
           "kickoff_utc": (now + timedelta(minutes=10)).isoformat()}
    doc = {"profile": "standard", "pdf_max_singles": 30, "prints_builders": False,
           "singles": [leg], "builders": []}
    (tmp_path / "08_confidence.json").write_text(json.dumps(doc))
    fixture = {"sofascore_event_id": 7, "superbet_event_ids": ["1"],
               "sport": "football",
               "kickoff_utc": leg["kickoff_utc"], "home_name": "A", "away_name": "B",
               "home_entity_id": 1, "away_entity_id": 2, "competition_name": "L",
               "competition_id": 3, "season_id": 4, "category_name": "C",
               "identity": "CONFIRMED", "round_number": None, "round_name": None,
               "cup_round_type": None, "previous_leg_event_id": None,
               "venue_name": None, "referee": None, "ground_type": None,
               "default_period_count": 2}
    (tmp_path / "02_fixtures.json").write_text(json.dumps([fixture]))

    class Boom:
        def fetch_offers(self, fixtures):
            raise TimeoutError("superbet timed out")

    assert cc.run_once(tmp_path, Boom(), now) == 1
    rec = json.loads((tmp_path / "closing.jsonl").read_text().splitlines()[0])
    assert rec["missing"] is True
