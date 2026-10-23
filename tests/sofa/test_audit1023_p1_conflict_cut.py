"""P1 of the coverage audit 2026-10-23 (B4): a two-squad clash cuts a
football side's sample at the clash instead of emptying it
(epochs.SAMPLE_CONFLICT_CUT_FROM_UTC), and two friendly tournaments leave
the sample under the same switch.

Off: the side is empty with an ENTITY_CONFLICT gap, exactly as before. On:
the side keeps its newest sample_n matches after the newest clash, only
when there are sample_n of them (the newest ten the cache replay reads).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import epochs, samples, timeutil
from bet.sofa.config import SofaConfig
from bet.sofa.contracts import Fixture, GapEntry, GapReason
from bet.sofa.samples import finish_history, get_historical_events

REPO = Path(__file__).resolve().parents[2]
ME = 7
H = 3600
T0 = 1_780_000_000
DAY = 24 * H


def ev(eid: int, at: int, opp: int, comp: int = 17) -> dict[str, Any]:
    return {
        "id": eid,
        "startTimestamp": at,
        "homeTeam": {"id": ME, "name": "Me"},
        "awayTeam": {"id": opp, "name": f"Opp {opp}"},
        "homeScore": {"current": 1},
        "awayScore": {"current": 0},
        "status": {"type": "finished", "code": 100},
        "tournament": {"uniqueTournament": {"id": comp}},
    }


def weekly(n: int, clash_after: int | None) -> list[dict[str, Any]]:
    """n weekly matches, newest a week before T0; with `clash_after`, an
    extra match 4 h after the `clash_after`-th newest (another opponent)."""
    out = [ev(100 + i, T0 - (i + 1) * 7 * DAY, 50 + i) for i in range(n)]
    if clash_after is not None:
        out.append(ev(999, T0 - (clash_after + 1) * 7 * DAY + 4 * H, 77))
    return out


def ids(events: list[dict[str, Any]]) -> list[int]:
    return sorted(int(e["id"]) for e in events)


def test_off_a_clash_long_before_the_ten_empties_the_side() -> None:
    gaps: list[GapEntry] = []
    got = finish_history(weekly(14, 12), ME, "football", 17, T0, 10, gaps)
    assert got == []
    assert [g.reason for g in gaps] == [GapReason.ENTITY_CONFLICT]
    assert "side left empty" in gaps[0].detail


def test_on_a_clash_before_the_ten_keeps_the_newest_ten() -> None:
    gaps: list[GapEntry] = []
    got = finish_history(weekly(14, 12), ME, "football", 17, T0, 10, gaps,
                         conflict_cut=True)
    assert ids(got) == list(range(100, 110))
    assert [g.reason for g in gaps] == [GapReason.ENTITY_CONFLICT]
    assert "sample cut at the clash" in gaps[0].detail


def test_on_the_cut_sample_is_the_newest_ten_without_the_check() -> None:
    """What the cache replay reads (no two-squad check): the newest ten."""
    events = weekly(14, 12)
    newest = sorted(events, key=lambda e: e["startTimestamp"])[-10:]
    got = finish_history(events, ME, "football", 17, T0, 10, None,
                         conflict_cut=True)
    assert ids(got) == ids(newest)


def test_on_a_clash_inside_the_ten_still_empties_the_side() -> None:
    gaps: list[GapEntry] = []
    got = finish_history(weekly(14, 5), ME, "football", 17, T0, 10, gaps,
                         conflict_cut=True)
    assert got == []
    assert "side left empty" in gaps[-1].detail


def test_on_two_clashes_cut_at_the_newest() -> None:
    events = weekly(16, 14) + [ev(998, T0 - 12 * 7 * DAY + 3 * H, 78)]
    got = finish_history(events, ME, "football", 17, T0, 10, None,
                         conflict_cut=True)
    assert ids(got) == list(range(100, 110))


def test_no_clash_is_untouched_by_the_switch() -> None:
    events = weekly(14, None)
    assert finish_history(events, ME, "football", 17, T0, 10) == finish_history(
        events, ME, "football", 17, T0, 10, conflict_cut=True)


def fixture() -> Fixture:
    return Fixture(
        sofascore_event_id=1, superbet_event_ids=["1"], sport="football",
        kickoff_utc=datetime.fromtimestamp(T0, UTC),
        home_name="Me", away_name="X", home_entity_id=ME, away_entity_id=8,
        competition_name="C", competition_id=17, season_id=1, category_name="X",
        identity="CONFIRMED", round_number=None, round_name=None,
        cup_round_type=None, previous_leg_event_id=None, venue_name=None,
        referee=None, ground_type=None, default_period_count=None,
    )


class Cache:
    def __init__(self, events: list[dict[str, Any]]) -> None:
        self.listing = {"events": events}

    def get_entity_events(self, *a: Any) -> dict[str, Any] | None:
        return self.listing if a[2] == 0 else None

    def save_entity_events(self, *_: Any) -> None:
        raise AssertionError("no write expected")

    def get_listed_events(self, *_: object) -> list[dict[str, Any]]:
        return []


class Client:
    def entity_events(self, *_: Any) -> None:
        return None


def run(events: list[dict[str, Any]], conflict_cut: bool | None,
        gaps: list[GapEntry] | None = None) -> list[dict[str, Any]]:
    return get_historical_events(
        Client(), Cache(events), ME, "football", fixture(),  # type: ignore[arg-type]
        SofaConfig.from_env(), gaps, conflict_cut=conflict_cut)


def test_get_historical_events_both_switch_states() -> None:
    events = weekly(14, 12)
    assert run(events, False) == []
    assert ids(run(events, True)) == list(range(100, 110))


def test_the_switch_is_read_by_the_fixture_day_and_the_build_clock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = weekly(14, 12)
    switch = datetime.fromtimestamp(T0 - DAY, UTC)
    monkeypatch.setattr(epochs, "SAMPLE_CONFLICT_CUT_FROM_UTC", switch)
    monkeypatch.setattr(timeutil, "now", lambda: switch)
    assert ids(run(events, None)) == list(range(100, 110))
    # built before the switch: off
    monkeypatch.setattr(timeutil, "now",
                        lambda: datetime.fromtimestamp(T0 - 2 * DAY, UTC))
    assert run(events, None) == []
    # a day before the switch, built after it: off
    monkeypatch.setattr(epochs, "SAMPLE_CONFLICT_CUT_FROM_UTC",
                        datetime.fromtimestamp(T0 + 2 * DAY, UTC))
    monkeypatch.setattr(timeutil, "now",
                        lambda: datetime.fromtimestamp(T0 + 3 * DAY, UTC))
    assert run(events, None) == []


def test_the_two_friendlies_leave_the_sample_only_under_the_switch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = weekly(12, None)
    # a friendly tournament two matches a day apart -> a clash when it counts
    events += [ev(500, T0 - 3 * DAY, 90, comp=38659),
               ev(501, T0 - 3 * DAY + 5 * H, 91, comp=38659)]
    monkeypatch.setattr(samples, "CONFLICT_CUT_FRIENDLY_IDS",
                        frozenset({38659}))
    gaps: list[GapEntry] = []
    assert run(events, False, gaps) == []
    assert GapReason.ENTITY_CONFLICT in [g.reason for g in gaps]
    assert ids(run(events, True)) == list(range(100, 110))


def test_the_config_holds_both_ids_apart_from_the_list_every_day_reads() -> None:
    cfg = json.loads((REPO / "config/sofa_friendly_competitions.json").read_text())
    entries = cfg["excluded_from_sample_conflict_cut"]
    assert {e["competition_id"] for e in entries} == {38292, 38659}
    assert samples.CONFLICT_CUT_FRIENDLY_IDS == {38292, 38659}
    assert not samples.CONFLICT_CUT_FRIENDLY_IDS & samples.FRIENDLY_COMPETITION_IDS
    for e in entries:
        assert (REPO / e["evidence"]).exists()
        assert str(e["competition_id"]) in (REPO / e["evidence"]).read_text()
