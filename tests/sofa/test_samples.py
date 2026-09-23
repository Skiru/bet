from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from bet.sofa.cache import SofaCache
from bet.sofa.config import SofaConfig
from bet.sofa.contracts import Fixture
from bet.sofa.samples import get_historical_events, process_fixture_samples

EVIDENCE_DIR = (
    Path(__file__).parent.parent.parent / "docs" / "sofa" / "evidence"
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
    # docs/sofa/evidence/team_2829_events_last_0.json is
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
    compare_at = src.index('event.get("groundType"), fixture.ground_type')
    assert unknown_at < compare_at
    assert "GapReason.SURFACE_UNKNOWN" in src


def _bare_fixture(**overrides):
    base = dict(
        sofascore_event_id=900,
        superbet_event_ids=["9001"],
        sport="tennis",
        kickoff_utc=datetime(2026, 9, 21, 18, 0, tzinfo=UTC),
        home_name="A",
        away_name="B",
        home_entity_id=10,
        away_entity_id=20,
        competition_name="ITF",
        competition_id=1,
        season_id=1,
        category_name="Cat",
        identity="CONFIRMED",
        round_number=None,
        round_name=None,
        cup_round_type=None,
        previous_leg_event_id=None,
        venue_name=None,
        referee=None,
        ground_type=None,
        default_period_count=3,
    )
    base.update(overrides)
    return Fixture(**base)


class TestEmptyOfferEntryIsNotAnAnswer:
    """An offer entry naming no market must not stand in for asking.

    `metrics_from_offer` returning an empty set is the *absence* of an answer,
    true only of the moment it was fetched. On 2026-09-21 the 08:05Z OFFER
    found eight fixtures unpriced, Superbet posted their ladders during the
    day, and the 16:29Z SAMPLES read that stale emptiness and blocked all
    eight with NO_PRICE — 116 rungs, every fixture still hours from kickoff,
    and zero Superbet requests made to check (verified in run.log.jsonl: the
    stage called none of their event ids).
    """

    def _offer(self, rungs):
        from bet.sofa.contracts import FixtureOffer

        return FixtureOffer(
            sofascore_event_id=900,
            status="PRICED" if rungs else "NO_PRICE",
            rungs=rungs,
            unmapped_markets=[],
        )

    def test_empty_offer_entry_still_asks_superbet(self, mock_clients):
        client, cache, superbet = mock_clients
        superbet.event_odds.return_value = {
            "odds": [{"marketName": "Liczba gemów", "odds": []}]
        }
        client.entity_events.return_value = {"events": [], "hasNextPage": False}

        process_fixture_samples(
            _bare_fixture(),
            client,
            cache,
            superbet,
            SofaConfig(sample_n=10),
            offer=self._offer([]),
        )
        assert superbet.event_odds.called, (
            "an empty offer entry must fall through to the live call, "
            "exactly like a missing one"
        )

    def test_no_price_is_only_concluded_after_asking(self, mock_clients):
        client, cache, superbet = mock_clients
        superbet.event_odds.return_value = {"odds": None}
        client.entity_events.return_value = {"events": [], "hasNextPage": False}

        samples = process_fixture_samples(
            _bare_fixture(),
            client,
            cache,
            superbet,
            SofaConfig(sample_n=10),
            offer=self._offer([]),
        )
        assert samples.readiness == "BLOCKED"
        assert [g.reason.value for g in samples.gaps] == ["NO_PRICE"]
        assert superbet.event_odds.called

    def test_a_populated_offer_entry_still_costs_no_request(self, mock_clients):
        """The F19 saving must survive the fix."""
        from bet.sofa.contracts import PricedRung
        from bet.sofa.timeutil import now

        client, cache, superbet = mock_clients
        client.entity_events.return_value = {"events": [], "hasNextPage": False}

        process_fixture_samples(
            _bare_fixture(),
            client,
            cache,
            superbet,
            SofaConfig(sample_n=10),
            offer=self._offer(
                [
                    PricedRung(
                        market="games_total",
                        subject="",
                        line=20.5,
                        over_odds=1.9,
                        under_odds=1.9,
                        fetched_at_utc=now(),
                    )
                ]
            ),
        )
        assert not superbet.event_odds.called


# --- the predictable 404 on /event/{id}/statistics ------------------------
#
# 3,806 of one run's 26,493 live Sofascore requests were a 404 on this route
# (measured 2026-09-22). 1,241 of them sat in tournaments that have never once
# served statistics across 35,815 cached events, so they are predictable from
# a payload we already hold.


def _historical_event(event_id: int, tournament_id: int, **extra):
    return {
        "id": event_id,
        "startTimestamp": int(datetime(2026, 9, 1, 12, 0, tzinfo=UTC).timestamp()),
        "status": {"type": "finished"},
        "homeTeam": {"id": 1, "name": "Home"},
        "awayTeam": {"id": 2, "name": "Away"},
        "tournament": {
            "name": "T",
            "uniqueTournament": {"id": tournament_id, "name": "T"},
        },
        **extra,
    }


def _skip_fixture():
    return Fixture(
        sofascore_event_id=999,
        superbet_event_ids=["1"],
        sport="football",
        kickoff_utc=datetime(2026, 9, 22, 18, 0, tzinfo=UTC),
        home_name="Home",
        away_name="Away",
        home_entity_id=1,
        away_entity_id=2,
        competition_name="T",
        competition_id=35308,
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


def _call_process(monkeypatch, cache, event, listed_ids):
    from bet.sofa import samples as samples_mod

    monkeypatch.setattr(samples_mod, "NO_STATS_TOURNAMENT_IDS", frozenset(listed_ids))
    client = MagicMock()
    client.event_statistics.return_value = None
    client.event_incidents.return_value = None
    fixture = _skip_fixture()
    samples_mod.process_historical_event(
        client, cache, event, 1, "football", set(), fixture
    )
    return client


def test_statistics_skipped_for_a_tournament_that_never_serves_them(
    mock_clients, monkeypatch
):
    """The saving: a listed tournament costs zero requests, not one 404."""
    _, cache, _ = mock_clients
    client = _call_process(
        monkeypatch, cache, _historical_event(500, 35308), {35308}
    )
    assert client.event_statistics.call_count == 0


def test_statistics_still_fetched_for_an_unlisted_tournament(
    mock_clients, monkeypatch
):
    """The guard: the gate is the list, not "lower division" by vibes."""
    _, cache, _ = mock_clients
    client = _call_process(
        monkeypatch, cache, _historical_event(501, 17), {35308}
    )
    assert client.event_statistics.call_count == 1


def test_event_payload_overrides_the_list(mock_clients, monkeypatch):
    """The valve: a tournament that starts publishing is not locked out.

    hasEventPlayerStatistics is True for 11,574 cached events, of which only
    20 lacked statistics (0.2%), and for none of the 1,241 events the list
    skips — so honouring it costs nothing today.
    """
    _, cache, _ = mock_clients
    client = _call_process(
        monkeypatch,
        cache,
        _historical_event(502, 35308, hasEventPlayerStatistics=True),
        {35308},
    )
    assert client.event_statistics.call_count == 1


def test_a_skip_is_not_written_to_the_cache(mock_clients, monkeypatch):
    """A prediction must not read back as an observation.

    A row with NULL statistics is indistinguishable from "asked, got 404", and
    that row stops the next run from asking at all. If the list is ever wrong,
    a later run still being free to ask is the only thing that corrects it.
    """
    _, cache, _ = mock_clients
    _call_process(monkeypatch, cache, _historical_event(503, 35308), {35308})
    assert cache.get_event_stats(503) is None


def test_incidents_are_still_fetched_when_statistics_are_skipped(
    mock_clients, monkeypatch
):
    """29 of the 1,241 skipped events carry incidents despite no statistics,
    and card points have no other source, so the saving stops at /statistics."""
    from bet.sofa import samples as samples_mod

    _, cache, _ = mock_clients
    monkeypatch.setattr(samples_mod, "NO_STATS_TOURNAMENT_IDS", frozenset({35308}))
    client = MagicMock()
    client.event_incidents.return_value = {"incidents": []}
    fixture = _skip_fixture()
    samples_mod.process_historical_event(
        client,
        cache,
        _historical_event(504, 35308),
        1,
        "football",
        {"cards_points_total"},
        fixture,
    )
    assert client.event_statistics.call_count == 0
    assert client.event_incidents.call_count == 1


def test_the_shipped_list_is_a_fit_not_a_hand_edit():
    """config/sofa_no_stats_tournaments.json must carry its own provenance."""
    import json

    from bet.sofa.samples import _NO_STATS_PATH

    raw = json.loads(_NO_STATS_PATH.read_text(encoding="utf-8"))
    assert raw["min_events"] >= 10
    assert raw["fitted_at_utc"].endswith("Z")
    assert raw["events_examined"] > 0
    assert all(
        isinstance(entry["id"], int) and entry["events"] >= raw["min_events"]
        for entry in raw["tournaments"]
    )


def test_a_generic_surface_label_samples_its_whole_family():
    """2026-09-23: 111 of 316 tennis fixtures carried "Hard" or "Clay".

    Compared literally, a fixture on "Hard" was scoped to the few past matches
    labelled "Hard" and never to "Hardcourt outdoor" - the ITF W35 Sharm El
    Sheikh draw came out at 0-3 observations a side.
    """
    from bet.sofa.settle import surfaces_comparable

    assert surfaces_comparable("Hardcourt outdoor", "Hard")
    assert surfaces_comparable("Hardcourt indoor", "Hard")
    assert surfaces_comparable("Hard", "Hardcourt outdoor")
    assert surfaces_comparable("Red clay", "Clay")
    assert surfaces_comparable("Clay", "Green clay")
    # Two specific labels must still agree: indoor and outdoor stay apart.
    assert not surfaces_comparable("Hardcourt indoor", "Hardcourt outdoor")
    assert not surfaces_comparable("Red clay", "Hardcourt outdoor")
    assert not surfaces_comparable("Grass", "Hard")
    assert not surfaces_comparable(None, "Hard")


def test_a_retirement_is_not_described_as_status_finished():
    """2026-09-23: "EVENT_NOT_FINISHED ... status=finished" read as a
    contradiction; a finished event refused by is_completed_event is a
    retirement or walkover and the gap has to say which code it carried."""
    src = (
        Path(__file__).resolve().parents[2] / "src/bet/sofa/samples.py"
    ).read_text(encoding="utf-8")
    assert "finished abnormally (status code {code}" in src
