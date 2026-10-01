"""A match cached without incidents (first cached for a fixture with no card
market) must be asked for /incidents once a card sample needs it - review
2026-10-01: 118 NO_INCIDENTS gaps over 59 cached events, all NULL."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from bet.sofa.cache import SofaCache
from bet.sofa.config import SofaConfig
from bet.sofa.db import migrate
from bet.sofa.samples import process_historical_event

KICKOFF_TS = 1_759_000_000  # 2025-09-27, long final


@pytest.fixture
def cache(tmp_path: Path) -> SofaCache:
    db = str(tmp_path / "sofa.db")
    migrate(db)
    return SofaCache(SofaConfig(db_path=db))


def _stats() -> dict[str, Any]:
    items = [
        {"key": k, "homeValue": 5, "awayValue": 3, "home": "5", "away": "3"}
        for k in ("cornerKicks", "fouls", "yellowCards")
    ]
    return {"statistics": [{"period": "ALL", "groups": [{"statisticsItems": items}]}]}


def _put_without_incidents(cache: SofaCache, eid: int) -> None:
    conn = sqlite3.connect(cache.config.db_path)
    conn.execute(
        "INSERT INTO sofa_event_stats (sofascore_event_id, fetched_at,"
        " statistics_json, incidents_json, status_type)"
        " VALUES (?, '2025-10-10T00:00:00+00:00', ?, NULL, 'finished')",
        (eid, json.dumps(_stats())),
    )
    conn.commit()
    conn.close()


def _event(eid: int) -> dict[str, Any]:
    return {
        "id": eid,
        "startTimestamp": KICKOFF_TS,
        "status": {"type": "finished"},
        "homeTeam": {"id": 1, "name": "A"},
        "awayTeam": {"id": 2, "name": "B"},
        "homeScore": {"current": 1},
        "awayScore": {"current": 0},
    }


def test_card_sample_asks_incidents_for_a_cached_match(cache: SofaCache) -> None:
    _put_without_incidents(cache, 501)
    client = MagicMock()
    client.event_incidents.return_value = {
        "incidents": [{"incidentType": "card", "incidentClass": "yellow",
                       "isHome": True, "player": {"id": 9}, "time": 30}]
    }
    process_historical_event(
        client, cache, _event(501), 1, "football", {"cards_points_total"}, MagicMock()
    )
    assert client.event_incidents.call_count == 1
    assert client.event_statistics.call_count == 0
    row = cache.get_event_stats(501)
    assert row is not None and row[0] is not None  # statistics kept
    assert row[1] is not None and row[1]["incidents"]


def test_a_404_is_stored_and_not_asked_again(cache: SofaCache) -> None:
    _put_without_incidents(cache, 502)
    client = MagicMock()
    client.event_incidents.return_value = None  # the client's 404
    for _ in range(2):
        process_historical_event(
            client, cache, _event(502), 1, "football", {"cards_points_for"},
            MagicMock(),
        )
    assert client.event_incidents.call_count == 1
    row = cache.get_event_stats(502)
    assert row is not None and row[1] == {}


def test_no_card_metric_asks_nothing(cache: SofaCache) -> None:
    _put_without_incidents(cache, 503)
    client = MagicMock()
    process_historical_event(
        client, cache, _event(503), 1, "football", {"corners_total"}, MagicMock()
    )
    assert client.event_incidents.call_count == 0


def _event_with_goals(eid: int) -> dict[str, Any]:
    ev = _event(eid)
    ev["homeScore"] = {"current": 2, "normaltime": 2}
    ev["awayScore"] = {"current": 1, "normaltime": 1}
    return ev


def test_a_404_never_poisons_the_matchs_other_metrics(cache: SofaCache) -> None:
    # Review 2026-10-01: a stored {} was read as "incidents, zero goals" and
    # every metric of a 2-1 match went INTERNAL_INCONSISTENT, for good.
    from bet.sofa.contracts import GapReason

    _put_without_incidents(cache, 504)
    client = MagicMock()
    client.event_incidents.return_value = None
    process_historical_event(
        client, cache, _event_with_goals(504), 1, "football",
        {"corners_total", "cards_points_total"}, MagicMock(),
    )
    later = process_historical_event(
        MagicMock(), cache, _event_with_goals(504), 1, "football",
        {"corners_total"}, MagicMock(),
    )
    corners = later["collected"]["corners_total"]
    assert not isinstance(corners, GapReason), corners


def test_a_provider_fault_on_the_ask_costs_only_the_cards(cache: SofaCache) -> None:
    from bet.sofa.contracts import GapReason
    from bet.sofa.errors import CircuitOpenError

    _put_without_incidents(cache, 505)
    client = MagicMock()
    client.event_incidents.side_effect = CircuitOpenError("open")
    out = process_historical_event(
        client, cache, _event_with_goals(505), 1, "football",
        {"corners_total", "cards_points_total"}, MagicMock(),
    )
    assert not isinstance(out["collected"]["corners_total"], GapReason)
    assert out["collected"]["cards_points_total"] == GapReason.PROVIDER_ERROR
    row = cache.get_event_stats(505)
    assert row is not None and row[1] is None  # not recorded: ask again next run


def test_empty_incidents_grade_as_none_everywhere() -> None:
    # The shared metrics code is what SETTLE, regrade, calibration and the
    # rating read: {} must be NO_INCIDENTS there too, never 0 cards.
    from bet.sofa.contracts import GapReason
    from bet.sofa.metrics import calculate_cards_points, check_identities

    assert calculate_cards_points({}, {"yellowCards": (0.0, 0.0)}) == GapReason.NO_INCIDENTS
    assert calculate_cards_points(None) == GapReason.NO_INCIDENTS
    assert check_identities({}, {}, _event_with_goals(1), "football") is None


def test_a_superbet_error_in_the_metric_fallback_is_one_listing() -> None:
    from bet.sofa.contracts import Fixture
    from bet.sofa.samples import fetch_available_metrics

    class Boom(Exception):
        pass

    client = MagicMock()
    client.event_odds.side_effect = Boom("404 Client Error")
    fx = Fixture.model_construct(superbet_event_ids=["1", "2"])
    assert fetch_available_metrics(fx, client) == set()
