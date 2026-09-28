"""An early /statistics snapshot is asked again, once (bet.sofa.cache).

2026-09-28: Sofascore publishes a lower-league match's cards within a day and
the rest days later; the cache kept the first answer forever. Event 15275908
was cached with 2 keys and had 31 a week later. Measured live: cards-only rows
fetched within a day of kick-off, 4-10 days old, recovered 10/12; rows fetched
a week after kick-off 0/8; rows only <= 2 days old 2/13.
"""

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from bet.sofa.cache import SofaCache, is_provisional
from bet.sofa.config import SofaConfig
from bet.sofa.db import migrate

KICKOFF = datetime(2026, 9, 20, 18, 0, tzinfo=UTC)
K = int(KICKOFF.timestamp())


def _body(*keys: str) -> dict[str, Any]:
    return {
        "statistics": [
            {
                "period": "ALL",
                "groups": [
                    {
                        "statisticsItems": [
                            {"key": k, "homeValue": 1, "awayValue": 1} for k in keys
                        ]
                    }
                ],
            }
        ]
    }


CARDS = json.dumps(_body("yellowCards", "redCards"))
FULL = json.dumps(_body("cornerKicks", "fouls", "yellowCards"))


def _at(hours_after_kickoff: float) -> str:
    return (KICKOFF + timedelta(hours=hours_after_kickoff)).isoformat()


def _now(days: float) -> datetime:
    return KICKOFF + timedelta(days=days)


@pytest.mark.parametrize(
    ("stats", "fetched_h", "age_d", "expected"),
    [
        (CARDS, 5, 5, True),  # the Racing de Cordoba case
        (None, 5, 5, True),  # asked early, got nothing, league may fill in
        (CARDS, 5, 2, False),  # too young: Sofascore has not filled it yet
        (FULL, 5, 5, False),  # early but already complete
        (CARDS, 200, 12, False),  # fetched a week late: the league has only cards
    ],
)
def test_which_rows_are_provisional(
    stats: str | None, fetched_h: float, age_d: float, expected: bool
) -> None:
    assert is_provisional(stats, _at(fetched_h), K, _now(age_d)) is expected


@pytest.fixture
def cache(tmp_path: Path) -> SofaCache:
    db = str(tmp_path / "sofa.db")
    migrate(db)
    return SofaCache(SofaConfig(db_path=db))


def _put(cache: SofaCache, eid: int, stats: str | None, fetched_at: str) -> None:
    conn = sqlite3.connect(cache.config.db_path)
    conn.execute(
        "INSERT INTO sofa_event_stats (sofascore_event_id, fetched_at,"
        " statistics_json, incidents_json, status_type)"
        " VALUES (?, ?, ?, ?, 'finished')",
        (eid, fetched_at, stats, json.dumps({"incidents": []})),
    )
    conn.commit()
    conn.close()


def test_a_provisional_row_reads_as_a_miss_only_when_the_kickoff_is_given(
    cache: SofaCache, monkeypatch: pytest.MonkeyPatch
) -> None:
    import bet.sofa.cache as cache_module

    _put(cache, 7, CARDS, _at(5))
    monkeypatch.setattr(cache_module, "now", lambda: _now(6))
    assert cache.get_event_stats(7, kickoff_ts=K) is None
    kept = cache.get_event_stats(7)  # callers without a kickoff: unchanged
    assert kept is not None and kept[0] == json.loads(CARDS)


def test_one_refetch_makes_the_row_final_and_keeps_the_incidents(
    cache: SofaCache, monkeypatch: pytest.MonkeyPatch
) -> None:
    import bet.sofa.cache as cache_module

    _put(cache, 7, CARDS, _at(5))
    monkeypatch.setattr(cache_module, "now", lambda: _now(6))
    # A cards-only league answers cards-only again: it must not be asked a third time.
    cache.save_event_stats(7, json.loads(CARDS), None, "finished")
    again = cache.get_event_stats(7, kickoff_ts=K)
    assert again is not None and again[1] == {"incidents": []}


def test_samples_ask_again_for_an_early_snapshot(
    cache: SofaCache, monkeypatch: pytest.MonkeyPatch
) -> None:
    import bet.sofa.cache as cache_module
    from bet.sofa.samples import process_historical_event

    _put(cache, 15275908, CARDS, _at(5))
    monkeypatch.setattr(cache_module, "now", lambda: _now(8))
    client = MagicMock()
    client.event_statistics.return_value = _body(
        "cornerKicks", "yellowCards", "redCards"
    )
    client.event_incidents.return_value = {"incidents": []}
    event = {
        "id": 15275908,
        "startTimestamp": K,
        "status": {"type": "finished"},
        "homeTeam": {"id": 1, "name": "A"},
        "awayTeam": {"id": 2, "name": "B"},
        "homeScore": {"current": 1},
        "awayScore": {"current": 0},
    }
    process_historical_event(
        client, cache, event, 1, "football", {"corners_total"}, MagicMock()
    )
    assert client.event_statistics.call_count == 1
    row = cache.get_event_stats(15275908)
    assert row is not None and row[0] is not None
    keys = {
        i["key"]
        for g in row[0]["statistics"][0]["groups"]
        for i in g["statisticsItems"]
    }
    assert "cornerKicks" in keys


def test_the_repair_asks_only_provisional_rows_and_backs_them_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sys

    import bet.sofa.cache as cache_module
    import bet.sofa.client as client_module
    import scripts.sofa.refetch_provisional_stats as repair

    db = str(tmp_path / "sofa.db")
    migrate(db)
    c = SofaCache(SofaConfig(db_path=db))
    _put(c, 1, CARDS, _at(5))  # provisional
    _put(c, 2, FULL, _at(5))  # complete
    _put(c, 3, CARDS, _at(200))  # a cards-only league, fetched late
    football = {"category": {"sport": {"slug": "football"}}}
    listing = {
        "events": [
            {"id": i, "startTimestamp": K, "tournament": football} for i in (1, 2, 3)
        ]
    }
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO sofa_entity_events VALUES (9, 'last', 0, ?, ?)",
        (_at(0), json.dumps(listing)),
    )
    conn.commit()
    conn.close()

    at = _now(8)
    monkeypatch.setattr(cache_module, "now", lambda: at)
    monkeypatch.setattr(repair, "datetime", MagicMock(now=lambda tz=None: at))
    asked: list[int] = []

    class FakeClient:
        def __init__(self, config: SofaConfig) -> None:
            pass

        def event_statistics(self, eid: int) -> dict[str, Any]:
            asked.append(eid)
            return _body("cornerKicks", "yellowCards", "redCards")

        def event_incidents(self, eid: int) -> dict[str, Any]:
            return {"incidents": [{"incidentType": "card"}]}

    monkeypatch.setattr(client_module, "SofascoreClient", FakeClient)
    monkeypatch.setenv("SOFA_DB_PATH", db)
    monkeypatch.setenv("SOFA_RUNS_DIR", str(tmp_path / "runs"))

    monkeypatch.setattr(sys, "argv", ["repair"])
    assert repair.main() == 0 and asked == []  # dry run asks nothing

    monkeypatch.setattr(sys, "argv", ["repair", "--apply"])
    assert repair.main() == 0
    assert asked == [1]
    row = c.get_event_stats(1, kickoff_ts=K)
    # Football: the incidents are re-asked with the statistics, not kept stale.
    assert row is not None and row[1] == {"incidents": [{"incidentType": "card"}]}
    backup = json.loads(
        next((tmp_path / "runs").glob("refetch_provisional_*.json")).read_text()
    )
    assert [b["event_id"] for b in backup] == [1] and backup[0][
        "statistics_json"
    ] == CARDS
