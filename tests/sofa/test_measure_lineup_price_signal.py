"""Offline tests of the read-only lineup / price measurement
(scripts/sofa/measure_lineup_price_signal.py)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from scripts.sofa import measure_lineup_price_signal as m


def _side(xi: list[int], shots: dict[int, float]) -> m.SideLineup:
    return m.SideLineup(frozenset(xi), dict(shots), {p: f"P{p}" for p in xi})


def _lineups(home_xi: list[int]) -> dict[str, object]:
    players = [{"player": {"id": p, "name": f"P{p}"}, "substitute": False,
                "statistics": {"totalShots": 1}} for p in home_xi]
    players.append({"player": {"id": 99, "name": "Bench"}, "substitute": True,
                    "statistics": {"onTargetScoringAttempt": 1, "shotOffTarget": 2}})
    return {"home": {"players": players}, "away": {"players": players[:5]}}


def test_side_lineup_needs_eleven_starters() -> None:
    lu = _lineups(list(range(1, 12)))
    home = m.side_lineup(lu, "home")
    assert home is not None and len(home.xi) == 11
    assert home.shots[99] == 3.0  # parts summed without totalShots
    assert m.side_lineup(lu, "away") is None


def test_top_shooter_needs_starts_and_share() -> None:
    xi = list(range(1, 12))
    hist = [_side(xi, {1: 4.0, 2: 1.0, 3: 1.0}) for _ in range(5)]
    assert m.top_shooter(hist) == (1, pytest.approx(4 / 6))
    # four starts only: not a regular
    short = hist[:4]
    assert m.top_shooter(short) is None
    flat = [_side(xi, {p: 1.0 for p in xi}) for _ in range(5)]
    assert m.top_shooter(flat) is None  # 1/11 below MIN_TOP_SHARE


def test_core_missing_counts_regulars_not_in_xi() -> None:
    xi = list(range(1, 12))
    hist = [_side(xi, {}) for _ in range(10)]
    today = frozenset([*range(3, 12), 20, 21])
    assert m.core_missing(hist, today) == 2
    assert m.core_missing([], today) == 0


def test_devig_and_family() -> None:
    assert m.devig(2.0, 2.0) == pytest.approx(0.5)
    assert m.devig(1.5, 2.5) == pytest.approx((1 / 1.5) / (1 / 1.5 + 1 / 2.5))
    assert m.family("player_shots_for") == "PLAYER"
    assert m.family("shots_on_target_total") == "SHOTS"
    assert m.family("goals_1h_for") == "GOALS"
    assert m.family("corners_total") == "OTHER"


def test_news_direction_frozen_rule() -> None:
    nd = m.news_direction
    assert nd("goals_for", "OVER", 0, 2, None) == "FAVOURED"
    assert nd("goals_for", "UNDER", 0, 2, None) == "DISFAVOURED"
    assert nd("goals_for", "UNDER", 1, 0, None) == "FAVOURED"
    assert nd("goals_for", "OVER", 1, 0, None) == "DISFAVOURED"
    assert nd("goals_for", "OVER", 0, 0, None) == "NEUTRAL"
    assert nd("goals_for", "OVER", 1, 1, None) == "MIXED"
    assert nd("goals_total", "OVER", None, 1, None) == "TOTAL_ANY_MISSING"
    assert nd("goals_total", "OVER", None, 0, None) == "TOTAL_NONE"
    assert nd("player_shots_for", "OVER", None, None, True) == "FAVOURED"
    assert nd("player_shots_for", "OVER", None, None, False) == "NEUTRAL"
    assert nd("player_shots_for", "OVER", None, None, None) == "UNKNOWN"


def test_price_timing() -> None:
    ko = datetime(2026, 11, 5, 20, 0, tzinfo=UTC)
    assert m.price_timing(m.lead_minutes(ko, datetime(2026, 11, 5, 18, 0,
                                                      tzinfo=UTC))) == "PRE"
    assert m.price_timing(30.0) == "POST"
    assert m.price_timing(60.0) == "MID"
    assert m.price_timing(None) == "UNKNOWN"


def test_bh() -> None:
    assert m.bh([0.01, 0.04, 0.5]) == [True, True, False]
    assert m.bh([0.2, 0.5]) == [False, False]


def test_leg_metrics_tax() -> None:
    r = m.leg_metrics({"event": 1, "day": "d", "odds": 2.0, "outcome": "WIN",
                       "confidence": 0.6})
    assert r["roi"] == pytest.approx(1.0)
    assert r["roi_tax"] == pytest.approx(2.0 * 0.88 - 1)
    assert r["res_minus_implied"] == pytest.approx(0.5)
    assert r["res_minus_conf"] == pytest.approx(0.4)
    lost = m.leg_metrics({"event": 1, "day": "d", "odds": 2.0, "outcome": "LOSS"})
    assert lost["roi_tax"] == -1.0 and lost["res_minus_conf"] is None


def test_bootstrap_by_match_and_diff() -> None:
    rows = []
    for e in range(40):
        grp = "A" if e % 2 else "B"
        for _ in range(3):
            rows.append({"event": e, "x": 1.0 if grp == "A" else 0.0, "g": grp})
    d = m.diff_of(m.mean_of("x", lambda r: r["g"] == "A"),
                  m.mean_of("x", lambda r: r["g"] == "B"))
    out = m.bootstrap(rows, d, reps=200)
    assert out["point"] == pytest.approx(1.0)
    assert out["matches"] == 40 and out["n"] == 120
    assert out["lo"] == pytest.approx(1.0) and out["p"] == 0.0
    single = m.bootstrap(rows[:3], m.mean_of("x"), reps=50)
    assert single["lo"] is None  # one match: no interval
