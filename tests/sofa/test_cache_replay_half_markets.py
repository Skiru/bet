"""The cache replay settles the football per-half markets (2026-10-04).

Until then match_values read the ALL period only, so a per-half market's
confidence curve came from live SETTLE alone and, where a bucket fell under
MIN_MARKET_BUCKET, CONFIDENCE read the football pool (goals_1h_total UNDER at
0.80-0.85 printed 0.815 / 0.841 from pooled:football on 2026-10-03). Each half
value is read with metrics.extract_metric - what SAMPLES and SETTLE read.
"""

from __future__ import annotations

import json
from typing import Any

from bet.sofa.metrics import FOOTBALL_METRICS
from scripts.sofa.calibrate_from_cache import (
    HALF_BASES,
    MIN_SAMPLE,
    Played,
    build,
    half_values,
    market_name,
    match_values,
)


def _event(h1: int, a1: int, h2: int, a2: int, code: int = 100) -> dict[str, Any]:
    return {
        "id": 1,
        "status": {"type": "finished", "code": code},
        "homeScore": {"current": h1 + h2, "normaltime": h1 + h2,
                      "period1": h1, "period2": h2},
        "awayScore": {"current": a1 + a2, "normaltime": a1 + a2,
                      "period1": a1, "period2": a2},
    }


def _stats(periods: dict[str, dict[str, tuple[float, float]]]) -> str:
    return json.dumps({"statistics": [
        {"period": period, "groups": [{"statisticsItems": [
            {"key": k, "homeValue": h, "awayValue": a} for k, (h, a) in items.items()
        ]}]}
        for period, items in periods.items()
    ]})


def test_half_bases_are_every_football_half_metric() -> None:
    halves = {m for m in FOOTBALL_METRICS if "_1h_" in m or "_2h_" in m}
    assert {market_name(b, s) for b in HALF_BASES for s in ("for", "total")} == halves


def test_goals_halves_come_off_the_listing() -> None:
    values = match_values(_event(1, 0, 2, 1), "football", None, None)
    assert values["goals"] == (3.0, 1.0)
    assert values["goals_1h"] == (1.0, 0.0)
    assert values["goals_2h"] == (2.0, 1.0)


def test_stat_halves_come_off_their_period() -> None:
    stats = _stats({
        "ALL": {"cornerKicks": (5, 7), "fouls": (10, 12)},
        "1ST": {"cornerKicks": (2, 2), "fouls": (4, 6)},
        "2ND": {"cornerKicks": (3, 5), "fouls": (6, 6)},
    })
    values = match_values(_event(0, 0, 0, 0), "football", stats, None)
    assert values["corners"] == (5.0, 7.0)
    assert values["corners_1h"] == (2.0, 2.0)
    assert values["corners_2h"] == (3.0, 5.0)
    assert values["fouls_1h"] == (4.0, 6.0)
    assert values["fouls_2h"] == (6.0, 6.0)
    assert "shots_1h" not in values  # not reported: absent, never zero


def test_a_half_that_does_not_add_up_is_refused() -> None:
    stats = _stats({
        "ALL": {"cornerKicks": (5, 7)},
        "1ST": {"cornerKicks": (2, 2)},
        "2ND": {"cornerKicks": (2, 5)},  # 2 + 2 != 5
    })
    values = match_values(_event(0, 0, 0, 0), "football", stats, None)
    assert "corners_1h" not in values and "corners_2h" not in values
    assert values["corners"] == (5.0, 7.0)


def test_a_negative_corrected_half_score_is_refused() -> None:
    event = _event(5, 0, -5, 0)
    values = half_values(event, {})
    assert "goals_1h" in values  # period1 itself is a count
    assert "goals_2h" not in values


def test_extra_time_keeps_goal_halves_and_drops_stat_halves() -> None:
    stats = _stats({
        "ALL": {"cornerKicks": (5, 7)},
        "1ST": {"cornerKicks": (2, 2)},
        "2ND": {"cornerKicks": (3, 5)},
    })
    values = match_values(_event(1, 1, 0, 0, code=110), "football", stats, None)
    assert values["goals_1h"] == (1.0, 1.0)
    assert "corners_1h" not in values


def test_tennis_gets_no_football_halves() -> None:
    values = match_values(_event(6, 4, 6, 3), "tennis", None, None)
    assert not any(b in values for b in HALF_BASES)


def test_replay_settles_goals_1h_total_rows() -> None:
    played = []
    ts = 1_000
    for i in range(MIN_SAMPLE + 1):
        played.append(Played(i, ts + i, 1, 100 + i, "football", 17,
                             {"goals_1h": (float(i % 2), 0.0)}))
        played.append(Played(1000 + i, ts + i, 200 + i, 2, "football", 17,
                             {"goals_1h": (0.0, float(i % 3 == 0))}))
    played.append(
        Played(9999, ts + 100, 1, 2, "football", 17, {"goals_1h": (0.0, 1.0)}))
    rows = [r for r in build(played, {}) if r.event_id == 9999]
    markets = {r.market for r in rows}
    assert markets == {"goals_1h_for", "goals_1h_total"}
    under = [r for r in rows if r.market == "goals_1h_total" and r.direction == "UNDER"
             and r.line == 1.5]
    assert len(under) == 1 and under[0].outcome == "WIN" and under[0].actual == 1.0
