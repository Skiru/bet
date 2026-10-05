"""F2.2 (09-25 defect F5): a promoted / relegated side's sample holds the
other division's matches. Shown as a note (OTHER_DIVISION_SAMPLE), never
gated, and only from epochs.MODEL_FIXES_FROM_UTC."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest

from bet.sofa import epochs
from bet.sofa.schedule import FixtureSchedule, fixture_schedule, other_division_matches

DAY = 86400
KICKOFF = 200 * DAY
LIGA, SEGUNDA, COPA = 8, 54, 329


def _event(eid: int, day: int, comp: int, season: int, country: str = "Spain",
           status: str = "finished") -> dict[str, Any]:
    return {
        "id": eid, "startTimestamp": day * DAY, "status": {"type": status},
        "homeTeam": {"id": 1}, "awayTeam": {"id": eid + 1000},
        "season": {"id": season},
        "tournament": {"name": "x", "category": {"name": country},
                       "uniqueTournament": {"id": comp, "name": f"comp {comp}"}},
    }


def _promoted() -> list[dict[str, Any]]:
    # Last season (61) in Segunda, promoted to LaLiga for season 62.
    last = [_event(i, 100 + 4 * i, SEGUNDA, 61) for i in range(1, 11)]
    this = [_event(50 + i, 180 + 5 * i, LIGA, 62) for i in range(1, 4)]
    return last + this


def test_a_promoted_side_counts_its_other_division_matches() -> None:
    got = other_division_matches(_promoted(), LIGA, "Spain", 62, KICKOFF)
    assert got == 7  # newest ten: 3 LaLiga + 7 Segunda


def test_a_side_that_played_the_league_before_is_not_new() -> None:
    # Apertura / Clausura, or a side relegated and promoted back: it played
    # the fixture's competition before this season.
    events = [_event(900, 20, LIGA, 60), *_promoted()]
    assert other_division_matches(events, LIGA, "Spain", 62, KICKOFF) == 0


def test_another_country_or_a_cup_is_no_division() -> None:
    abroad = [_event(i, 100 + 4 * i, SEGUNDA, 61, country="Portugal")
              for i in range(1, 11)]
    assert other_division_matches(abroad, LIGA, "Spain", 62, KICKOFF) == 0
    no_history_before = [_event(50 + i, 180 + 5 * i, LIGA, 62) for i in range(1, 4)]
    assert other_division_matches(no_history_before, LIGA, "Spain", 62, KICKOFF) == 0


def test_the_note_waits_for_the_model_fixes(monkeypatch: pytest.MonkeyPatch) -> None:
    args = (_promoted(), [], 1, 2, LIGA, KICKOFF, 999)
    off = fixture_schedule(*args, season=62, category_name="Spain")
    assert off.side_a.other_division == 0
    assert not any(f.startswith("OTHER_DIVISION_SAMPLE") for f in off.flags())

    monkeypatch.setattr(
        epochs, "MODEL_FIXES_FROM_UTC", datetime(2026, 1, 1, tzinfo=UTC))
    on = fixture_schedule(*args, season=62, category_name="Spain")
    assert on.side_a.other_division == 7 and on.side_b.other_division == 0
    assert "OTHER_DIVISION_SAMPLE(home 7/10 from another league of its country)" in (
        on.flags())
    # The artifact round-trips, and an older artifact without the field reads.
    again = FixtureSchedule.model_validate_json(on.model_dump_json())
    assert again.side_a.other_division == 7
    raw = on.model_dump(mode="json")
    del raw["side_a"]["other_division"]
    old = FixtureSchedule.model_validate_json(json.dumps(raw))
    assert old.side_a.other_division == 0
