"""Referee profiles, squad availability, and the fixture context that used to be
parsed and thrown away.

Every payload here was captured live from sports.bzzoiro.com on 2026-08-30:
referee 1897 (Peter Bankes), team 17 (Manchester United, 39 players of whom 5
were unavailable), and an ``/events/`` row for Deportivo Pasto v Deportivo
Pereira.

The property under test throughout is the one that makes this data safe to add:
**none of it is an observation.** Referee averages and injury lists reach the
dossier's context slots and never ``metrics``, so no hit rate can be counted
from them and ``p_low`` cannot move.
"""
from types import SimpleNamespace

import pytest

from bet.api_clients.bzzoiro import BzzoiroClient
from bet.api_clients.rate_limiter import RateLimiter
from bet.integration.source_result import SourceOperationResult, SourceResultStatus
from bet.simple_stats import providers
from bet.simple_stats.contracts import EventRecord, FixtureContext
from bet.simple_stats.enrich import _dossier_for_event, _fixture_extras_for_event
from bet.simple_stats.providers import (
    FetchOutcome,
    RunBudget,
    fetch_bzzoiro_referee,
    fetch_bzzoiro_squad_availability,
    reset_bzzoiro_referee_cache,
)

# --- live-shaped payloads -------------------------------------------------

REFEREE_PAYLOAD = {
    "id": 1897,
    "name": "Peter Bankes",
    "country": "England",
    "nationality_a3": "",
    "birthdate": None,
    "matches": 27,
    "total_yellow_cards": 112,
    "total_red_cards": 6,
    "avg_yellow_per_match": 4.15,
    "avg_red_per_match": 0.22,
    "avg_goals_per_match": 2.81,
    "avg_fouls_per_match": 22.1,
    "career_games": 345,
    "career_yellow_cards": 1362,
    "career_red_cards": 36,
}

SQUAD_PAYLOAD = {
    "team_id": 17,
    "count": 4,
    "players": [
        {
            "id": 1795,
            "name": "Diogo Dalot",
            "position": "D",
            "availability": "available",
            "injury_type": "",
            "injury_expected_return": None,
        },
        {
            "id": 1790,
            "name": "Matthijs de Ligt",
            "position": "D",
            "availability": "injured",
            "injury_type": "Back Injury",
            "injury_expected_return": "2026-09-30",
        },
        {
            "id": 4118,
            "name": "Harry Maguire",
            "position": "D",
            # The provider publishes no report for some players. That is not
            # evidence of fitness and must not be counted as such.
            "availability": "",
            "injury_type": "",
            "injury_expected_return": None,
        },
        {
            "id": 1792,
            "name": "Amad Diallo",
            "position": "M",
            "availability": "suspended",
            "injury_type": "",
            "injury_expected_return": None,
        },
    ],
}

EVENTS_PAYLOAD = {
    "count": 1,
    "results": [
        {
            "id": 220103,
            "league_id": 80,
            "season_id": 1570,
            "home_team_id": 3419,
            "home_team": "Deportivo Pasto",
            "away_team_id": 4780,
            "away_team": "Deportivo Pereira",
            "referee_id": 2942,
            "venue_id": 1654,
            "event_date": "2026-08-31T23:00:00+00:00",
            "status": "notstarted",
            "is_local_derby": False,
            "is_neutral_ground": False,
            "travel_distance_km": 436,
            "weather": {
                "code": 51,
                "description": None,
                "wind_speed": 8.2,
                "temperature_c": 13,
            },
        }
    ],
}


def _client(monkeypatch, tmp_path, payloads):
    """A BzzoiroClient whose HTTP layer replays ``{endpoint: payload}``."""
    import json as _json

    client = BzzoiroClient(rate_limiter=RateLimiter(usage_dir=tmp_path / "usage"))
    client.api_key = "test-key"
    calls = []

    def _fake(*, endpoint, params, operation, source_event_id=None):
        calls.append((endpoint, dict(params or {})))
        payload = payloads.get(endpoint)
        if payload is None:
            return SourceOperationResult(
                status=SourceResultStatus.NOT_FOUND,
                provider="bzzoiro",
                operation=operation,
                error_code="http_404",
            )
        return SourceOperationResult(
            status=SourceResultStatus.SUCCESS,
            value=_json.loads(_json.dumps(payload)),
            provider="bzzoiro",
            operation=operation,
            http_status=200,
        )

    monkeypatch.setattr(client, "_request_with_evidence", _fake)
    return client, calls


@pytest.fixture(autouse=True)
def _clear_referee_cache():
    reset_bzzoiro_referee_cache()
    yield
    reset_bzzoiro_referee_cache()


# --- client parsing -------------------------------------------------------


def test_referee_profile_separates_averages_from_counts(monkeypatch, tmp_path):
    """4.15 yellows a match is a float; 27 matches is not.

    Rendering the sample size as ``27.0`` invites it to be read as another
    average, and the sample size is the one field that says whether to believe
    the averages at all.
    """
    client, _ = _client(monkeypatch, tmp_path, {"/referees/1897/": REFEREE_PAYLOAD})
    result = client.get_referee_result(1897)

    assert result.status is SourceResultStatus.SUCCESS
    ref = result.value["referee"]
    assert ref["name"] == "Peter Bankes"
    assert ref["avg_yellow_per_match"] == 4.15
    assert ref["avg_fouls_per_match"] == 22.1
    assert ref["matches"] == 27 and isinstance(ref["matches"], int)
    assert ref["career_games"] == 345 and isinstance(ref["career_games"], int)


def test_referee_without_averages_is_valid_empty_not_an_error(monkeypatch, tmp_path):
    """A referee below the provider's publication floor is a real state.

    Nothing is malformed -- there is simply nothing to read -- so this must not
    look like a schema failure, which is what would get the endpoint blamed.
    """
    thin = {"id": 4242, "name": "New Official", "matches": 2}
    client, _ = _client(monkeypatch, tmp_path, {"/referees/4242/": thin})
    result = client.get_referee_result(4242)

    assert result.status is SourceResultStatus.VALID_EMPTY
    assert result.value["referee"]["avg_yellow_per_match"] is None


def test_squad_counts_unavailable_and_keeps_unknown_separate(monkeypatch, tmp_path):
    """An empty ``availability`` is not fitness.

    Collapsing "no report published" into "available" would let a thinly
    covered squad read as a fully fit one, which is the failure that matters:
    it is silent and it flatters the bet.
    """
    client, _ = _client(monkeypatch, tmp_path, {"/teams/17/squad/": SQUAD_PAYLOAD})
    result = client.get_team_squad_result(17)

    assert result.status is SourceResultStatus.SUCCESS
    value = result.value
    assert value["squad_size"] == 4
    assert value["unavailable_count"] == 2  # injured + suspended
    assert value["availability_unknown_count"] == 1  # Maguire, no report
    names = {p["player_name"] for p in value["unavailable"]}
    assert names == {"Matthijs de Ligt", "Amad Diallo"}
    de_ligt = next(p for p in value["unavailable"] if p["player_name"] == "Matthijs de Ligt")
    assert de_ligt["injury_type"] == "Back Injury"
    assert de_ligt["injury_expected_return"] == "2026-09-30"


def test_events_row_keeps_the_context_it_used_to_discard(monkeypatch, tmp_path):
    """referee_id and friends arrive in a page discovery already pays for.

    This is the whole economics of the feature: the block costs no request, and
    dropping it was the reason cards and fouls had no source outside the two
    clubs' own histories.
    """
    client, _ = _client(monkeypatch, tmp_path, {"/events/": EVENTS_PAYLOAD})
    result = client.get_events_result(date_from="2026-08-31", date_to="2026-08-31")

    row = result.value["matches"][0]
    assert row["referee_id"] == "2942"
    assert row["venue_id"] == "1654"
    assert row["is_local_derby"] is False
    assert row["is_neutral_ground"] is False
    assert row["travel_distance_km"] == 436.0
    assert row["weather"]["temperature_c"] == 13


# --- provider layer -------------------------------------------------------


def test_referee_profile_is_cached_across_fixtures(monkeypatch, tmp_path):
    """One official works several of a slate's fixtures; pay once."""
    client, calls = _client(monkeypatch, tmp_path, {"/referees/1897/": REFEREE_PAYLOAD})
    monkeypatch.setattr(providers, "get_client", lambda *a, **k: client)

    first, gaps_a = fetch_bzzoiro_referee("1897", RateLimiter(usage_dir=tmp_path / "u"))
    second, gaps_b = fetch_bzzoiro_referee("1897", RateLimiter(usage_dir=tmp_path / "u"))

    assert first == second
    assert first["avg_yellow_per_match"] == 4.15
    assert gaps_a == [] and gaps_b == []
    assert len(calls) == 1, "second fixture with the same referee re-paid for the profile"


def test_missing_referee_is_a_gap_not_a_crash(monkeypatch, tmp_path):
    client, _ = _client(monkeypatch, tmp_path, {})  # every endpoint 404s
    monkeypatch.setattr(providers, "get_client", lambda *a, **k: client)

    profile, gaps = fetch_bzzoiro_referee("9999", RateLimiter(usage_dir=tmp_path / "u"))

    assert profile is None
    assert any("referee profile" in g for g in gaps)


def test_referee_respects_the_run_budget(monkeypatch, tmp_path):
    """Exhaustion is a gap, not an exception -- and the override has to be
    lowered explicitly to reach it.

    ``RunBudget(limit=0)`` alone does **not** stop a bzzoiro call:
    ``limit_for`` takes ``max(limit, RUN_BUDGET_OVERRIDES["bzzoiro"])``, which
    is 20000. That is deliberate on the budget's side, and it is why this test
    passes an explicit override rather than a low limit -- a test that used the
    limit alone would silently assert nothing.
    """
    client, calls = _client(monkeypatch, tmp_path, {"/referees/1897/": REFEREE_PAYLOAD})
    monkeypatch.setattr(providers, "get_client", lambda *a, **k: client)
    budget = RunBudget(limit=0, overrides={"bzzoiro": 0})

    profile, gaps = fetch_bzzoiro_referee(
        "1897", RateLimiter(usage_dir=tmp_path / "u"), budget
    )

    assert profile is None
    assert calls == []
    assert any("run budget exhausted" in g for g in gaps)


def test_default_run_budget_does_not_throttle_referee_lookups(monkeypatch, tmp_path):
    """The uncapped-football override reaches this path too.

    Football is uncapped on the PRO plan, so a slate's worth of referee lookups
    must not be rationed by the generic 100-a-run default.
    """
    client, calls = _client(monkeypatch, tmp_path, {"/referees/1897/": REFEREE_PAYLOAD})
    monkeypatch.setattr(providers, "get_client", lambda *a, **k: client)

    profile, gaps = fetch_bzzoiro_referee(
        "1897", RateLimiter(usage_dir=tmp_path / "u"), RunBudget(limit=0)
    )

    assert profile is not None and gaps == []
    assert len(calls) == 1


def test_squad_availability_labels_its_side(monkeypatch, tmp_path):
    client, _ = _client(monkeypatch, tmp_path, {"/teams/17/squad/": SQUAD_PAYLOAD})
    monkeypatch.setattr(providers, "get_client", lambda *a, **k: client)

    block, gaps = fetch_bzzoiro_squad_availability(
        "17", "away", RateLimiter(usage_dir=tmp_path / "u")
    )

    assert gaps == []
    assert block["side"] == "away"
    assert block["unavailable_count"] == 2
    assert block["availability_unknown_count"] == 1


# --- enrich wiring --------------------------------------------------------


def _event(**overrides):
    kwargs = dict(
        event_id="evt-1",
        sport="football",
        competition="Premier League",
        home_team="Manchester United",
        away_team="Arsenal",
        start_time="2026-08-31T23:00:00+00:00",
        source_ids={"bzzoiro": "220103"},
        provider_team_ids={"bzzoiro": {"home": "17", "away": "42"}},
        identity_confidence="CONFIRMED",
        status="ACTIVE",
        fixture_context=FixtureContext(
            referee_id="1897",
            venue_id="1654",
            is_local_derby=True,
            travel_distance_km=436.0,
        ),
    )
    kwargs.update(overrides)
    return EventRecord(**kwargs)


def test_extras_resolve_referee_and_both_squads(monkeypatch, tmp_path):
    client, calls = _client(
        monkeypatch,
        tmp_path,
        {
            "/referees/1897/": REFEREE_PAYLOAD,
            "/teams/17/squad/": SQUAD_PAYLOAD,
            "/teams/42/squad/": SQUAD_PAYLOAD,
        },
    )
    monkeypatch.setattr(providers, "get_client", lambda *a, **k: client)

    extras = _fixture_extras_for_event(_event(), RateLimiter(usage_dir=tmp_path / "u"), None)

    assert extras.referee.name == "Peter Bankes"
    assert extras.referee.avg_fouls_per_match == 22.1
    assert {s.side for s in extras.squad_availability} == {"home", "away"}
    assert extras.data_gaps == []
    assert len(calls) == 3


def test_tennis_never_spends_its_quota_here(monkeypatch, tmp_path):
    """Tennis has no referee endpoint and the one real quota ceiling left."""
    client, calls = _client(monkeypatch, tmp_path, {"/referees/1897/": REFEREE_PAYLOAD})
    monkeypatch.setattr(providers, "get_client", lambda *a, **k: client)

    event = _event(
        sport="tennis",
        home_team=None,
        away_team=None,
        player_one="A",
        player_two="B",
    )
    extras = _fixture_extras_for_event(event, RateLimiter(usage_dir=tmp_path / "u"), None)

    assert extras.referee is None
    assert extras.squad_availability == []
    assert calls == []


def test_context_reaches_the_dossier_but_never_the_metrics(monkeypatch, tmp_path):
    """The point of the whole feature, asserted directly.

    Referee averages and injury lists are circumstances, not observations. If
    they ever landed in ``metrics`` they would be counted into a hit rate, and
    ``p_low`` would then rest on a number describing an official's season rather
    than on matches this pipeline actually watched.
    """
    client, _ = _client(
        monkeypatch,
        tmp_path,
        {
            "/referees/1897/": REFEREE_PAYLOAD,
            "/teams/17/squad/": SQUAD_PAYLOAD,
            "/teams/42/squad/": SQUAD_PAYLOAD,
        },
    )
    monkeypatch.setattr(providers, "get_client", lambda *a, **k: client)
    event = _event()
    extras = _fixture_extras_for_event(event, RateLimiter(usage_dir=tmp_path / "u"), None)

    buckets = {k: FetchOutcome() for k in ("team_a", "team_b", "h2h")}
    dossier = _dossier_for_event(event, buckets, None, None, extras)

    assert dossier.referee.avg_yellow_per_match == 4.15
    assert dossier.fixture_context.is_local_derby is True
    assert dossier.fixture_context.referee_id == "1897"
    assert len(dossier.squad_availability) == 2
    # The load-bearing assertion.
    assert dossier.metrics == {}


def test_dossier_keeps_context_even_when_every_provider_failed(monkeypatch, tmp_path):
    """A BLOCKED fixture that is a derby is still worth saying so about.

    ``fixture_context`` is carried from EVENT_LIST at no request cost, so it
    does not depend on any fetch succeeding.
    """
    event = _event()
    buckets = {k: FetchOutcome() for k in ("team_a", "team_b", "h2h")}

    dossier = _dossier_for_event(event, buckets, None, None, None)

    assert dossier.readiness == "BLOCKED"
    assert dossier.referee is None
    assert dossier.fixture_context.is_local_derby is True
