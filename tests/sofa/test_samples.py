from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from bet.sofa.cache import SofaCache
from bet.sofa.config import SofaConfig
from bet.sofa.contracts import Fixture
from bet.sofa.samples import get_historical_events, process_fixture_samples

EVIDENCE_DIR = (
    Path(__file__).parent.parent.parent / "docs" / "sofascore-api" / "evidence"
)


@pytest.fixture
def mock_clients(tmp_path):
    client = MagicMock()
    db_path = str(tmp_path / "test.db")
    from bet.sofa.db import migrate

    migrate(db_path)
    cache = SofaCache(SofaConfig(db_path=db_path))
    superbet = MagicMock()
    return client, cache, superbet


def test_t12_no_future_leak(mock_clients):
    client, cache, _ = mock_clients
    config = SofaConfig(sample_n=10)

    fixture = Fixture(
        sofascore_event_id=100,
        superbet_event_ids=["1"],
        sport="football",
        kickoff_utc=datetime(2026, 9, 17, 12, 0, tzinfo=UTC),
        home_name="A",
        away_name="B",
        home_entity_id=10,
        away_entity_id=20,
        competition_name="Liga",
        competition_id=1,
        season_id=1,
        category_name="Cat",
        identity="CONFIRMED",
        round_number=1,
        round_name=None,
        cup_round_type=None,
        previous_leg_event_id=None,
        venue_name=None,
        referee=None,
        ground_type=None,
        default_period_count=None,
    )

    # Mock entity events: one past, one future (leak)
    # The real payload is the envelope Sofascore sends, not a bare list:
    # docs/sofascore-api/evidence/team_2829_events_last_0.json is
    # {"events": [...], "hasNextPage": true}.
    client.entity_events.side_effect = lambda eid, kind, p: (
        {
            "events": [
                {
                    "id": 1,
                    "status": {"type": "finished"},
                    "startTimestamp": datetime(
                        2026, 9, 10, 12, 0, tzinfo=UTC
                    ).timestamp(),
                    "homeTeam": {"id": 10},
                    "awayTeam": {"id": 99},
                },
                {
                    "id": 2,
                    "status": {"type": "finished"},
                    "startTimestamp": datetime(
                        2026, 9, 18, 12, 0, tzinfo=UTC
                    ).timestamp(),  # FUTURE
                    "homeTeam": {"id": 10},
                    "awayTeam": {"id": 99},
                },
            ],
            "hasNextPage": False,
        }
        if p == 0
        else None
    )

    events = get_historical_events(client, cache, 10, "football", fixture, config)
    assert len(events) == 1
    assert events[0]["id"] == 1


def test_t13_cache_hit_zero_requests(mock_clients):
    client, cache, superbet = mock_clients
    config = SofaConfig(sample_n=10)

    fixture = Fixture(
        sofascore_event_id=100,
        superbet_event_ids=["1"],
        sport="football",
        kickoff_utc=datetime(2026, 9, 17, 12, 0, tzinfo=UTC),
        home_name="A",
        away_name="B",
        home_entity_id=10,
        away_entity_id=20,
        competition_name="Liga",
        competition_id=1,
        season_id=1,
        category_name="Cat",
        identity="CONFIRMED",
        round_number=1,
        round_name=None,
        cup_round_type=None,
        previous_leg_event_id=None,
        venue_name=None,
        referee=None,
        ground_type=None,
        default_period_count=None,
    )

    superbet.event_odds.return_value = {"odds": [{"marketName": "Liczba goli"}]}

    # Event 1 from side A
    event_1 = {
        "id": 1,
        "status": {"type": "finished"},
        "startTimestamp": datetime(2026, 9, 10, 12, 0, tzinfo=UTC).timestamp(),
        "homeTeam": {"id": 10},
        "awayTeam": {"id": 99},
        "homeScore": {"current": 1},
        "awayScore": {"current": 0},
    }

    # Mocking entity events directly in the method
    client.entity_events.side_effect = lambda eid, kind, page: (
        {"events": [event_1], "hasNextPage": False} if eid == 10 and page == 0 else None
    )

    # Pre-populate cache for event_id = 1
    cache.save_event_stats(1, {}, {}, "finished")

    # Reset mock counters
    client.event_statistics.reset_mock()
    client.event_incidents.reset_mock()

    samples = process_fixture_samples(fixture, client, cache, superbet, config)

    assert client.event_statistics.call_count == 0
    assert client.event_incidents.call_count == 0
    assert "goals_total" in samples.metrics


def test_t14_readiness_both_sports(mock_clients):
    client, cache, superbet = mock_clients
    config = SofaConfig(sample_n=5, min_sample=5)

    def make_events(entity_id):
        return [
            {
                "id": entity_id * 100 + i,
                "status": {"type": "finished"},
                "startTimestamp": datetime(2026, 9, 10, 12, 0, tzinfo=UTC).timestamp()
                - i * 86400,
                "homeTeam": {"id": entity_id},
                "awayTeam": {"id": 99},
                "homeScore": {"current": 2, "period1": 6, "period2": 6},
                "awayScore": {"current": 1, "period1": 4, "period2": 4},
                "groundType": "Hardcourt outdoor",
                "defaultPeriodCount": 3,
            }
            for i in range(5)
        ]

    client.entity_events.side_effect = lambda eid, kind, page: (
        {"events": make_events(eid), "hasNextPage": False} if page == 0 else None
    )
    client.event_statistics.return_value = {"statistics": []}

    # Football
    fixture_fb = Fixture(
        sofascore_event_id=100,
        superbet_event_ids=["1"],
        sport="football",
        kickoff_utc=datetime(2026, 9, 17, 12, 0, tzinfo=UTC),
        home_name="A",
        away_name="B",
        home_entity_id=10,
        away_entity_id=20,
        competition_name="Liga",
        competition_id=1,
        season_id=1,
        category_name="Cat",
        identity="CONFIRMED",
        round_number=1,
        round_name=None,
        cup_round_type=None,
        previous_leg_event_id=None,
        venue_name=None,
        referee=None,
        ground_type=None,
        default_period_count=None,
    )
    superbet.event_odds.return_value = {"odds": [{"marketName": "Liczba goli"}]}

    res_fb = process_fixture_samples(fixture_fb, client, cache, superbet, config)
    assert res_fb.readiness == "READY"

    # Tennis
    fixture_te = Fixture(
        sofascore_event_id=101,
        superbet_event_ids=["2"],
        sport="tennis",
        kickoff_utc=datetime(2026, 9, 17, 12, 0, tzinfo=UTC),
        home_name="C",
        away_name="D",
        home_entity_id=30,
        away_entity_id=40,
        competition_name="Liga",
        competition_id=1,
        season_id=1,
        category_name="Cat",
        identity="CONFIRMED",
        round_number=1,
        round_name=None,
        cup_round_type=None,
        previous_leg_event_id=None,
        venue_name=None,
        referee=None,
        ground_type="Hardcourt outdoor",
        default_period_count=3,
    )
    # tennis needs games_total mapping. "liczba gemow" maps to "games_total"
    superbet.event_odds.return_value = {"odds": [{"marketName": "Liczba gemow"}]}

    # we need to provide flat_stats for tennis "gamesWon"
    client.event_statistics.return_value = {
        "statistics": [
            {
                "period": "ALL",
                "groups": [
                    {
                        "statisticsItems": [
                            {"key": "gamesWon", "homeValue": "12", "awayValue": "8"}
                        ]
                    }
                ],
            }
        ]
    }

    res_te = process_fixture_samples(fixture_te, client, cache, superbet, config)
    assert res_te.readiness == "READY"


def test_h2h_deduplication(mock_clients):
    client, cache, superbet = mock_clients
    config = SofaConfig(sample_n=10)

    fixture = Fixture(
        sofascore_event_id=100,
        superbet_event_ids=["1"],
        sport="football",
        kickoff_utc=datetime(2026, 9, 17, 12, 0, tzinfo=UTC),
        home_name="A",
        away_name="B",
        home_entity_id=10,
        away_entity_id=20,
        competition_name="Liga",
        competition_id=1,
        season_id=1,
        category_name="Cat",
        identity="CONFIRMED",
        round_number=1,
        round_name=None,
        cup_round_type=None,
        previous_leg_event_id=None,
        venue_name=None,
        referee=None,
        ground_type=None,
        default_period_count=None,
    )

    superbet.event_odds.return_value = {"odds": [{"marketName": "Liczba goli"}]}

    # H2H event present for both teams
    event_1 = {
        "id": 1,
        "status": {"type": "finished"},
        "startTimestamp": datetime(2026, 9, 10, 12, 0, tzinfo=UTC).timestamp(),
        "homeTeam": {"id": 10, "name": "A"},
        "awayTeam": {"id": 20, "name": "B"},
        "homeScore": {"current": 2},
        "awayScore": {"current": 1},
    }

    client.entity_events.side_effect = lambda eid, kind, page: (
        {"events": [event_1], "hasNextPage": False} if page == 0 else None
    )
    client.event_statistics.return_value = {"statistics": []}

    cache.save_event_stats(1, {}, {}, "finished")

    samples = process_fixture_samples(fixture, client, cache, superbet, config)
    metric = samples.metrics["goals_total"]

    # One observation from side_a, one from side_b, and it's H2H
    # Ensure they point to the exact same match.
    # Total unique matches should be exactly 1
    unique_matches = set(
        o.sofascore_event_id for o in metric.side_a + metric.side_b + metric.h2h
    )
    assert len(unique_matches) == 1

    assert (
        len(metric.h2h) == 1
    )  # a head-to-head sits in both histories and must enter h2h once (L13)
    assert len(metric.side_a) == 1
    assert len(metric.side_b) == 1


def test_tennis_sample_filtering(mock_clients):
    client, cache, superbet = mock_clients
    config = SofaConfig(sample_n=10)

    fixture = Fixture(
        sofascore_event_id=101,
        superbet_event_ids=["2"],
        sport="tennis",
        kickoff_utc=datetime(2026, 9, 17, 12, 0, tzinfo=UTC),
        home_name="C",
        away_name="D",
        home_entity_id=30,
        away_entity_id=40,
        competition_name="Liga",
        competition_id=1,
        season_id=1,
        category_name="Cat",
        identity="CONFIRMED",
        round_number=1,
        round_name=None,
        cup_round_type=None,
        previous_leg_event_id=None,
        venue_name=None,
        referee=None,
        ground_type="Hardcourt outdoor",
        default_period_count=3,
    )

    superbet.event_odds.return_value = {"odds": [{"marketName": "Liczba gemow"}]}

    client.entity_events.side_effect = lambda eid, kind, page: (
        {
            "events": [
                {
                    "id": 1,
                    "status": {"type": "finished"},
                    "startTimestamp": datetime(
                        2026, 9, 10, 12, 0, tzinfo=UTC
                    ).timestamp(),
                    "homeTeam": {"id": 30},
                    "awayTeam": {"id": 99},
                    "homeScore": {"current": 2},
                    "awayScore": {"current": 1},
                    "groundType": "Clay",  # Mismatch!
                    "defaultPeriodCount": 3,
                },
                {
                    "id": 2,
                    "status": {"type": "finished"},
                    "startTimestamp": datetime(
                        2026, 9, 11, 12, 0, tzinfo=UTC
                    ).timestamp(),
                    "homeTeam": {"id": 30},
                    "awayTeam": {"id": 99},
                    "homeScore": {"current": 2},
                    "awayScore": {"current": 1},
                    "groundType": "Hardcourt outdoor",
                    "defaultPeriodCount": 5,  # Mismatch!
                },
                {
                    "id": 3,
                    "status": {"type": "finished"},
                    "startTimestamp": datetime(
                        2026, 9, 12, 12, 0, tzinfo=UTC
                    ).timestamp(),
                    "homeTeam": {"id": 30},
                    "awayTeam": {"id": 99},
                    "homeScore": {"current": 2, "period1": 6, "period2": 6},
                    "awayScore": {"current": 1, "period1": 4, "period2": 4},
                    "groundType": "Hardcourt outdoor",
                    "defaultPeriodCount": 3,  # Match!
                },
            ],
            "hasNextPage": False,
        }
        if eid == 30 and page == 0
        else None
    )

    client.event_statistics.return_value = {
        "statistics": [
            {
                "period": "ALL",
                "groups": [
                    {
                        "statisticsItems": [
                            {"key": "gamesWon", "homeValue": "12", "awayValue": "8"}
                        ]
                    }
                ],
            }
        ]
    }

    samples = process_fixture_samples(fixture, client, cache, superbet, config)
    metric = samples.metrics["games_total"]

    # Event 1 (clay) and 2 (best-of-5) are cut; only event 3 matches.
    assert len(metric.side_a) == 1
    assert metric.side_a[0].sofascore_event_id == 3


def test_a_fixture_with_no_surface_says_so_instead_of_emptying_its_sample():
    """L14 applied to the tennis surface filter.

    `event.groundType != fixture.ground_type` is a surface filter only when we
    know our own surface. When `fixture.ground_type` is None it keeps just the
    past matches whose surface is ALSO unknown — almost none — and the sample
    empties with no reason recorded, which is indistinguishable from a
    provider gap.
    """
    from bet.sofa.contracts import GapReason

    assert GapReason.SURFACE_UNKNOWN == "SURFACE_UNKNOWN"
    src = (
        Path(__file__).resolve().parents[2] / "src/bet/sofa/samples.py"
    ).read_text(encoding="utf-8")
    # The unknown-surface branch must come BEFORE the != comparison, or the
    # comparison silently swallows the case it is meant to report.
    unknown_at = src.index("if fixture.ground_type is None:")
    compare_at = src.index('if event.get("groundType") != fixture.ground_type:')
    assert unknown_at < compare_at
    assert "GapReason.SURFACE_UNKNOWN" in src
