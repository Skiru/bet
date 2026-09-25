"""SETTLE leaves enough on disk to audit a settlement afterwards.

Measured on 2026-09-24: 43 of the variant's 91 losses came from matches that
Sofascore publishes no statistics for, and the final score SETTLE graded them
from was fetched live and never kept - so no recount could reach them. And
07_settle_skips.json carried only counts, so three fixtures with no settled
row could not be told apart as a retirement or an interruption, while five
that looked the same had been postponed to the next day.
"""

from __future__ import annotations

from typing import Any

import pytest

from bet.sofa.cache import SofaCache
from bet.sofa.config import SofaConfig
from scripts.sofa.run_settle import SkipLedger, _event_payload

EVENT_ID = 17108587


class _Client:
    def __init__(self, status: dict[str, Any]) -> None:
        self.detail = {
            "event": {
                "id": EVENT_ID,
                "status": status,
                "homeScore": {"current": 2, "period1": 6, "period2": 7},
                "awayScore": {"current": 0, "period1": 3, "period2": 6},
            }
        }

    def event(self, event_id: int) -> dict[str, Any]:
        return self.detail

    def event_statistics(self, event_id: int) -> dict[str, Any]:
        return {}

    def event_incidents(self, event_id: int) -> dict[str, Any]:
        return {}


@pytest.fixture()
def cache(tmp_path) -> SofaCache:
    return SofaCache(SofaConfig(db_path=str(tmp_path / "sofa.db")))


def test_a_finished_match_keeps_its_final_score(cache):
    client = _Client({"type": "finished", "code": 100, "description": "Ended"})
    payload = _event_payload(client, cache, EVENT_ID)  # type: ignore[arg-type]
    assert not isinstance(payload, str)
    kept = cache.get_event_detail(EVENT_ID)
    assert kept is not None
    assert kept["event"]["homeScore"]["period2"] == 7


def test_a_retirement_is_kept_with_the_status_that_explains_the_skip(cache):
    status = {"type": "finished", "code": 92, "description": "Retired"}
    client = _Client(status)
    assert _event_payload(client, cache, EVENT_ID) == "FINISHED_ABNORMALLY"  # type: ignore[arg-type]
    kept = cache.get_event_detail(EVENT_ID)
    assert kept is not None
    assert kept["event"]["status"]["description"] == "Retired"


@pytest.mark.parametrize(
    "status",
    [
        {"type": "notstarted", "code": 0},
        {"type": "postponed", "code": 60},
        {"type": "inprogress", "code": 7},
    ],
)
def test_a_match_that_can_still_change_is_not_frozen(cache, status):
    """The detail cache keeps "finished" forever; anything else must not
    enter it as final, or a postponed match would never be graded."""
    client = _Client(status)
    assert isinstance(_event_payload(client, cache, EVENT_ID), str)  # type: ignore[arg-type]
    assert cache.get_event_detail(EVENT_ID) is None


def test_the_ledger_attributes_every_skip_to_its_event():
    ledger = SkipLedger()
    ledger.add(1, "NOT_FINISHED", 12)
    ledger.add(2, "FINISHED_ABNORMALLY", 7)
    ledger.add(2, "corners_for:NO_STATISTICS")
    ledger.add(2, "corners_for:NO_STATISTICS")
    ledger.add(3, "PUSH", 0)  # nothing skipped, nothing recorded

    assert ledger.counts == {
        "NOT_FINISHED": 12,
        "FINISHED_ABNORMALLY": 7,
        "corners_for:NO_STATISTICS": 2,
    }
    fixtures = {
        1: {"sport": "tennis", "home_name": "Jiri Cizek",
            "away_name": "Petros Tsitsipas", "kickoff_utc": "2026-09-24T08:30:00Z"},
    }
    events = ledger.events(fixtures)
    assert [e["sofascore_event_id"] for e in events] == [1, 2]
    assert events[0]["home_name"] == "Jiri Cizek"
    assert events[0]["skipped"] == {"NOT_FINISHED": 12}
    # An event with no fixture is still listed - NO_FIXTURE is exactly that case.
    assert events[1]["home_name"] is None
    assert events[1]["skipped"] == {"FINISHED_ABNORMALLY": 7,
                                    "corners_for:NO_STATISTICS": 2}
    # The per-event list and the counter describe the same skips.
    listed = sum(sum(e["skipped"].values()) for e in events)
    assert listed == sum(ledger.counts.values())
