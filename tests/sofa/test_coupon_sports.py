"""F7 (plan 2026-10-05): the measured sports' legs on the one coupon."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from bet.sofa import coupon_sports as cs
from bet.sofa.contracts import LegRead
from bet.sofa.locked_print import leg_key
from scripts.sofa.build_coupon import assemble


def _sport_leg(**extra: Any) -> dict[str, Any]:
    leg = {
        "sport": "hockey", "group_key": "sofa:900", "sofascore_event_id": 900,
        "superbet_event_id": "sb9", "market_id": 623, "family": "total",
        "period": 0, "subject": "", "line": 5.5, "side": "OVER",
        "confidence": 0.84, "calibrated_on": "hockey:total|OVER",
        "calibration_n": 3000, "sample_hit_rate": 0.7, "sample_k": 7,
        "sample_n": 10, "forecast_p": 0.86, "forecast_source": "score_model",
        "odds": 1.15, "x": 0.966, "overround": 0.06,
        "kickoff_utc": "2026-10-07T18:00:00Z", "source_date": "2026-10-07",
        "price_fetched_at_utc": "2026-10-07T09:00:00Z", "match": "A - B",
        "competition": "NHL",
    }
    leg.update(extra)
    return leg


def test_a_sport_leg_gets_the_readers_names_and_keeps_its_own():
    leg = cs.normalize(_sport_leg())
    assert (leg["market"], leg["direction"], leg["offered_odds"]) == (
        "total", "OVER", 1.15)
    assert leg["leg_ev"] == round(0.84 * 1.15 - 1, 4)
    assert leg["family"] == "total" and leg["side"] == "OVER"
    # a winner leg has no line; the shared key still works
    winner = cs.normalize(_sport_leg(family="winner", line=None, side="T1"))
    assert leg_key(winner)[3] is None


def test_a_watch_on_a_sport_leg_removes_it_and_a_period_read_covers_only_its_period():
    full = cs.normalize(_sport_leg())
    p1 = cs.normalize(_sport_leg(period=1))
    read = LegRead(sofascore_event_id=900, market="total", subject=None, line=5.5,
                   direction="OVER", verdict="WATCH", author="analyst",
                   reason="goalie out", period=1)
    kept, removed, vetoed = cs.apply_reads([full, p1], [], [read])
    assert [x["period"] for x in kept] == [0]
    assert [(x["period"], x["refusal"], x["reason"]) for x in removed] == [
        (1, "WATCHED", "analyst")]
    assert vetoed == 0


def test_a_read_accepts_a_sport_side_and_refuses_nonsense():
    import pytest
    from pydantic import ValidationError

    for side in ("T1", "DRAW", "ODD", "YES", "3:1"):
        LegRead(sofascore_event_id=1, market="winner", subject=None, line=None,
                direction=side, verdict="KEEP", author="analyst", reason="r")
    with pytest.raises(ValidationError):
        LegRead(sofascore_event_id=1, market="winner", subject=None, line=None,
                direction="SIDEWAYS", verdict="KEEP", author="analyst", reason="r")


def test_a_started_printed_sport_leg_is_locked_and_a_future_one_is_not():
    printed = {"profile": "standard", "epoch": "stats_only",
               "created_at_utc": "2026-10-07T09:00:00Z",
               "pdf_rendered_at_utc": "2026-10-07T09:01:00Z",
               "singles": [cs.normalize(_sport_leg(position=3, block=2)),
                           cs.normalize(_sport_leg(sofascore_event_id=901,
                                                   kickoff_utc="2026-10-07T23:00:00Z"))]}
    now = datetime(2026, 10, 7, 17, 50, tzinfo=UTC)
    locked = cs.locked_sport_legs(printed, now)
    assert [x["sofascore_event_id"] for x in locked] == [900]
    assert locked[0]["locked"] and "position" not in locked[0]
    assert locked[0]["printed_at_utc"] == "2026-10-07T09:01:00Z"
    assert locked[0]["printed_under"]["epoch"] == "stats_only"


def test_grading_refuses_a_record_settled_under_another_id(tmp_path):
    import json

    run = tmp_path / "2026-10-07"
    run.mkdir()
    (run / cs.SPORT_FIXTURES_FILE).write_text(json.dumps({"fixtures": [
        {"superbet_event_id": "sb9", "sofascore_event_id": 900,
         "status": "IDENTIFIED"}]}))
    settled = {"2026-10-07": {"events": {"sb9": {
        "state": "SETTLED", "sofascore_event_id": 12345,
        "t1_periods": [3, 2, 1], "t2_periods": [0, 1, 0], "t1_full": 6,
        "t2_full": 1, "winner": "T1", "overtime": False}}}}
    graded = cs.grade(str(tmp_path), "2026-10-07", [cs.normalize(_sport_leg())],
                      datetime(2026, 10, 8, tzinfo=UTC),
                      load=lambda rd, sport, dates: settled)
    assert graded[0]["outcome"] == "NOT_GRADED:ID_CHANGED"
    settled["2026-10-07"]["events"]["sb9"]["sofascore_event_id"] = 900
    graded = cs.grade(str(tmp_path), "2026-10-07", [cs.normalize(_sport_leg())],
                      datetime(2026, 10, 8, tzinfo=UTC),
                      load=lambda rd, sport, dates: settled)
    assert graded[0]["outcome"] == "WIN"  # 7 goals over 5.5


def test_the_coupon_orders_both_sources_together():
    football = {"sofascore_event_id": 1, "confidence": 0.80, "market": "goals_total",
                "subject": "", "line": 2.5, "direction": "UNDER",
                "kickoff_utc": "2026-10-07T12:00:00Z", "offered_odds": 1.2,
                "match": "F1", "epoch": "stats_only"}
    conf = {"profile": "standard", "epoch": "stats_only", "created_at_utc": "x",
            "singles": [football], "legs": [football], "builders": []}
    sports = {"created_at_utc": "y", "legs": [cs.normalize(_sport_leg())],
              "removed_by_reads": [{"sofascore_event_id": 5}]}
    doc = assemble(conf, sports, [], {}, "now", "2026-10-07")
    assert [(s["position"], s["sofascore_event_id"]) for s in doc["singles"]] == [
        (1, 900), (2, 1)]
    assert doc["built_from"]["08_confidence_sports.json"] == "y"
    assert doc["removed_by_reads"] == [{"sofascore_event_id": 5}]
