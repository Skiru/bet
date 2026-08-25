"""Tests for bet.simple_stats.discover: dedup merging and identity classification."""
from datetime import datetime, timezone

from bet.discovery.dedup import DeduplicationEngine
from bet.discovery.models import DiscoveredEvent

from bet.simple_stats.discover import _detect_ambiguous, _to_event_record

_KICKOFF = datetime(2026, 6, 23, 15, 0, tzinfo=timezone.utc)


def _event(source, external_id, sport="football", home="Norway", away="Senegal", kickoff=_KICKOFF):
    return DiscoveredEvent(
        source=source,
        external_id=external_id,
        sport=sport,
        competition="World Cup 2026",
        home_team=home,
        away_team=away,
        kickoff=kickoff,
        status="scheduled",
    )


def test_merges_two_sources_into_one_event():
    events_by_source = {
        "odds-api": [_event("odds-api", "abc123")],
        "highlightly": [_event("highlightly", "456")],
    }

    merged = DeduplicationEngine().merge(events_by_source)
    assert len(merged) == 1
    assert merged[0].source_count == 2

    record = _to_event_record(merged[0])
    assert record.status == "ACTIVE"
    assert record.source_ids == {"odds-api": "abc123", "highlightly": "456"}
    assert record.identity_confidence in ("CONFIRMED", "FUZZY_MATCHED")
    assert record.home_team == "Norway"
    assert record.away_team == "Senegal"


def test_ambiguous_identity_blocked():
    events_by_source = {
        "odds-api": [_event("odds-api", "1", sport="football")],
        "highlightly": [_event("highlightly", "2", sport="tennis")],
    }

    blocked_records, filtered = _detect_ambiguous(events_by_source)

    assert len(blocked_records) == 1
    record = blocked_records[0]
    assert record.status == "BLOCKED_IDENTITY"
    assert record.identity_confidence == "AMBIGUOUS"
    assert "sport" in record.terminal_reason
    assert record.source_ids == {"odds-api": "1", "highlightly": "2"}

    # the ambiguous raw events are pulled out of the pool before dedup
    assert filtered["odds-api"] == []
    assert filtered["highlightly"] == []


def test_non_conflicting_events_are_not_ambiguous():
    events_by_source = {
        "odds-api": [_event("odds-api", "1")],
        "highlightly": [_event("highlightly", "2")],
    }

    blocked_records, filtered = _detect_ambiguous(events_by_source)

    assert blocked_records == []
    assert filtered["odds-api"] == events_by_source["odds-api"]
    assert filtered["highlightly"] == events_by_source["highlightly"]


def test_provider_team_ids_are_carried_from_source_raw_data():
    """Highlightly's /statistics endpoint hard-fails without its own native
    team ids, so discovery must carry them onto the EventRecord; without this
    ENRICH cannot call that provider at all."""
    hl = _event("highlightly", "1336361826")
    hl.raw_data = {
        "provider_match_id": "1336361826",
        "home_team_id": "3662637",
        "away_team_id": "16819097",
    }
    events_by_source = {"odds-api": [_event("odds-api", "abc123")], "highlightly": [hl]}
    merged = DeduplicationEngine().merge(events_by_source)
    record = _to_event_record(merged[0])

    assert record.provider_team_ids["highlightly"] == {"home": "3662637", "away": "16819097"}


def test_provider_team_ids_omitted_when_ids_are_missing_or_identical():
    """A source with no ids, or the same id on both sides, must not produce a
    provider_team_ids entry -- Highlightly rejects identical ids outright."""
    hl = _event("highlightly", "1336361826")
    hl.raw_data = {"home_team_id": "999", "away_team_id": "999"}
    merged = DeduplicationEngine().merge({"highlightly": [hl]})
    assert _to_event_record(merged[0]).provider_team_ids == {}


def test_odds_api_events_adapter_reads_the_free_events_endpoint():
    """The paid /odds endpoint answers 401 OUT_OF_USAGE_CREDITS once the
    monthly quota is spent, which zeroed out discovery; /events is free and
    carries every field EVENT_LIST_V1 needs."""
    import bet.simple_stats.discover as discover_module

    captured = {}

    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return [
                {
                    "id": "evt-1",
                    "sport_title": "EPL",
                    "commence_time": "2026-06-23T15:00:00Z",
                    "home_team": "Norway",
                    "away_team": "Senegal",
                },
                {  # different date -- must be filtered out
                    "id": "evt-2",
                    "sport_title": "EPL",
                    "commence_time": "2026-06-24T15:00:00Z",
                    "home_team": "A",
                    "away_team": "B",
                },
            ]

    def _fake_get(url, params=None, timeout=None, **kwargs):
        captured["url"] = url
        captured["params"] = params
        return _Resp()

    original = discover_module.requests.get
    discover_module.requests.get = _fake_get
    try:
        adapter = discover_module.OddsAPIEventsAdapter(api_key="k")
        events = adapter._fetch_for_key("soccer_epl", "football", "2026-06-23")
    finally:
        discover_module.requests.get = original

    assert captured["url"].endswith("/sports/soccer_epl/events")
    assert "markets" not in captured["params"]  # no odds requested, no credits spent
    assert [e.external_id for e in events] == ["evt-1"]
