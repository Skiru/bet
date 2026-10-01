"""A day's stat-gap skips can be asked again (2026-10-01).

The 09-30 coupon's 4 unsettled legs and the WARIANT's 10 were corners on three
matches cached ~5 h after the final whistle with no statistics or cards only.
The cache re-asks such a row only once the match is REFETCH_AFTER_DAYS old;
nothing settled the date again by then, so the legs stayed unsettled for ever.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.sofa import run_settle


def test_stat_gap_events_reads_only_statistic_gaps(tmp_path: Path) -> None:
    path = tmp_path / "07_settle_skips.json"
    path.write_text(
        json.dumps(
            {
                "skipped_events": [
                    {"sofascore_event_id": 1, "skipped": {"corners_total:NO_STATISTICS": 14}},
                    {"sofascore_event_id": 2, "skipped": {"corners_total:STAT_KEY_ABSENT": 10}},
                    {"sofascore_event_id": 3, "skipped": {"FINISHED_ABNORMALLY": 5}},
                    {"sofascore_event_id": 4, "skipped": {"NOT_FINISHED": 2, "cards_points_total:STAT_KEY_ABSENT": 1}},
                ]
            }
        ),
        encoding="utf-8",
    )
    assert run_settle.stat_gap_events(path) == frozenset({1, 2, 4})
    assert run_settle.stat_gap_events(tmp_path / "missing.json") == frozenset()


class _Client:
    def __init__(self) -> None:
        self.stats_calls = 0

    def event(self, event_id: int) -> dict[str, Any]:
        return {
            "event": {
                "id": event_id,
                "startTimestamp": 1_780_000_000,
                "status": {"type": "finished", "code": 100},
            }
        }

    def event_statistics(self, event_id: int) -> dict[str, Any]:
        self.stats_calls += 1
        return {"statistics": [{"period": "ALL", "groups": []}]}

    def event_incidents(self, event_id: int) -> dict[str, Any]:
        return {"incidents": []}


class _Cache:
    def __init__(self) -> None:
        self.saved: list[int] = []

    def save_event_detail(self, *_: Any) -> None: ...

    def get_event_stats(self, *_: Any, **__: Any) -> Any:
        return ({"statistics": []}, {"incidents": []}, "finished")  # the stale row

    def save_event_stats(self, event_id: int, *_: Any) -> None:
        self.saved.append(event_id)


def _payload(refetch: bool) -> tuple[_Client, _Cache, Any]:
    client, cache = _Client(), _Cache()
    out = run_settle._event_payload(client, cache, 7, refetch)  # type: ignore[arg-type]
    return client, cache, out


def test_without_the_flag_the_cached_row_is_used() -> None:
    client, cache, out = _payload(False)
    assert client.stats_calls == 0 and cache.saved == []
    assert out[1] == {"statistics": []}


def test_with_the_flag_the_statistics_are_asked_again_and_cached() -> None:
    client, cache, out = _payload(True)
    assert client.stats_calls == 1
    assert cache.saved == [7], "the fresh payload replaces the stale row"
    assert out[1] == {"statistics": [{"period": "ALL", "groups": []}]}
