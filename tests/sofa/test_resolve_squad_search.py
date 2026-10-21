"""A reserve / youth side searched again by its board name (2026-10-21).

`search_query` strips our "(r)" marker, so "Atlas U21" went to Sofascore as
"atlas": the senior Atlas FC filled the candidates and Atlas FC U21
(1111909) was not among the results at all. Under
epochs.SQUAD_SEARCH_RETRY_FROM_UTC a squad side the marker-free search did
not find is searched again with Superbet's name, and only candidates of its
own level are tried; SHADOW_SETTLE (record_miss=False) reads it at once.
Measured: scripts/sofa/measure_squad_search.py,
docs/sofa/history/RAPORT_RESOLVE_REZERWY_2026-10-21.md.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from bet.sofa import epochs
from bet.sofa.cache import SofaCache
from bet.sofa.config import MATCH_LOGIC_VERSION, SofaConfig
from bet.sofa.db import get_connection, migrate
from bet.sofa.names import normalize_name
from bet.sofa.resolve import (
    SofaResolver,
    squad_level_candidate,
    squad_retry_queries,
)

# The switch reads the kickoff's day and the build clock: the tests place it
# an hour before the real clock and the games three hours after it.
NOW = datetime.now(UTC)
KICKOFF = NOW + timedelta(hours=3)


def _team(id_: int, name: str) -> dict[str, Any]:
    return {"id": id_, "name": name, "gender": "M", "sport": {"slug": "football"}}


class _Client:
    """Sofascore as measured live 2026-10-21: "atlas" ranks the senior club
    and no U21; "Atlas U21" returns Atlas FC U21 (1111909)."""

    def __init__(self, kickoff: datetime) -> None:
        self.kickoff = kickoff
        self.queries: list[str] = []
        self.listed: list[int] = []

    def search(self, q: str) -> dict[str, Any]:
        self.queries.append(q)
        if q == "atlas":
            return {"results": [
                {"type": "team", "entity": _team(5260, "Atlas FC")},
                {"type": "team", "entity": _team(43820, "CA Atlas")},
            ]}
        if q == "Atlas U21":
            return {"results": [
                {"type": "team", "entity": _team(5260, "Atlas FC")},
                {"type": "team", "entity": _team(1111909, "Atlas FC U21")},
            ]}
        return {"results": []}

    def entity_events(self, entity_id: int, kind: str, page: int) -> dict[str, Any]:
        self.listed.append(entity_id)
        ts = int(self.kickoff.timestamp())
        if page > 0:
            return {"events": [], "hasNextPage": False}
        if entity_id == 1111909:
            return {"events": [{
                "id": 9001, "startTimestamp": ts,
                "tournament": {"name": "Liga MX U21", "slug": "liga-mx-u21"},
                "homeTeam": {"id": 1111909, "name": "Atlas FC U21", "gender": "M"},
                "awayTeam": {"id": 1111921, "name": "Club America U21", "gender": "M"},
            }], "hasNextPage": False}
        if entity_id == 5260:
            # The senior club plays the senior America at the same hour: it
            # must never become the reserve fixture.
            return {"events": [{
                "id": 8001, "startTimestamp": ts,
                "tournament": {"name": "Liga MX", "slug": "liga-mx"},
                "homeTeam": {"id": 5260, "name": "Atlas FC", "gender": "M"},
                "awayTeam": {"id": 1980, "name": "Club América", "gender": "M"},
            }], "hasNextPage": False}
        return {"events": [], "hasNextPage": False}


def _resolver(tmp_path: Any, client: _Client) -> SofaResolver:
    config = SofaConfig(db_path=str(tmp_path / "t.db"))
    migrate(config.db_path)
    return SofaResolver(config, client, SofaCache(config))  # type: ignore[arg-type]


def _resolve(resolver: SofaResolver, kickoff: datetime,
             record_miss: bool = True) -> tuple[Any, Any, bool]:
    return resolver.resolve_entity(
        "football", "Atlas U21", kickoff, "Club America U21",
        board_side_a="Atlas U21", board_side_b="Club America U21",
        record_miss=record_miss,
    )


@pytest.fixture(autouse=True)
def _switch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(epochs, "SQUAD_SEARCH_RETRY_FROM_UTC", NOW - timedelta(hours=1))
    # The other RESOLVE miss bounds (on from 2026-10-21) stay out of this test.
    for name in ("ENTITY_MISS_PER_DAY_FROM_UTC", "FOOTBALL_SEARCHED_ANCHOR_FROM_UTC",
                 "FOOTBALL_SQUAD_LEVEL_ALIAS_FROM_UTC",
                 "FOOTBALL_SQUAD_LEVEL_ALIAS_LOOSE_FROM_UTC",
                 "FOOTBALL_SHORT_NAME_SEARCH_FROM_UTC"):
        monkeypatch.setattr(epochs, name, None)


def _switch_tomorrow(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(epochs, "SQUAD_SEARCH_RETRY_FROM_UTC", NOW + timedelta(days=1))


def test_retry_queries_carry_the_board_marker() -> None:
    def q(side: str) -> list[str]:
        return squad_retry_queries(side, normalize_name(side))

    assert q("Atlas U21") == ["Atlas U21"]
    assert q("Independiente (PAN) II") == ["Independiente (PAN) II"]
    assert q("Zulte Waregem B") == ["Zulte Waregem B"]
    # "(R)" is no word Sofascore knows: its own spelling of reserves.
    assert q("CA River Plate (R)") == ["CA River Plate Reserve"]
    # Senior sides, and names whose marker the plain query already keeps.
    assert q("Legia Warszawa") == []
    assert q("Standard Liege U23") == []
    assert q("Dukla Liberec B (K)") == []


def test_squad_level_candidate_never_takes_the_senior_club() -> None:
    assert squad_level_candidate("atlas (r)", _team(1111909, "Atlas FC U21"))
    assert squad_level_candidate("san martin sj (r)", _team(1, "San Martin Reserve"))
    assert not squad_level_candidate("atlas (r)", _team(5260, "Atlas FC"))
    assert not squad_level_candidate("legia warszawa", _team(2, "Legia Warszawa II"))


def test_reserve_side_found_by_its_board_name(tmp_path: Any) -> None:
    client = _Client(KICKOFF)
    entity_id, event, ambiguous = _resolve(_resolver(tmp_path, client), KICKOFF)

    assert client.queries == ["atlas", "Atlas U21"]
    assert (entity_id, ambiguous) == (1111909, False)
    assert event is not None and event["id"] == 9001
    # The senior club's listings were read by the plain search only; the
    # retry tried the U21 side alone.
    assert client.listed[client.listed.index(1111909):] == [1111909, 1111909]


def test_before_the_switch_resolve_searches_once(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _switch_tomorrow(monkeypatch)
    client = _Client(KICKOFF)
    entity_id, event, _ = _resolve(_resolver(tmp_path, client), KICKOFF)

    assert client.queries == ["atlas"]
    assert (entity_id, event) == (None, None)


def test_settle_reads_the_retry_at_once(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _switch_tomorrow(monkeypatch)
    client = _Client(KICKOFF)
    entity_id, _, _ = _resolve(_resolver(tmp_path, client), KICKOFF, record_miss=False)

    assert entity_id == 1111909


@pytest.mark.parametrize(("missed_ago_h", "found"), [(2, True), (0.5, False)])
def test_a_miss_from_before_the_switch_does_not_block(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch, missed_ago_h: float, found: bool
) -> None:
    client = _Client(KICKOFF)
    resolver = _resolver(tmp_path, client)
    with get_connection(str(tmp_path / "t.db")) as conn:
        conn.execute(
            "INSERT INTO sofa_entity_miss (sport, query_key, missed_at, "
            "match_logic_version) VALUES (?, ?, ?, ?)",
            ("football", "atlas (r)",
             (NOW - timedelta(hours=missed_ago_h)).isoformat(), MATCH_LOGIC_VERSION),
        )

    entity_id, _, _ = _resolve(resolver, KICKOFF)

    # Recorded by the marker-free search before the switch: no evidence about
    # the name. Recorded after it: the retry already failed, a week's miss.
    assert (entity_id == 1111909) is found
    assert bool(client.queries) is found


def test_measure_counts_lost_squad_entries(tmp_path: Any) -> None:
    import json

    from scripts.sofa import measure_squad_search as msq

    day = tmp_path / "2026-10-21"
    day.mkdir()
    board = [
        {"superbet_event_id": "1", "sport": "football", "side_a": "Atlas U21",
         "side_b": "Club America U21"},
        {"superbet_event_id": "2", "sport": "football", "side_a": "Cracovia II",
         "side_b": "Wisla Krakow II"},
        {"superbet_event_id": "3", "sport": "football", "side_a": "Legia",
         "side_b": "Lech"},
        {"superbet_event_id": "4", "sport": "tennis", "side_a": "A", "side_b": "B"},
    ]
    (day / "01_board.json").write_text(json.dumps(board))
    (day / "02_fixtures.json").write_text(json.dumps([{"superbet_event_ids": ["2"]}]))

    off = msq.offline(str(tmp_path), None, None)

    assert off["per_date"]["2026-10-21"] == {
        "entries": 3, "squad_entries": 2, "lost": 2, "squad_lost": 1}
    assert off["lost_sides"] == {"Atlas U21": 1, "Club America U21": 1}
