"""scripts/sofa/measure_national_friendly_samples.py - pure helpers of the
national-friendly goal sample measurement (pre-registered in
docs/sofa/evidence/national_friendly_samples_2026-10-13.md)."""

from typing import Any

import pytest

from bet.sofa.count_dispersion import DispersionTable, MarketCell
from scripts.sofa.measure_national_friendly_samples import (
    AsOfPrior,
    Past,
    Target,
    before,
    in_pool,
    parse_event,
    pooled_totals,
    samples,
    score_target,
    shrunk,
    verdict,
)

DAY = 86400


def past(day: int, eid: int, comp: int | None, gf: float = 1, ga: float = 0,
         regular: bool = True) -> Past:
    return Past(day * DAY, eid, comp, regular, float(gf), float(ga))


def test_in_pool_keeps_the_two_senior_friendlies_and_drops_other_excluded():
    excluded = frozenset({851, 856})
    assert in_pool(851, excluded)
    assert in_pool(852, excluded)
    assert not in_pool(856, excluded)
    assert in_pool(10783, excluded)
    assert in_pool(None, excluded)


def test_before_is_strict_and_newest_first():
    history = [past(d, d, 1) for d in (1, 2, 3, 4)]
    got = before(history, 3 * DAY)
    assert [p.event_id for p in got] == [2, 1]


def test_samples_variants():
    # newest first: friendlies 852 on even days, competitive 290 on odd days
    pool = [past(100 - d, 100 - d, 852 if d % 2 == 0 else 290) for d in range(30)]
    s = samples(pool, 852, knockout=False)
    assert [p.competition for p in s["A"]] == [852] * 10
    assert s["B"] == pool[:10]
    oldest = min(p.ts for p in s["A"])
    assert s["C"] == [p for p in pool if p.ts >= oldest]
    assert len(s["C"]) == 19
    assert {p.competition for p in s["D"]} == {290}
    assert len(s["D"]) == 10


def test_samples_fall_back_to_b():
    pool = [past(100 - d, d, 290) for d in range(12)]
    pool[3] = past(97, 3, 852)
    s = samples(pool, 852, knockout=False)  # one friendly < minimum 5
    assert s["A"] == s["B"] == s["C"] == pool[:10]
    knock = samples([past(100 - d, d, 852) for d in range(10)], 852, knockout=True)
    assert knock["A"] == knock["B"]
    # D below the minimum competitive matches reads B
    assert knock["D"] == knock["B"]


def test_pooled_totals_counts_a_shared_match_once():
    a = [past(1, 7, 1, 2, 1), past(2, 8, 1, 0, 0)]
    b = [past(1, 7, 1, 1, 2), past(3, 9, 1, 1, 1)]
    assert pooled_totals(a, b) == [3.0, 0.0, 2.0]


def test_shrunk():
    assert shrunk([2.0, 4.0], None, 15) == pytest.approx(3.0)
    assert shrunk([2.0, 4.0], 1.0, 2) == pytest.approx(0.5 * 3 + 0.5 * 1)


def test_verdict_is_the_preregistered_rule():
    assert verdict({"t": (-1, -2, -0.1), "f": (-1, -2, -0.1)}) == "BETTER"
    assert verdict({"t": (-1, -2, -0.1), "f": (0, -1, 1)}) == "HINT"
    assert verdict({"t": (1, 0.1, 2), "f": (0, -1, 1)}) == "WORSE"
    assert verdict({"t": (0, -1, 1), "f": (0, -1, 1)}) == "NONE"


def test_asof_prior_needs_its_minimum_and_sees_only_the_past():
    prior = AsOfPrior(minimum=2)
    prior.observe(851, 2)
    assert prior.total(851) is None
    prior.observe(851, 4)
    assert prior.total(851) == pytest.approx(3.0)
    assert prior.total(852) is None


def _event(eid: int, comp: int, ts: int, national: bool = True,
           status: str = "finished") -> dict[str, Any]:
    return {
        "id": eid, "startTimestamp": ts, "status": {"type": status},
        "homeTeam": {"id": 1, "national": national},
        "awayTeam": {"id": 2, "national": national},
        "homeScore": {"current": 2}, "awayScore": {"current": 1},
        "tournament": {"uniqueTournament": {"id": comp}},
    }


def test_parse_event_builds_both_histories_and_the_friendly_target():
    history: dict[int, list[Past]] = {1: [], 2: []}
    seen: set[int] = set()
    t = parse_event(_event(5, 852, DAY), frozenset({851}), history, seen)
    assert isinstance(t, Target) and t.home_goals == 2 and t.away_goals == 1
    assert history[1][0].goals_for == 2 and history[2][0].goals_for == 1
    assert parse_event(_event(5, 852, DAY), frozenset(), history, seen) is None
    assert parse_event(_event(6, 290, DAY), frozenset(), history, seen) is None
    assert len(history[1]) == 2
    assert parse_event(_event(7, 851, DAY, national=False), frozenset(),
                       history, seen) is None
    assert parse_event(_event(8, 851, DAY, status="notstarted"), frozenset(),
                       history, seen) is None


def test_score_target_scores_the_same_case_for_every_variant():
    history = {
        1: [past(d, d, 852 if d % 2 else 290, 1, 1) for d in range(1, 25)],
        2: [past(d, 100 + d, 852, 2, 0) for d in range(1, 25)],
    }
    t = Target(50 * DAY, 999, 852, False, 1, 2, 1.0, 1.0)
    table = DispersionTable({
        "goals_total": MarketCell(0.05, "nb"), "goals_for": MarketCell(0.25, "nb")})
    cases = score_target(t, history, {}, table, 15.0)
    assert [c.market for c in cases] == ["goals_total", "goals_for", "goals_for"]
    for c in cases:
        assert set(c.nb) == set(c.sq) == {"A", "B", "C", "D"}
    # side 2 plays only friendlies: A == B there
    assert cases[2].differs is False and cases[1].differs is True
