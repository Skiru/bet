"""7c split by sport and epoch, 7h removed_by_reads (plan K6/K7)."""

from __future__ import annotations

from typing import Any

from scripts.sofa.audit_settlement import (
    render_removed_by_reads,
    render_stats_only_split,
)


def _leg(eid: int, sport: str, odds: float, **extra: Any) -> dict[str, Any]:
    return {"sofascore_event_id": eid, "market": "goals_total", "subject": "",
            "line": 2.5, "direction": "UNDER", "confidence": 0.8,
            "offered_odds": odds, "sport": sport, **extra}


def _key(leg: dict[str, Any]) -> tuple[Any, ...]:
    return (leg["sofascore_event_id"], leg["market"], "", 2.5, "UNDER")


def test_7c_shows_the_morning_locked_legs_apart_from_the_stats_only_ones():
    legs = [_leg(1, "football", 1.5, epoch="stats_only"),
            _leg(2, "tennis", 1.4, epoch="stats_only"),
            _leg(3, "football", 1.3, locked=True,
                 printed_under={"confidence_floor": 0.7})]
    by_key = {_key(legs[0]): {"outcome": "WIN"}, _key(legs[1]): {"outcome": "LOSS"},
              _key(legs[2]): {"outcome": "WIN"}}
    text = "\n".join(render_stats_only_split(legs, by_key))
    assert "| football | old | 1 | 1 | 1 / 0 | 0 | +0.30 j. |" in text
    assert "| football | stats_only | 1 | 1 | 1 / 0 | 0 | +0.50 j. |" in text
    assert "| tennis | stats_only | 1 | 1 | 0 / 1 | 0 | -1.00 j. |" in text


def test_7h_grades_the_removed_legs_by_who_removed_them():
    removed = [_leg(1, "football", 1.5, reason="analyst"),
               _leg(2, "football", 1.5, reason="auto")]
    by_key = {_key(removed[0]): {"outcome": "LOSS"},
              _key(removed[1]): {"outcome": "WIN"}}
    text = "\n".join(render_removed_by_reads(removed, by_key))
    assert "## 7h." in text
    assert "| analyst | 1 | 0 / 1 | -1.00 j. |" in text
    assert "| auto | 1 | 1 / 0 | +0.50 j. |" in text
