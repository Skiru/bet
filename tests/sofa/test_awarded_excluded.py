"""Results awarded at the table (Sofascore `isAwarded`) leave the football
samples and the rating SHEET replays under epochs.AWARDED_EXCLUDED_FROM_UTC.

2026-10-29 verification: Maardu Linnameeskond withdrew from the Esiliiga and
its unplayed games (15514355 vs Tallinna Kalev, 15514366 vs Nomme Kalju U21)
sat in both sides' goal samples as 0-0 - status 100 "Ended", isAwarded true,
no periods, no statistics. SETTLE already refused the flag
(settle.is_settleable); the samples and the rating did not.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from bet.sofa import epochs, timeutil
from bet.sofa.comparability import is_awarded_event
from bet.sofa.config import SofaConfig
from bet.sofa.contracts import GapEntry, GapReason
from bet.sofa.football_rating import parse_event, without_awarded
from bet.sofa.samples import get_historical_events, peer_history
from bet.sofa.score_model import parse_event as sport_parse_event
from bet.sofa.shadow import SPORTS
from tests.sofa.test_audit1023_p1_conflict_cut import (
    DAY,
    ME,
    T0,
    Cache,
    Client,
    ev,
    fixture,
    ids,
)


def awarded(eid: int, at: int, opp: int) -> dict[str, Any]:
    """Maardu's shape: Ended, 0-0, winnerCode 3, isAwarded, no periods."""
    e = ev(eid, at, opp)
    e["homeScore"] = {"current": 0, "display": 0, "normaltime": 0}
    e["awayScore"] = {"current": 0, "display": 0, "normaltime": 0}
    e["winnerCode"] = 3
    e["isAwarded"] = True
    return e


def events() -> list[dict[str, Any]]:
    out = [ev(100 + i, T0 - (i + 1) * 7 * DAY, 50 + i) for i in range(12)]
    out.append(awarded(900, T0 - 3 * DAY, 60))
    return out


def run(gaps: list[GapEntry] | None = None) -> list[dict[str, Any]]:
    return get_historical_events(
        Client(), Cache(events()), ME, "football", fixture(),  # type: ignore[arg-type]
        SofaConfig.from_env(), gaps)


def switch_at(monkeypatch: pytest.MonkeyPatch, at: datetime | None,
              now: datetime) -> None:
    monkeypatch.setattr(epochs, "AWARDED_EXCLUDED_FROM_UTC", at)
    monkeypatch.setattr(timeutil, "now", lambda: now)


def test_the_flag_is_isawarded_true_only() -> None:
    assert is_awarded_event(awarded(1, T0, 2))
    assert not is_awarded_event(ev(1, T0, 2))
    assert not is_awarded_event({**ev(1, T0, 2), "isAwarded": False})


def test_off_the_awarded_0_0_is_in_the_sample(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    switch_at(monkeypatch, None, datetime.fromtimestamp(T0 - DAY, UTC))
    assert 900 in ids(run())


def test_on_it_leaves_the_sample_with_a_named_gap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    at = datetime.fromtimestamp(T0 - 2 * DAY, UTC)
    switch_at(monkeypatch, at, datetime.fromtimestamp(T0 - DAY, UTC))
    gaps: list[GapEntry] = []
    got = run(gaps)
    assert 900 not in ids(got)
    assert ids(got) == list(range(100, 110))
    hit = [g for g in gaps if "900 awarded" in g.detail]
    assert [g.reason for g in hit] == [GapReason.EVENT_NOT_FINISHED]


def test_a_day_built_before_the_switch_keeps_the_old_rule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    at = datetime.fromtimestamp(T0 + 2 * DAY, UTC)
    switch_at(monkeypatch, at, datetime.fromtimestamp(T0 + 3 * DAY, UTC))
    assert 900 in ids(run())


def test_the_peers_history_drops_it_only_under_the_switch() -> None:
    listed = events()
    assert 900 in ids(peer_history(listed, ME, T0, conflict_cut=False))
    assert 900 not in ids(peer_history(listed, ME, T0, conflict_cut=False,
                                       awarded_out=True))


def test_the_rating_marks_it_and_without_awarded_drops_it() -> None:
    def football(e: dict[str, Any]) -> dict[str, Any]:
        return {**e, "tournament": {"id": 77, "uniqueTournament": {"id": 17},
                                    "category": {"sport": {"slug": "football"}}},
                "awayTeam": {"id": 60}}
    played = parse_event(football(ev(1, T0, 60)))
    forfeit = parse_event(football(awarded(2, T0, 60)))
    assert played is not None and not played.awarded
    assert forfeit is not None and forfeit.awarded
    assert forfeit.values["goals_for"] == (0.0, 0.0)  # what the rating read
    assert without_awarded([played, forfeit]) == [played]


@pytest.mark.parametrize("sport,home,away", [
    ("basketball", 20, 0), ("hockey", 5, 0), ("volleyball", 3, 0)])
def test_the_measured_sports_already_drop_it_no_periods(
    sport: str, home: int, away: int,
) -> None:
    """Cached shape of their awarded games (537 basketball 20-0 / 0-20, 59
    hockey, 62 volleyball on 10-29): a score with no periods, which the
    score model never reads - nothing to switch there."""
    spec = SPORTS[sport]
    e = {
        "id": 3, "startTimestamp": T0, "isAwarded": True, "winnerCode": 1,
        "tournament": {"id": 5, "name": "League", "uniqueTournament": {
            "id": 5, "name": "League"},
            "category": {"sport": {"slug": spec.sofascore_slug}}},
        "status": {"type": "finished", "code": 100, "description": "Ended"},
        "homeTeam": {"id": 1}, "awayTeam": {"id": 2},
        "homeScore": {"current": home, "display": home},
        "awayScore": {"current": away, "display": away},
    }
    assert sport_parse_event(e, spec) is None
