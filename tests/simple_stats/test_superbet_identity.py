"""The OddsPapi identity bridge: what it recovers, and what it refuses.

The bridge exists to name a Superbet fixture by a Betradar id instead of by
spelling. Two properties matter more than the happy path:

* it is **optional** -- no key, no quota, a dead provider, a crashed call, all
  end in an empty bridge and the fixture matcher behaving exactly as it did
  before the module existed; and
* it **refuses** rather than guesses. A wrong pairing is not a missing column,
  it is a real price filed against the wrong match.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from bet.api_clients.oddspapi import OddsPapiFixture, parse_account
from bet.simple_stats.contracts import EventListV1
from bet.simple_stats.superbet_identity import (
    IdentityBridge,
    build_identity_bridge,
    disabled,
    read_cached_account,
    write_cached_account,
)

ACCOUNT = json.loads(
    (Path(__file__).resolve().parents[1] / "fixtures" / "oddspapi" / "account.json").read_text()
)


def event(event_id, home, away, start="2026-09-01T18:45:00+00:00", sport="football"):
    return {
        "event_id": event_id, "sport": sport, "competition": "Championship",
        "home_team": home if sport == "football" else None,
        "away_team": away if sport == "football" else None,
        "player_one": home if sport == "tennis" else None,
        "player_two": away if sport == "tennis" else None,
        "start_time": start, "source_ids": {}, "provider_team_ids": {},
        "identity_confidence": "CONFIRMED", "status": "ACTIVE", "terminal_reason": None,
    }


def event_list(*events, date="2026-09-01"):
    return EventListV1.model_validate({
        "run_id": "RID", "generated_at": f"{date}T00:00:00+00:00", "date": date,
        "sports": sorted({e["sport"] for e in events}) or ["football"],
        "events": list(events),
    })


def fixture(betradar, home, away, minute=45, sport_id=10):
    return OddsPapiFixture(
        fixture_id=f"id{betradar}", sport_id=sport_id,
        start_time=datetime(2026, 9, 1, 18, minute, tzinfo=UTC),
        home=home, away=away, betradar_id=str(betradar), has_odds=True,
    )


class FakeApi:
    """Stands in for OddsPapiClient. Records what it was asked for."""

    def __init__(self, fixtures_by_sport=None, *, account_payload=ACCOUNT, fail=None):
        self._fixtures = fixtures_by_sport or {}
        self._account_payload = account_payload
        self._fail = fail
        self.request_count = 0
        self.sports_asked: list[str] = []

    def account(self):
        self.request_count += 1
        return parse_account(self._account_payload)

    def fixtures(self, sport, start, end, **kwargs):
        self.request_count += 1
        self.sports_asked.append(sport)
        if self._fail:
            raise self._fail
        return self._fixtures.get(sport, [])


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    """Never read or write the real account cache from a test."""
    monkeypatch.setenv("ODDSPAPI_ACCOUNT_CACHE", str(tmp_path / "account.json"))
    monkeypatch.setenv("ODDSPAPI_API_KEY", "test-key")


# --- the happy path ---------------------------------------------------------


def test_the_bridge_resolves_our_events_to_betradar_ids():
    events = event_list(
        event("ours-1", "West Ham United", "Wolverhampton Wanderers"),
        event("ours-2", "Universitatea Cluj", "Petrolul Ploiesti"),
    )
    api = FakeApi({"football": [
        fixture(72339758, "West Ham United", "Wolverhampton Wanderers"),
        fixture(74019308, "FC Universitatea Cluj", "FC Petrolul Ploiesti"),
    ]})

    bridge = build_identity_bridge(events, client=api)

    assert bridge.enabled is True
    assert bridge.betradar_by_event_id == {"ours-1": "72339758", "ours-2": "74019308"}
    assert bridge.as_metrics()["oddspapi_bridge_events"] == 2


def test_only_bridgeable_sports_are_asked_about():
    """One request per sport. Asking about a sport nothing joins is waste."""
    events = event_list(
        event("f", "A FC", "B FC"),
        event("t", "Osaka, Naomi", "Zakharova, Anastasia", sport="tennis"),
    )
    api = FakeApi({"football": [], "tennis": []})

    build_identity_bridge(events, client=api)

    assert sorted(api.sports_asked) == ["football", "tennis"]


def test_an_empty_event_list_costs_no_request():
    """The contract only admits football and tennis, so "no bridgeable sport"
    is reachable exactly one way: an event list with nothing in it."""
    api = FakeApi()

    bridge = build_identity_bridge(event_list(), client=api)

    assert bridge.enabled is False
    assert api.request_count == 0


# --- refusals ---------------------------------------------------------------


def test_two_plausible_fixtures_resolve_to_neither():
    """A coin flip between two Superbet fixtures is worse than no bridge."""
    events = event_list(event("ours", "Atletico", "Nacional"))
    api = FakeApi({"football": [
        fixture(1, "Atletico Nacional", "Nacional Atletico", minute=45),
        fixture(2, "Atletico Nacional", "Nacional Atletico", minute=50),
    ]})

    assert build_identity_bridge(events, client=api).betradar_by_event_id == {}


def test_one_betradar_id_claimed_by_two_of_our_events_resolves_to_neither():
    """Then our own event list has a duplicate, and neither claim is safe."""
    events = event_list(
        event("ours-a", "West Ham United", "Wolverhampton Wanderers"),
        event("ours-b", "West Ham", "Wolverhampton", start="2026-09-01T18:50:00+00:00"),
    )
    api = FakeApi({"football": [fixture(72339758, "West Ham United", "Wolverhampton Wanderers")]})

    assert build_identity_bridge(events, client=api).betradar_by_event_id == {}


def test_a_fixture_outside_the_kickoff_tolerance_is_not_a_match():
    events = event_list(event("ours", "West Ham United", "Wolverhampton Wanderers"))
    api = FakeApi({"football": [
        # Same names, four hours later: for football that is a different fixture.
        OddsPapiFixture(
            fixture_id="idX", sport_id=10,
            start_time=datetime(2026, 9, 1, 22, 45, tzinfo=UTC),
            home="West Ham United", away="Wolverhampton Wanderers", betradar_id="9",
        ),
    ]})

    assert build_identity_bridge(events, client=api).betradar_by_event_id == {}


def test_a_fixture_with_no_betradar_id_cannot_bridge():
    events = event_list(event("ours", "West Ham United", "Wolverhampton Wanderers"))
    api = FakeApi({"football": [
        OddsPapiFixture(
            fixture_id="idX", sport_id=10,
            start_time=datetime(2026, 9, 1, 18, 45, tzinfo=UTC),
            home="West Ham United", away="Wolverhampton Wanderers", betradar_id=None,
        ),
    ]})

    bridge = build_identity_bridge(events, client=api)
    assert bridge.betradar_by_event_id == {}
    assert any("betradarId" in note for note in bridge.notes)


# --- degrading, never failing -----------------------------------------------


def test_a_missing_credential_disables_the_bridge_rather_than_raising(monkeypatch):
    # ``oddspapi`` did ``from .env import get_env``, so the name to patch is the
    # one bound in *that* module. Patching ``bet.api_clients.env.get_env``
    # instead is a no-op -- and the test then quietly makes a live call.
    monkeypatch.setattr("bet.api_clients.oddspapi.get_env", lambda *_a, **_k: "")

    bridge = build_identity_bridge(event_list(event("ours", "A FC", "B FC")))

    assert bridge.enabled is False
    assert bridge.betradar_by_event_id == {}


def test_a_failing_fixtures_call_leaves_the_bridge_empty_and_says_so():
    events = event_list(event("ours", "A FC", "B FC"))
    api = FakeApi({"football": []}, fail=RuntimeError("provider down"))

    bridge = build_identity_bridge(events, client=api)

    assert bridge.betradar_by_event_id == {}
    assert any("provider down" in note for note in bridge.notes)


def test_a_failing_account_probe_disables_the_bridge():
    class Broken(FakeApi):
        def account(self):
            raise RuntimeError("401")

    bridge = build_identity_bridge(event_list(event("ours", "A FC", "B FC")), client=Broken())

    assert bridge.enabled is False


# --- the quota reserve ------------------------------------------------------


def test_the_bridge_refuses_to_spend_the_last_requests_on_a_nice_to_have():
    """The free plan is 250 requests in *total*, so the floor is real."""
    thin = json.loads(json.dumps(ACCOUNT))
    thin["subscriptions"][0]["request_count"] = 249
    api = FakeApi({"football": [fixture(1, "A FC", "B FC")]}, account_payload=thin)

    bridge = build_identity_bridge(event_list(event("ours", "A FC", "B FC")), client=api)

    assert bridge.enabled is False
    assert "quota too low" in bridge.notes[0]
    assert api.sports_asked == [], "no fixtures call should have been made"


def test_a_reserve_of_zero_lets_the_last_requests_through():
    thin = json.loads(json.dumps(ACCOUNT))
    thin["subscriptions"][0]["request_count"] = 249
    api = FakeApi({"football": [fixture(1, "A FC", "B FC")]}, account_payload=thin)

    bridge = build_identity_bridge(
        event_list(event("ours", "A FC", "B FC")), client=api, min_quota_reserve=0
    )

    assert bridge.enabled is True


# --- the account cache ------------------------------------------------------


def test_a_fresh_cached_account_saves_the_probe_request():
    api = FakeApi({"football": [fixture(1, "West Ham United", "Wolverhampton Wanderers")]})
    events = event_list(event("ours", "West Ham United", "Wolverhampton Wanderers"))

    first = build_identity_bridge(events, client=api)
    second = build_identity_bridge(events, client=FakeApi({"football": api._fixtures["football"]}))

    assert first.requests_made == 2  # account + fixtures
    assert second.requests_made == 1  # fixtures only
    assert any("cache" in note for note in second.notes)


def test_a_stale_cached_account_is_ignored():
    now = datetime(2026, 9, 1, 12, tzinfo=UTC)
    write_cached_account({"remaining": 200}, now=now - timedelta(hours=7))

    assert read_cached_account(now=now) is None


def test_a_corrupt_cache_file_is_ignored_rather_than_fatal(tmp_path, monkeypatch):
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")
    monkeypatch.setenv("ODDSPAPI_ACCOUNT_CACHE", str(path))

    assert read_cached_account() is None


# --- the empty bridge is a valid bridge -------------------------------------


def test_a_disabled_bridge_is_falsy_and_carries_its_reason():
    bridge = disabled("no key")

    assert not bridge
    assert bridge.as_metrics() == {
        "oddspapi_bridge_enabled": False,
        "oddspapi_bridge_events": 0,
        "oddspapi_bridge_requests": 0,
        "oddspapi_quota_remaining": None,
        "oddspapi_bridge_notes": ["no key"],
    }
    assert IdentityBridge().betradar_by_event_id == {}
