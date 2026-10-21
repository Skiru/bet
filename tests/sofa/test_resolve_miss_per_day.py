"""An entity miss counts for its own day only (epochs.ENTITY_MISS_PER_DAY,
2026-10-21).

A name RESOLVE failed to find was not searched again for 7 days; 11 of the
127 football gaps of 10-13..10-20 with neither side known were names a miss
from an earlier fixture blocked while Sofascore had the game, and the late
RESOLVE pass could not re-ask the ITF matches Sofascore listed after the
morning. Report: docs/sofa/history/RAPORT_RESOLVE_PUDLA_2026-10-21.md.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from bet.sofa import epochs
from bet.sofa.cache import SofaCache
from bet.sofa.config import MATCH_LOGIC_VERSION, SofaConfig
from bet.sofa.db import get_connection, migrate
from bet.sofa.resolve import SofaResolver

NOW = datetime.now(UTC)
KICKOFF = NOW + timedelta(hours=2)


class _Client:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def search(self, q: str) -> dict[str, Any]:
        self.queries.append(q)
        return {"results": [{"type": "team", "entity": {
            "id": 77, "name": "AC Tripoli", "gender": "M",
            "sport": {"slug": "football"}}}]}

    def entity_events(self, entity_id: int, kind: str, page: int) -> dict[str, Any]:
        if page > 0 or kind != "next":
            return {"events": [], "hasNextPage": False}
        return {"events": [{
            "id": 17182512, "startTimestamp": int(KICKOFF.timestamp()),
            "tournament": {"name": "Lebanese Premier League", "slug": "lpl"},
            "homeTeam": {"id": 77, "name": "AC Tripoli", "gender": "M"},
            "awayTeam": {"id": 78, "name": "Al-Akhaa Al-Ahli", "gender": "M"},
        }], "hasNextPage": False}


def _resolver(tmp_path: Any, missed_at: datetime) -> tuple[SofaResolver, _Client]:
    config = SofaConfig(db_path=str(tmp_path / "t.db"))
    migrate(config.db_path)
    with get_connection(config.db_path) as conn:
        conn.execute(
            "INSERT INTO sofa_entity_miss (sport, query_key, missed_at, "
            "match_logic_version) VALUES (?, ?, ?, ?)",
            ("football", "tripoli sc", missed_at.isoformat(), MATCH_LOGIC_VERSION))
    client = _Client()
    return SofaResolver(config, client, SofaCache(config)), client  # type: ignore[arg-type]


def _resolve(resolver: SofaResolver) -> Any:
    return resolver.resolve_entity(
        "football", "Tripoli SC", KICKOFF, "Al Akhaa Ahli Aley",
        board_side_a="Tripoli SC", board_side_b="Al Akhaa Ahli Aley")[0]


@pytest.fixture(autouse=True)
def _on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(epochs, "ENTITY_MISS_PER_DAY_FROM_UTC",
                        NOW - timedelta(hours=1))
    # The other RESOLVE miss bounds (on from 2026-10-21) stay out of this test.
    for name in ("FOOTBALL_SEARCHED_ANCHOR_FROM_UTC", "FOOTBALL_SQUAD_LEVEL_ALIAS_FROM_UTC",
                 "FOOTBALL_SQUAD_LEVEL_ALIAS_LOOSE_FROM_UTC",
                 "FOOTBALL_SHORT_NAME_SEARCH_FROM_UTC"):
        monkeypatch.setattr(epochs, name, None)


def _day_start(t: datetime) -> datetime:
    return t.replace(hour=0, minute=0, second=0, microsecond=0)


def test_a_miss_from_an_earlier_day_does_not_block(tmp_path: Any) -> None:
    resolver, client = _resolver(tmp_path, _day_start(KICKOFF) - timedelta(hours=3))
    assert _resolve(resolver) == 77
    assert client.queries == ["tripoli sc"]


def test_a_miss_from_the_kickoff_day_still_blocks(tmp_path: Any) -> None:
    missed = max(_day_start(KICKOFF), NOW - timedelta(minutes=5))
    resolver, client = _resolver(tmp_path, missed)
    assert _resolve(resolver) is None
    assert client.queries == []


def test_the_late_pass_re_asks_a_miss_older_than_its_freshness(tmp_path: Any) -> None:
    missed = max(_day_start(KICKOFF), NOW - timedelta(minutes=45))
    resolver, client = _resolver(tmp_path, missed)
    resolver.miss_fresh_min = 30
    expected = 77 if missed < NOW - timedelta(minutes=30) else None
    assert _resolve(resolver) == expected


def test_switch_off_keeps_the_week(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(epochs, "ENTITY_MISS_PER_DAY_FROM_UTC", None)
    resolver, client = _resolver(tmp_path, _day_start(KICKOFF) - timedelta(days=2))
    assert _resolve(resolver) is None
    assert client.queries == []
