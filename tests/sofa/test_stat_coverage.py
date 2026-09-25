"""The /statistics counts Superbet prices, end to end (2026-09-25 coverage audit).

Second halves of fouls / shots / shots on target, offsides by half, goalkeeper
saves, throw-ins, goal kicks and tackles. Every one was in the cached
/statistics payload and on the Superbet board, and nothing connected them.
The chain is: Superbet name -> classify_market -> extract_metric (SAMPLES and
SETTLE both read it) -> SHEET row -> cache replay (baselines and the confidence
curve) -> CONFIDENCE quantity family.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from bet.sofa.confidence import quantity_family
from bet.sofa.config import SofaConfig
from bet.sofa.contracts import GapReason
from bet.sofa.db import migrate
from bet.sofa.market_mapper import (
    MATCH_MARKET_NAMES,
    TEAM_MARKET_PATTERNS,
    classify_market,
)
from bet.sofa.metrics import (
    FOOTBALL_METRICS,
    ZERO_MEANS_UNTRACKED,
    extract_flat_statistics,
    extract_metric,
    stat_is_untracked,
)
from scripts.sofa.calibrate_from_cache import load_cache
from scripts.sofa.run_sheet import process_fixture
from tests.sofa.test_sheet import make_fixture, make_offer, make_samples, rung

NEW_METRICS = [
    f"{base}_{suffix}"
    for base in (
        "fouls_2h", "shots_2h", "shots_on_target_2h", "offsides_1h",
        "offsides_2h", "saves", "saves_1h", "throw_ins", "throw_ins_1h",
        "throw_ins_2h", "goal_kicks", "goal_kicks_1h", "goal_kicks_2h", "tackles",
    )
    for suffix in ("total", "for")
]

# Folded strings as the 2026-09-22..25 boards carried them, one per shape.
BOARD_NAMES = [
    ("2. połowa - liczba fauli", "fouls_2h_total", ""),
    ("2. połowa - Grecja liczba fauli", "fouls_2h_for", "grecja"),
    ("2. połowa - liczba strzałów", "shots_2h_total", ""),
    ("2. połowa - Serbia liczba strzałów", "shots_2h_for", "serbia"),
    ("2. połowa - liczba celnych strzałów", "shots_on_target_2h_total", ""),
    ("2. połowa - Dania liczba celnych strzałów", "shots_on_target_2h_for", "dania"),
    ("1. połowa - liczba spalonych", "offsides_1h_total", ""),
    ("1. połowa - Serbia liczba spalonych", "offsides_1h_for", "serbia"),
    ("2. połowa - liczba spalonych", "offsides_2h_total", ""),
    ("2. połowa - Niemcy liczba spalonych", "offsides_2h_for", "niemcy"),
    ("Liczba obronionych strzałów przez bramkarza", "saves_total", ""),
    ("Grecja - liczba obronionych strzałów przez bramkarza", "saves_for", "grecja"),
    ("1. połowa - liczba obronionych strzałów przez bramkarza", "saves_1h_total", ""),
    ("1. połowa - Serbia - liczba obronionych strzałów przez bramkarza",
     "saves_1h_for", "serbia"),
    ("Liczba rzutów z autu", "throw_ins_total", ""),
    ("Liczba rzutów z autu - Holandia", "throw_ins_for", "holandia"),
    ("1. połowa - liczba rzutów z autu", "throw_ins_1h_total", ""),
    ("1. połowa - Norwegia liczba rzutów z autu", "throw_ins_1h_for", "norwegia"),
    ("2. połowa - liczba rzutów z autu", "throw_ins_2h_total", ""),
    ("2. połowa - Niemcy liczba rzutów z autu", "throw_ins_2h_for", "niemcy"),
    ("Liczba wybić od bramki", "goal_kicks_total", ""),
    ("Liczba wybić z bramki Niemcy", "goal_kicks_for", "niemcy"),
    ("1. połowa - liczba wybić od bramki", "goal_kicks_1h_total", ""),
    ("2. połowa - liczba wybić od bramki", "goal_kicks_2h_total", ""),
    ("Liczba odbiorów", "tackles_total", ""),
    ("Dania - liczba odbiorów", "tackles_for", "dania"),
]


def _stats(periods: dict[str, dict[str, tuple[float, float]]]) -> dict[str, Any]:
    return {"statistics": [
        {"period": period, "groups": [{"groupName": "g", "statisticsItems": [
            {"key": k, "homeValue": h, "awayValue": a} for k, (h, a) in items.items()
        ]}]}
        for period, items in periods.items()
    ]}


@pytest.mark.parametrize(("name", "metric", "subject"), BOARD_NAMES)
def test_board_names_classify(name: str, metric: str, subject: str) -> None:
    assert classify_market(name) == (metric, subject)


def test_every_new_metric_is_declared_and_reachable_from_a_name() -> None:
    reachable = set(MATCH_MARKET_NAMES.values()) | {m for _, m in TEAM_MARKET_PATTERNS}
    for metric in NEW_METRICS:
        assert metric in FOOTBALL_METRICS, metric
    # goal_kicks by half has no per-team market on any board seen.
    unreachable = {m for m in NEW_METRICS if m not in reachable}
    assert unreachable == {"goal_kicks_1h_for", "goal_kicks_2h_for"}


def test_half_cards_stay_refused() -> None:
    # metrics.py: a second yellow spanning the halves is a modelling question.
    assert classify_market("1. połowa - liczba kartek") is None


def test_extract_reads_each_period_and_both_sides() -> None:
    flat = extract_flat_statistics(_stats({
        "ALL": {"throwIns": (22, 18), "goalkeeperSaves": (3, 5), "fouls": (12, 9)},
        "1ST": {"throwIns": (10, 8), "goalkeeperSaves": (1, 2), "fouls": (5, 4)},
        "2ND": {"throwIns": (12, 10), "goalkeeperSaves": (2, 3), "fouls": (7, 5)},
    }))
    ev: dict[str, Any] = {}
    assert extract_metric("throw_ins_total", "football", flat, None, ev, True) == 40.0
    assert extract_metric("throw_ins_for", "football", flat, None, ev, False) == 18.0
    assert extract_metric("throw_ins_2h_for", "football", flat, None, ev, True) == 12.0
    assert extract_metric("saves_1h_total", "football", flat, None, ev, True) == 3.0
    assert extract_metric("fouls_2h_for", "football", flat, None, ev, False) == 5.0


def test_a_missing_key_is_a_gap_not_a_zero() -> None:
    flat = extract_flat_statistics(_stats({"ALL": {"fouls": (12, 9)}}))
    got = extract_metric("saves_for", "football", flat, None, {}, True)
    assert got == GapReason.STAT_KEY_ABSENT


def test_halves_that_do_not_sum_to_the_match_are_refused() -> None:
    flat = extract_flat_statistics(_stats({
        "ALL": {"offsides": (3, 2)}, "1ST": {"offsides": (1, 1)},
        "2ND": {"offsides": (1, 1)},
    }))
    got = extract_metric("offsides_2h_for", "football", flat, None, {}, True)
    assert got == GapReason.INTERNAL_INCONSISTENT


@pytest.mark.parametrize(
    ("key", "pair", "untracked"),
    [
        ("throwIns", (0, 0), True), ("throwIns", (0, 21), True),
        ("totalTackle", (14, 0), True), ("goalKicks", (0, 0), True),
        ("goalKicks", (0, 9), False), ("goalkeeperSaves", (0, 0), False),
        ("throwIns", (20, 18), False),
    ],
)
def test_placeholder_zeros(
    key: str, pair: tuple[float, float], untracked: bool
) -> None:
    assert stat_is_untracked(key, pair) is untracked


def test_a_placeholder_match_yields_no_observation_in_any_period() -> None:
    assert set(ZERO_MEANS_UNTRACKED) == {"throwIns", "totalTackle", "goalKicks"}
    flat = extract_flat_statistics(_stats({
        "ALL": {"throwIns": (0, 0), "totalTackle": (0, 0)},
        "1ST": {"throwIns": (0, 0)}, "2ND": {"throwIns": (0, 0)},
    }))
    for metric in ("throw_ins_total", "throw_ins_1h_for", "tackles_for"):
        got = extract_metric(metric, "football", flat, None, {}, True)
        assert got == GapReason.NO_STATISTICS, metric


def test_sheet_prices_a_new_metric() -> None:
    samples = make_samples("throw_ins_total", [40, 42, 38, 44, 41, 39, 43, 40, 42, 41],
                           [38, 40, 41, 39, 42, 40, 37, 43, 41, 40])
    offer = make_offer([rung(39.5, 1.85, 1.95, market="throw_ins_total"),
                        rung(41.5, 2.10, 1.70, market="throw_ins_total")])
    rows, _ = process_fixture(make_fixture(), samples, offer, baselines={},
                              reliability={}, engine_constants={}, vetoes=[],
                              config=SofaConfig())
    assert {r.line for r in rows} == {39.5, 41.5}
    assert all(r.market == "throw_ins_total" for r in rows)


def test_quantity_families_keep_correlated_counts_together() -> None:
    assert quantity_family("saves_for") == quantity_family("shots_on_target_for")
    assert quantity_family("goal_kicks_total") == quantity_family("shots_total")
    assert quantity_family("throw_ins_1h_for") == "throw_ins"
    assert quantity_family("tackles_total") == "tackles"
    assert quantity_family("fouls_2h_for") == quantity_family("fouls_total")


def test_cache_replay_carries_the_new_bases_and_refuses_placeholders(
    tmp_path: Path,
) -> None:
    db = tmp_path / "sofa.db"
    migrate(str(db))

    def event(eid: int) -> dict[str, Any]:
        return {"id": eid, "status": {"type": "finished"},
                "startTimestamp": 1_000 + eid,
                "homeTeam": {"id": 1}, "awayTeam": {"id": 2},
                "homeScore": {"current": 1}, "awayScore": {"current": 0},
                "tournament": {"uniqueTournament": {"id": 17},
                               "category": {"sport": {"slug": "football"}}}}

    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO sofa_entity_events VALUES (1, 'last', 0, 'x', ?)",
                 (json.dumps({"events": [event(10), event(11)]}),))
    tracked = {"ALL": {"throwIns": (21, 19), "goalKicks": (7, 9),
                       "totalTackle": (15, 12), "goalkeeperSaves": (2, 4)}}
    placeholder = {"ALL": {"throwIns": (0, 0), "goalKicks": (0, 0),
                           "totalTackle": (0, 11), "goalkeeperSaves": (0, 0)}}
    for eid, periods in ((10, tracked), (11, placeholder)):
        conn.execute(
            "INSERT INTO sofa_event_stats (sofascore_event_id, fetched_at, "
            "statistics_json, incidents_json, status_type) VALUES (?, 'x', ?, NULL, "
            "'finished')", (eid, json.dumps(_stats(periods))))
    conn.commit()
    conn.close()

    played = {p.event_id: p.values for p in load_cache(db)}
    assert played[10]["throw_ins"] == (21.0, 19.0)
    assert played[10]["goal_kicks"] == (7.0, 9.0)
    assert played[10]["tackles"] == (15.0, 12.0)
    assert played[10]["saves"] == (2.0, 4.0)
    assert "throw_ins" not in played[11]
    assert "goal_kicks" not in played[11]
    assert "tackles" not in played[11]
    # A goalkeeper can make no save: a real zero stays a zero.
    assert played[11]["saves"] == (0.0, 0.0)


def test_a_new_metric_cannot_borrow_the_pool_until_it_has_its_own_curve() -> None:
    from bet.sofa.confidence import AWAITING_OWN_CURVE, Calibration

    assert set(NEW_METRICS) == set(AWAITING_OWN_CURVE)
    pool = {"0.60-0.70": {"realised_lo95": 0.66, "n": 5000}}
    cal = Calibration(pooled=pool, by_market={}, pooled_by_sport={"football": pool})
    assert cal.realised("throw_ins_total", 0.65, "football") is None
    # An established market still reads the pool for a thin bucket.
    got = cal.realised("corners_total", 0.65, "football")
    assert got is not None and got[0] == 0.66
    # Once the market is fitted, its own curve is read.
    own = {"throw_ins_total": {"0.60-0.70": {"realised_lo95": 0.61, "n": 300}}}
    cal = Calibration(pooled=pool, by_market=own, pooled_by_sport={"football": pool})
    assert cal.realised("throw_ins_total", 0.65, "football") == (
        0.61, "market:throw_ins_total", 300)


@pytest.mark.parametrize("name", [
    "Zawodnik - liczba odbiorów",
    "Liczba rzutów z autu - handicap",
    "Liczba rzutów z autu - H2H",
    "Liczba rzutów z autu - remis",
    "Liczba rzutów z autu - kto wykona więcej",
    "Liczba wybić z bramki - handicap",
    "Liczba fauli - H2H",
])
def test_a_market_variant_or_a_player_is_not_a_team(name: str) -> None:
    assert classify_market(name) is None


def test_second_half_most_markets_are_derived_and_never_reach_confidence() -> None:
    # Declaring fouls_2h_for / shots_2h_for / shots_on_target_2h_for switches
    # these on in _scope_metric. Accepted on purpose: they are derived, so
    # CONFIDENCE refuses them (DERIVED_NOT_CALIBRATABLE).
    from bet.sofa.confidence import is_derived
    from bet.sofa.market_mapper import classify_derived_market

    for name, market in (("2. połowa - najwięcej fauli", "most_fouls_2h"),
                         ("2. połowa - najwięcej strzałów", "most_shots_2h")):
        got = classify_derived_market(name, "1", None)
        assert got is not None and got[0] == market, (name, got)
        assert is_derived(market)


def test_mechanism_families_for_the_coupon() -> None:
    from bet.sofa.market_mapper import get_mechanism_family

    assert get_mechanism_family("saves_1h_for") == get_mechanism_family("shots_for")
    assert get_mechanism_family("goal_kicks_total") == "attacking"
    assert get_mechanism_family("fouls_2h_for") == get_mechanism_family("fouls_for")


def test_half_coherence_check_sees_bases_with_an_underscore() -> None:
    from scripts.sofa.fit_constants import check_half_match_coherence, half_name

    assert half_name("throw_ins_total", "1h") == "throw_ins_1h_total"
    assert half_name("shots_on_target_for", "2h") == "shots_on_target_2h_for"
    broken = {
        "throw_ins_total": {"global": {"mean": 40.0, "n": 500}},
        "throw_ins_1h_total": {"global": {"mean": 10.0, "n": 500}},
        "throw_ins_2h_total": {"global": {"mean": 40.0, "n": 500}},
    }
    assert check_half_match_coherence(broken)
