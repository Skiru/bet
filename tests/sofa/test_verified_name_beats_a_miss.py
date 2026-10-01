"""A verified name is looked up even with a fresh miss row, and never gets a
miss written - review 2026-10-01: ~26 tennis matches (Tien-Hurkacz) were never
asked because one earlier fixture's absence blocked the known id for 7 days."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bet.sofa.cache import SofaCache
from bet.sofa.config import SofaConfig
from bet.sofa.db import migrate
from bet.sofa.resolve import SofaResolver

KICKOFF = datetime(2026, 10, 1, 11, 0, tzinfo=UTC)


class Client:
    def __init__(self, events: list[dict[str, Any]]) -> None:
        self.events = events
        self.listings = 0
        self.searches = 0

    def entity_events(self, *a: Any, **k: Any) -> Any:
        self.listings += 1
        return {"events": self.events, "hasNextPage": False}

    def search(self, *a: Any, **k: Any) -> Any:
        self.searches += 1
        return {"results": []}


def _setup(tmp_path: Path, events: list[dict[str, Any]]) -> tuple[SofaResolver, SofaCache, Client]:
    db = str(tmp_path / "sofa.db")
    migrate(db)
    config = SofaConfig(db_path=db, runs_dir=str(tmp_path))
    cache = SofaCache(config)
    cache.save_entity(
        sport="tennis", query_key="hubert hurkacz", sofascore_id=418826,
        sofascore_name="Hurkacz H.", entity_type="team", country=None,
        status="verified",
    )
    cache.save_entity_miss("tennis", "hubert hurkacz")
    client = Client(events)
    resolver = SofaResolver(config, client, cache)  # type: ignore[arg-type]
    resolver._is_match = lambda e, *a, **k: e.get("id") == 77  # type: ignore[method-assign]
    return resolver, cache, client


def test_verified_name_with_a_miss_row_still_resolves(tmp_path: Path) -> None:
    resolver, _, client = _setup(tmp_path, [{"id": 77}])
    sid, event, ambiguous = resolver.resolve_entity(
        "tennis", "Hubert Hurkacz", KICKOFF, "Learner Tien"
    )
    assert (sid, ambiguous) == (418826, False)
    assert event == {"id": 77}
    assert client.listings >= 1


def test_verified_name_is_never_recorded_as_a_miss(tmp_path: Path) -> None:
    resolver, cache, _ = _setup(tmp_path, [{"id": 5}])
    cache.clear_entity_miss("tennis", "hubert hurkacz")
    assert resolver.resolve_entity(
        "tennis", "Hubert Hurkacz", KICKOFF, "Learner Tien"
    ) == (None, None, False)
    assert cache.get_entity_miss("tennis", "hubert hurkacz") is False


def test_sofascore_reserve_suffix_folds_like_superbets_marker() -> None:
    from bet.sofa.names import normalize_name
    from bet.sofa.resolve import name_score

    assert normalize_name("River Plate Reserve") == "river plate (r)"
    assert normalize_name("Deportivo Riestra Reserves") == "deportivo riestra (r)"
    assert normalize_name("Reserve") == "reserve"
    assert name_score(
        normalize_name("CA River Plate (R)"), normalize_name("River Plate Reserve")
    ) >= 82
