"""Tests for bet.simple_stats.discover: dedup merging and identity classification."""
from datetime import datetime, timezone

import pytest

from bet.discovery.dedup import DeduplicationEngine
from bet.discovery.models import DiscoveredEvent

from bet.simple_stats.discover import (
    _canonicalize_competition_names,
    _competition_canonical_map,
    _detect_ambiguous,
    _event_id,
    _to_event_record,
    reset_competition_canonical_cache,
)

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


def _bzzoiro_events_payload():
    return {
        "count": 2,
        "results": [
            {
                "id": 587706,
                "league_id": 7,
                "season_id": 1,
                "home_team_id": 100,
                "away_team_id": 134,
                "home_team": "Olympique Lyonnais",
                "away_team": "Fenerbahçe",
                "home_score": None,
                "away_score": None,
                "event_date": "2026-08-26T19:00:00+00:00",
                "status": "notstarted",
            },
            {  # unusable: both sides are the same team id
                "id": 999,
                "league_id": 7,
                "season_id": 1,
                "home_team_id": 5,
                "away_team_id": 5,
                "home_team": "X",
                "away_team": "X",
                "event_date": "2026-08-26T19:00:00+00:00",
                "status": "notstarted",
            },
        ],
    }


def _stub_bzzoiro_adapter(monkeypatch, events_payload, leagues_payload):
    """A BzzoiroDiscoveryAdapter whose client replays two canned responses."""
    from bet.api_clients.rate_limiter import RateLimiter
    from bet.integration.source_result import SourceOperationResult, SourceResultStatus

    from bet.simple_stats.discover import BzzoiroDiscoveryAdapter

    adapter = BzzoiroDiscoveryAdapter(RateLimiter())
    adapter._client.api_key = "test-key"

    def _fake(*, endpoint, params, operation, source_event_id=None):
        payload = {"/events/": events_payload, "/leagues/": leagues_payload}.get(endpoint)
        if payload is None:
            return SourceOperationResult(
                status=SourceResultStatus.NOT_FOUND, provider="bzzoiro", operation=operation
            )
        return SourceOperationResult(
            status=SourceResultStatus.SUCCESS,
            value=payload,
            provider="bzzoiro",
            operation=operation,
            http_status=200,
        )

    monkeypatch.setattr(adapter._client, "_request_with_evidence", _fake)
    return adapter


def test_bzzoiro_adapter_names_the_competition_from_the_league_catalogue(monkeypatch):
    """``/events/`` gives only ``league_id``, and EventRecord.competition feeds
    the event id, the dedup key and every downstream competition lookup. One
    cached catalogue call resolves all of a day's leagues."""
    leagues = {
        "count": 1,
        "results": [{"id": 7, "name": "Champions League", "country": "Europe"}],
    }
    adapter = _stub_bzzoiro_adapter(monkeypatch, _bzzoiro_events_payload(), leagues)

    events = adapter._fetch_events_impl("2026-08-26", "football")
    assert len(events) == 1  # the same-team-id row is rejected
    assert events[0].competition == "Champions League"
    assert events[0].raw_data["home_team_id"] == "100"
    assert events[0].raw_data["away_team_id"] == "134"

    # Second call must not re-fetch the catalogue.
    assert adapter._league_name("7") == "Champions League"


def test_bzzoiro_competition_stays_unique_when_the_catalogue_is_unavailable(monkeypatch):
    """An empty competition name would collapse every fixture of the day into
    one competition -- and the dedup key and event id are built from it."""
    adapter = _stub_bzzoiro_adapter(monkeypatch, _bzzoiro_events_payload(), None)
    events = adapter._fetch_events_impl("2026-08-26", "football")
    assert events[0].competition == "bzzoiro-league-7"
    assert adapter.last_errors


def test_bzzoiro_native_ids_reach_the_event_record(monkeypatch):
    """Same generic lift as Highlightly's, with no provider-specific code in
    ``_to_event_record``: without these ids ENRICH builds no bzzoiro task."""
    leagues = {"count": 1, "results": [{"id": 7, "name": "Champions League", "country": "Europe"}]}
    adapter = _stub_bzzoiro_adapter(monkeypatch, _bzzoiro_events_payload(), leagues)
    discovered = adapter._fetch_events_impl("2026-08-26", "football")

    merged = DeduplicationEngine().merge({"bzzoiro": discovered})
    record = _to_event_record(merged[0])
    assert record.provider_team_ids["bzzoiro"] == {"home": "100", "away": "134"}
    assert record.source_ids["bzzoiro"] == "587706"


# docs/PLAN_BOGATE_STATYSTYKI.md Faza 6: competition-name canonicalization.


@pytest.fixture(autouse=True)
def _clear_competition_canonical_cache():
    reset_competition_canonical_cache()
    yield
    reset_competition_canonical_cache()


def test_competition_canonical_map_is_exact_pin_only():
    """The real config file: known duplicate spellings are pinned, and bare
    ambiguous names (which the ESPN table also refuses to pin, for the same
    reason) are NOT silently folded into a guessed country."""
    canonical = _competition_canonical_map()
    assert canonical["EPL"] == "Premier League"
    assert canonical["Veikkausliiga - Finland"] == "Veikkausliiga"
    assert canonical["Danish Superliga"] == "Denmark Superliga"
    assert canonical["Allsvenskan - Sweden"] == "Allsvenskan"
    # Romania and Denmark both call their top flight "Superliga" -- folding
    # the bare name to either country would repeat the 2026-08-28 incident.
    assert "Superliga" not in canonical


def test_canonicalize_competition_names_unifies_a_known_duplicate_pair():
    """Two providers naming the same real match "EPL" and "Premier League"
    must produce the same event_id once canonicalized, or the merge/ESPN
    layers downstream see two fixtures instead of one."""
    epl = _event("odds-api", "1", home="Aston Villa", away="Arsenal")
    epl.competition = "EPL"
    prem = _event("highlightly", "2", home="Aston Villa", away="Arsenal")
    prem.competition = "Premier League"
    events_by_source = {"odds-api": [epl], "highlightly": [prem]}

    _canonicalize_competition_names(events_by_source)

    assert epl.competition == "Premier League"
    assert prem.competition == "Premier League"
    participants = "aston villa|arsenal"
    epl_id = _event_id(
        "football", epl.competition, participants, epl.kickoff.isoformat()
    )
    prem_id = _event_id(
        "football", prem.competition, participants, prem.kickoff.isoformat()
    )
    assert epl_id == prem_id


def test_canonicalize_competition_names_leaves_unknown_names_untouched():
    ev = _event("odds-api", "1")
    ev.competition = "Some League Nobody Has Pinned Yet"
    events_by_source = {"odds-api": [ev]}

    _canonicalize_competition_names(events_by_source)

    assert ev.competition == "Some League Nobody Has Pinned Yet"


def test_canonicalize_competition_names_never_guesses_bare_superliga():
    """Regression guard for the 2026-08-28 incident: bare "Superliga" must
    reach ESPN resolution unresolved, not silently become Denmark's or
    Romania's."""
    ev = _event("odds-api", "1")
    ev.competition = "Superliga"
    events_by_source = {"odds-api": [ev]}

    _canonicalize_competition_names(events_by_source)

    assert ev.competition == "Superliga"


# Stakes context (round_name/group_name/previous_leg_event_id) carried
# through from bzzoiro's raw fixture row, at zero extra request cost.


def test_fixture_context_survives_a_missing_referee_id():
    """A fixture context field earns the whole block by source, not by
    referee_id being set: a fixture whose referee is not yet assigned must
    not lose is_local_derby/weather/stakes context along with it. Verified
    live 2026-08-31: Sutton United - Wealdstone had referee_id=None and
    is_local_derby=True at the same time."""
    ev = _event("bzzoiro", "1")
    ev.raw_data = {
        "referee_id": None,
        "is_local_derby": True,
        "round_name": "Final",
        "group_name": None,
        "previous_leg_event_id": "999",
    }
    merged = DeduplicationEngine().merge({"bzzoiro": [ev]})
    record = _to_event_record(merged[0])

    assert record.fixture_context is not None
    assert record.fixture_context.referee_id is None
    assert record.fixture_context.is_local_derby is True
    assert record.fixture_context.round_name == "Final"
    assert record.fixture_context.previous_leg_event_id == "999"


def test_fixture_context_is_absent_for_a_non_bzzoiro_source():
    ev = _event("highlightly", "1")
    ev.raw_data = {"round_name": "Final"}
    merged = DeduplicationEngine().merge({"highlightly": [ev]})
    record = _to_event_record(merged[0])

    assert record.fixture_context is None
