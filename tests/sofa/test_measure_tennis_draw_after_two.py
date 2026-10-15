"""measure_tennis_draw_after_two: the last pre-start Superbet price, the 1:1
settlement from point-by-point, the as-of forecast. Offline, synthetic."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from scripts.sofa.measure_tennis_draw_after_two import (
    MARKET,
    SELECTION,
    forecasts,
    last_prematch,
    outcome,
    p_draw,
    summarise,
)

START = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)


def rec(at: str, price: float, eid: int = 1, **kw: Any) -> dict[str, Any]:
    r: dict[str, Any] = {"sofascore_event_id": eid, "superbet_event_id": "9",
                         "fetched_at_utc": at, "marketName": MARKET, "name": SELECTION,
                         "price": price, "status": "active", "offerStateId": 1}
    r.update(kw)
    return r


def test_last_price_before_the_start_only() -> None:
    records = [
        rec("2026-10-14T10:00:00Z", 1.70),
        rec("2026-10-14T11:30:00Z", 1.65),
        rec("2026-10-14T12:05:00Z", 1.50),  # after the start: in play
        rec("2026-10-14T11:50:00Z", 1.40, offerStateId=2),  # live offer state
        rec("2026-10-14T11:55:00Z", 1.30, name="po 2 - Jan Kowalski"),
        rec("2026-10-14T11:56:00Z", 1.20, eid=2),  # no start clock
    ]
    quotes, dropped = last_prematch(records, {1: START})
    assert set(quotes) == {1}
    assert quotes[1].price == 1.65
    assert dropped == 2


def pbp_payload(set1: list[tuple[int, int, int]]) -> dict[str, Any]:
    """set1: (server, winner, ...) per game in play order."""
    games, h, a = [], 0, 0
    for i, (server, winner, _) in enumerate(set1, start=1):
        h, a = h + (winner == 1), a + (winner == 2)
        games.append({"game": i, "score": {"serving": server, "scoring": winner,
                                           "homeScore": h, "awayScore": a}})
    return {"pointByPoint": [{"set": 1, "games": list(reversed(games))}]}


def event(code: int, kind: str, p1: tuple[int, int] | None = None) -> dict[str, Any]:
    ev: dict[str, Any] = {"status": {"code": code, "type": kind}}
    if p1:
        ev["homeScore"], ev["awayScore"] = {"period1": p1[0]}, {"period1": p1[1]}
    return ev


def test_both_broken_is_a_draw_and_two_love_is_not() -> None:
    broken = pbp_payload([(1, 2, 0), (2, 1, 0), (1, 1, 0)])
    assert outcome(event(100, "finished", (2, 1)), broken).won == 1
    held = pbp_payload([(1, 1, 0), (2, 2, 0)])
    assert outcome(event(100, "finished", (1, 1)), held).won == 1
    lead = pbp_payload([(1, 1, 0), (2, 1, 0)])
    assert outcome(event(100, "finished", (2, 0)), lead).won == 0


def test_void_pending_and_data_gaps() -> None:
    two = pbp_payload([(1, 1, 0), (2, 2, 0)])
    assert outcome(event(92, "finished"), None).reason == "RETIRED"
    assert outcome(event(92, "finished"), two).reason == "RETIRED_AFTER_2"
    assert outcome(event(91, "finished"), None).status == "VOID"
    assert outcome(event(70, "canceled"), None).status == "VOID"
    assert outcome(event(8, "inprogress"), two).status == "PENDING"
    assert outcome(event(100, "finished"), None).status == "NOT_FOUND"
    assert outcome(None, two).status == "NOT_FOUND"
    assert outcome(event(100, "finished", (6, 4)), two).status == "MISMATCH"


def test_draw_probability_counts_both_breaks() -> None:
    assert abs(p_draw(0.8, 0.7) - (0.56 + 0.06)) < 1e-12
    assert p_draw(0.5, 0.5) == 0.5


def test_forecast_reads_only_earlier_matches() -> None:
    strong = [10, 10, 70, 30]  # sgw, sgt, spw, rpw: held every game
    weak = [0, 10, 30, 10]
    ts = int(START.timestamp())
    early = [(ts - 86400 * k, 100 + k, 7, 8, strong, weak) for k in range(1, 400)]
    later = [(ts + 3600, 999, 8, 7, strong, weak)]  # after the target
    rows = sorted(early)
    a = forecasts(rows, [(ts, 1, 7, 8)], 40.0)
    b = forecasts(sorted(early + later), [(ts, 1, 7, 8)], 40.0)
    assert a == b
    ha, hb = a[1]
    assert ha > 0.9 > 0.1 > hb


def test_summary_roi_and_interval() -> None:
    items = [{"won": 1, "price": 2.0, "p_draw": 0.6, "p_both_hold": 0.5},
             {"won": 0, "price": 2.0, "p_draw": 0.6, "p_both_hold": 0.5}]
    s = summarise(items, reps=200)
    assert s["n"] == 2 and s["hits"] == 1
    assert s["roi"] == 0.0 and s["mean_implied"] == 0.5
    assert s["roi_lo"] <= 0.0 <= s["roi_hi"]
    assert summarise([], reps=10) == {"n": 0}
