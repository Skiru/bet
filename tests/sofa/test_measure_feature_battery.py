"""The feature battery of 2026-11-05 (scripts/sofa/measure_feature_battery.py):
every history feature is computed as of the kickoff (a match at or after it
never changes a value), and the Benjamini-Hochberg step is the textbook one."""

from __future__ import annotations

import math

import numpy as np

from scripts.sofa import measure_feature_battery as fb

KO = 1_800_000_000
DAY = fb.DAY_S


class MemStore(fb.Store):
    """An in-memory store: team units, per-match values and a league pool."""

    def __init__(self) -> None:
        super().__init__()
        self.comp_index: dict[int | None, list[int]] = {}

    def add(
        self,
        key: int,
        ts: int,
        home: int,
        away: int,
        goals: tuple[float, float],
        corners: tuple[float, float],
    ) -> None:
        self.events[key] = (ts, home, away, 7, 70)
        self.vals[key] = {"goals": goals, "corners": corners}
        self.comp_index.setdefault(7, []).append(key)
        for team, is_home, opp in ((home, True, away), (away, False, home)):
            self.team_units.setdefault(team, []).append(
                fb.Unit(ts, key, is_home, opp, 7, 70, "X" if is_home else "Y")
            )
        self.__dict__.pop("_lg", None)


def _store() -> MemStore:
    s = MemStore()
    k = 0
    for i in range(1, 25):
        k += 1
        s.add(
            k,
            KO - i * 3 * DAY,
            1,
            2 if i % 3 == 0 else 3 + i,
            (i % 4, i % 3),
            (5 + i % 5, 4),
        )
        k += 1
        s.add(k, KO - i * 3 * DAY - DAY, 4 + i, 2, (1, i % 2), (3, 6 + i % 3))
    return s


def _features(store: fb.Store) -> dict[str, float]:
    ctx = fb.Ctx("football", KO, 1, 2, 7, 70, "X", 0.0, 0.6)
    out = dict(fb.event_features(store, ctx))
    for kind, stat, o, line in (
        ("total", "goals", 1, 2.5),
        ("side", "corners", -1, 4.5),
        ("margin", "goals", 1, -0.5),
    ):
        base = fb.stat_base(store, ctx, kind, stat, o)
        out.update(
            {f"{kind}:{k}": v for k, v in fb.stat_features(base, kind, line).items()}
        )
    return out


def _same(a: dict[str, float], b: dict[str, float]) -> bool:
    return a.keys() == b.keys() and all(
        (math.isnan(a[k]) and math.isnan(b[k])) or a[k] == b[k] for k in a
    )


def test_as_of_keeps_only_matches_strictly_before_the_kickoff() -> None:
    units = [
        fb.Unit(KO - 10, 1, True, 2, 7, 70, None),
        fb.Unit(KO, 2, True, 2, 7, 70, None),
        fb.Unit(KO + 10, 3, False, 2, 7, 70, None),
        fb.Unit(KO - 5, 4, False, 2, 7, 70, None),
    ]
    assert [u.key for u in fb.as_of(units, KO)] == [4, 1]


def test_a_fabricated_future_match_changes_no_feature() -> None:
    before = _features(_store())
    assert not math.isnan(before["total:A04"]) and not math.isnan(before["S04"])
    assert not math.isnan(before["total:L01"]) and before["C13"] > 0
    future = _store()
    # the match itself (start == kickoff) and later ones, h2h and league included
    future.add(900, KO, 1, 2, (9, 9), (20, 20))
    future.add(901, KO + DAY, 2, 1, (9, 0), (20, 0))
    future.add(902, KO + 2 * DAY, 1, 77, (0, 9), (0, 20))
    future.add(903, KO + 3 * DAY, 78, 79, (9, 9), (20, 20))
    after = _features(future)
    assert _same(before, after)
    # the same match a second earlier is seen: the test can fail
    seen = _store()
    seen.add(904, KO - 1, 1, 2, (9, 9), (20, 20))
    assert not _same(before, _features(seen))


def test_benjamini_hochberg_step_up() -> None:
    p = [0.001, 0.008, 0.039, 0.041, 0.042, 0.06, 0.074, 0.205, 0.212, 0.216]
    # q = 0.05, m = 10: thresholds 0.005, 0.010, 0.015, ...; the largest k with
    # p(k) <= k q / m is k = 2
    assert fb.bh(p, 0.05).tolist() == [True, True] + [False] * 8
    # q = 0.10: thresholds 0.01 .. 0.10; the largest k is 6 (0.06 <= 0.06)
    assert fb.bh(p, 0.10).tolist() == [True] * 6 + [False] * 4
    # step-up: 0.03 misses its own threshold 0.025 but rides on 0.04 <= 0.05
    assert fb.bh([0.03, 0.04], 0.05).tolist() == [True, True]
    assert fb.bh([0.5, 0.9], 0.1).tolist() == [False, False]
    assert fb.bh([], 0.1).tolist() == []
    shuffled = np.array([0.212, 0.001, 0.042, 0.06])
    assert fb.bh(shuffled, 0.10).tolist() == [False, True, True, True]
