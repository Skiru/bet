"""leg_key tells a leg's period / map apart (2026-10-21).

10-21 printed CS2 event 17374496 `map_rounds_handicap` -4.5 T2 on map 2
(@1.54) and on map 3 (@1.48); the five-item key (event, market, subject,
line, direction) made them one, so merge_locked / carry_over / any grader
keyed by it would keep one and drop the other. The key now adds the period
(or the CS2 map number) where a leg has one; a football / tennis leg keeps
its five items, so stored keys still read.
"""

from __future__ import annotations

import json
from typing import Any

from bet.sofa.locked_print import LockedPrint, leg_key, merge_locked, printed_leg_keys


def _cs2(map_nr: int, odds: float) -> dict[str, Any]:
    return {"sport": "cs2", "sofascore_event_id": 17374496,
            "market": "map_rounds_handicap", "family": "map_rounds_handicap",
            "period": map_nr, "map_nr": map_nr, "subject": "", "line": -4.5,
            "side": "T2", "direction": "T2", "odds": odds}


def _football() -> dict[str, Any]:
    return {"sport": "football", "sofascore_event_id": 1,
            "market": "goals_1h_total", "subject": "", "line": 0.5,
            "direction": "OVER", "odds": 1.4}


def test_two_maps_of_one_line_are_two_keys() -> None:
    a, b = _cs2(2, 1.54), _cs2(3, 1.48)
    assert leg_key(a) != leg_key(b)
    assert leg_key(a)[-1] == 2 and leg_key(b)[-1] == 3


def test_map_nr_alone_counts() -> None:
    leg = {**_cs2(2, 1.54), "period": None}
    assert leg_key(leg)[-1] == 2


def test_hockey_periods_are_three_keys() -> None:
    legs = [{"sport": "hockey", "sofascore_event_id": 9, "market": "period_total",
             "subject": "", "line": 0.5, "direction": "OVER", "period": p}
            for p in (1, 2, 3)]
    assert len({leg_key(x) for x in legs}) == 3


def test_a_leg_without_a_period_keeps_its_five_items() -> None:
    leg = _football()
    assert leg_key(leg) == (1, "goals_1h_total", "", 0.5, "OVER")
    # a stored key (printed/<ts>.json, printed_after_start) round-trips
    assert tuple(json.loads(json.dumps(list(leg_key(leg))))) == leg_key(leg)
    assert leg_key({**leg, "period": 0, "map_nr": None}) == leg_key(leg)


def test_merge_locked_keeps_both_maps() -> None:
    a, b = _cs2(2, 1.54), _cs2(3, 1.48)
    out = merge_locked(LockedPrint(singles=[a], legs=[a]),
                       LockedPrint(singles=[b], legs=[b]))
    assert [s["odds"] for s in out.singles] == [1.54, 1.48]
    assert len(out.legs) == 2


def test_printed_leg_keys_hold_both_maps() -> None:
    doc = {"singles": [_cs2(2, 1.54), _cs2(3, 1.48), _football()],
           "builders": []}
    keys = printed_leg_keys(doc)
    assert len(keys) == 3
    assert len(printed_leg_keys(doc, sheet_sports_only=True)) == 1
