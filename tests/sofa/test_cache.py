from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from bet.sofa.cache import SofaCache
from bet.sofa.config import SofaConfig
from bet.sofa.db import migrate


@pytest.fixture
def config(tmp_path: Path) -> SofaConfig:
    db_path = str(tmp_path / "sofa.db")
    migrate(db_path)
    return SofaConfig(db_path=db_path, events_ttl_min=360)


@pytest.fixture
def cache(config: SofaConfig) -> SofaCache:
    return SofaCache(config)


def test_event_stats_is_permanent(cache: SofaCache) -> None:
    stats = {"shots": 5}
    incidents = {"cards": 2}

    cache.save_event_stats(123, stats, incidents, "finished")

    res = cache.get_event_stats(123)
    assert res is not None
    loaded_stats, loaded_inc, status = res
    assert loaded_stats == stats
    assert loaded_inc == incidents
    assert status == "finished"

    # 404 case
    cache.save_event_stats(456, {}, {}, "finished")
    res2 = cache.get_event_stats(456)
    assert res2 is not None
    loaded_stats2, loaded_inc2, status2 = res2
    assert loaded_stats2 == {}
    assert loaded_inc2 == {}
    assert status2 == "finished"

    # Partial update case (None = not fetched)
    cache.save_event_stats(123, {"shots": 10}, None, "finished")
    res3 = cache.get_event_stats(123)
    assert res3 is not None
    loaded_stats3, loaded_inc3, status3 = res3
    assert loaded_stats3 == {"shots": 10}
    assert loaded_inc3 == {"cards": 2}  # Kept old value!


def test_save_event_stats_guards_non_terminal(cache: SofaCache) -> None:
    with pytest.raises(
        ValueError, match="Cannot save event stats for non-terminal status"
    ):
        cache.save_event_stats(999, {}, {}, "notstarted")


def test_entity_events_respects_ttl(cache: SofaCache, monkeypatch: Any) -> None:
    current_time = datetime(2026, 9, 17, 12, 0, tzinfo=UTC)

    def mock_now() -> datetime:
        return current_time

    monkeypatch.setattr("bet.sofa.cache.now", mock_now)

    events = {"data": "events"}
    cache.save_entity_events(100, "last", 0, events)

    # 1. Immediately available
    assert cache.get_entity_events(100, "last", 0) == events

    # 2. Within TTL (360 min)
    current_time += timedelta(minutes=359)
    assert cache.get_entity_events(100, "last", 0) == events

    # 3. Exactly at TTL
    current_time += timedelta(minutes=1)
    assert cache.get_entity_events(100, "last", 0) == events

    # 4. Beyond TTL (expires)
    current_time += timedelta(minutes=1)
    assert cache.get_entity_events(100, "last", 0) is None


def test_entity_returns_rejected(cache: SofaCache) -> None:
    # Save a rejected entity
    cache.save_entity("football", "bad team", 111, "Bad Team", "team", None, "rejected")

    # Should be returned (Negative Cache Hit)
    res = cache.get_entity("football", "bad team")
    assert res is not None
    assert res["status"] == "rejected"

    # Save a verified entity
    cache.save_entity(
        "football", "good team", 222, "Good Team", "team", "ES", "verified"
    )

    res = cache.get_entity("football", "good team")
    assert res is not None
    assert res["sofascore_id"] == 222
    assert res["sofascore_name"] == "Good Team"
    assert res["status"] == "verified"

    # Check that hit_count was incremented
    from bet.sofa.db import get_connection

    with get_connection(cache.config.db_path) as conn:
        row = conn.execute(
            "SELECT hit_count FROM sofa_entity WHERE query_key = 'good team'"
        ).fetchone()
        assert row["hit_count"] == 1


def test_entity_primary_key(cache: SofaCache) -> None:
    # Upewniamy się, że baza pozwala na klucze ze spacjami lub apostrofami
    cache.save_entity("football", "team's name", 123, "Team", "team", None, "candidate")
    cache.save_entity("football", "team's name", 456, "Team", "team", None, "verified")

    # Zastąpienie działa z tym samym kluczem
    res = cache.get_entity("football", "team's name")
    assert res is not None
    assert res["status"] == "verified"
    assert res["sofascore_id"] == 456
