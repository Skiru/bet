"""What OddsPapi v4 actually does, pinned against payloads captured from it.

Every fixture under ``tests/fixtures/oddspapi/`` is a real response recorded on
2026-09-01, trimmed but not reshaped. That matters more here than in most
places: the reason this provider sat unused for a month is that its behaviour
was inferred from prose rather than from a response, and the inference was
wrong in a way that looked like an outage.

The four facts these tests exist to keep true:

1. ``403 RESTRICTED_ACCESS`` is about a **bookmaker**, not an endpoint.
2. ``/odds`` takes ``fixtureId``, singular.
3. ``/fixtures`` needs a window and refuses one of ten days or more.
4. The quota is a **total** (250 on free), so ``remaining`` is a number a
   caller must be able to read before deciding to spend.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from bet.api_clients.oddspapi import (
    DEFAULT_BOOKMAKERS,
    MAX_FIXTURE_WINDOW_DAYS,
    SUPERBET_BOOKMAKER_SLUGS,
    MarketCatalog,
    OddsPapiClient,
    OddsPapiQuotaExhausted,
    OddsPapiRateLimited,
    OddsPapiRestrictedError,
    OddspapiConfig,
    _EndpointPacer,
    decode_bookmaker_odds,
    parse_account,
    parse_fixtures,
    superbet_event_id,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "oddspapi"


def load(name: str):
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


class FakeResponse:
    def __init__(self, payload, status_code=200, headers=None):
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FakeTransport:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0)


def client(*responses, **config_kwargs) -> tuple[OddsPapiClient, FakeTransport]:
    transport = FakeTransport(*responses)
    config = OddspapiConfig(api_key="secret-key", **config_kwargs)
    # Pacing is real time; a unit test must not spend it.
    return OddsPapiClient(config, transport, pacer=_EndpointPacer(0.0)), transport


# --- account and quota ------------------------------------------------------


def test_account_reads_plan_quota_and_entitlements_from_the_documented_shape():
    account = parse_account(load("account"))

    assert account.plan == "free"
    assert (account.request_count, account.request_limit) == (21, 250)
    assert account.remaining == 229
    assert account.active is True
    assert 10 in account.sport_ids


def test_account_picks_the_current_subscription_not_the_first_one():
    """A lapsed plan listed first must not report its entitlements as live."""
    payload = {
        "current_subscription_id": "live",
        "subscriptions": [
            {"subscription_id": "expired", "is_active": False, "plan": "pro",
             "request_limit": 100000, "request_count": 0, "bookmakers": {"superbet.pl": {}}},
            {"subscription_id": "live", "is_active": True, "plan": "free",
             "request_limit": 250, "request_count": 10, "bookmakers": {"superbet": {}}},
        ],
    }

    account = parse_account(payload)

    assert account.plan == "free"
    assert account.remaining == 240
    assert account.serves("superbet.pl") is False


def test_this_plan_cannot_serve_superbet_pl_and_falls_back_to_superbet():
    """The finding the whole integration turns on, kept as an assertion.

    ``superbet.pl`` is in the public bookmaker catalogue and is not in this
    plan's entitlements. Asking for it is a 403 on every odds call, which is
    why ``DEFAULT_BOOKMAKERS`` is not it.
    """
    account = parse_account(load("account"))

    assert account.serves("superbet.pl") is False
    assert account.serves("superbet") is True
    assert account.first_served(SUPERBET_BOOKMAKER_SLUGS) == "superbet"
    assert DEFAULT_BOOKMAKERS == ("superbet",)


def test_remaining_never_goes_negative():
    account = parse_account({
        "subscriptions": [{"is_active": True, "plan": "free",
                           "request_limit": 250, "request_count": 400}]
    })
    assert account.remaining == 0


# --- errors -----------------------------------------------------------------


RESTRICTED_BODY = {
    "error": {
        "message": "Restricted bookmaker(s).",
        "code": "RESTRICTED_ACCESS",
        "details": "Restricted bookmakers: superbet.pl. You do not have access to these bookmakers.",
    }
}


def test_a_restricted_bookmaker_is_not_a_dead_endpoint():
    api, _ = client(FakeResponse(RESTRICTED_BODY, status_code=403))

    with pytest.raises(OddsPapiRestrictedError) as caught:
        api.odds_for_fixture("id1", bookmaker="superbet.pl")

    # The slug, not a truncated "superbet" -- the terminator is a period
    # followed by whitespace, because the slugs are domains.
    assert caught.value.bookmakers == ("superbet.pl",)
    assert caught.value.code == "RESTRICTED_ACCESS"


def test_a_restricted_bookmaker_is_not_retried():
    """Retrying a permanent 403 spends quota to be told the same thing."""
    api, transport = client(FakeResponse(RESTRICTED_BODY, status_code=403))

    with pytest.raises(OddsPapiRestrictedError):
        api.odds_for_fixture("id1", bookmaker="superbet.pl")

    assert len(transport.calls) == 1


def test_rate_limiting_waits_the_body_s_retry_ms_not_a_missing_header(monkeypatch):
    """The wait is in the JSON body. There is no ``Retry-After`` header."""
    slept: list[float] = []
    monkeypatch.setattr("bet.api_clients.oddspapi.time.sleep", slept.append)
    body = {"error": {"code": "RATE_LIMITED", "message": "You are being rate limited.",
                      "details": "Please wait 1.90 seconds.", "retryMs": 1899}}
    api, transport = client(
        FakeResponse(body, status_code=429),
        FakeResponse({"fixtureId": "id1", "bookmakerOdds": {}}),
    )

    api.odds_for_fixture("id1")

    assert len(transport.calls) == 2
    assert slept == [pytest.approx(1.899)]


def test_rate_limited_surfaces_typed_when_the_retries_run_out(monkeypatch):
    monkeypatch.setattr("bet.api_clients.oddspapi.time.sleep", lambda _s: None)
    body = {"error": {"code": "RATE_LIMITED", "retryMs": 500}}
    api, _ = client(*[FakeResponse(body, status_code=429)] * 3, max_retries=2)

    with pytest.raises(OddsPapiRateLimited) as caught:
        api.odds_for_fixture("id1")
    assert caught.value.retry_seconds == pytest.approx(0.5)


def test_quota_exhaustion_is_its_own_error_because_waiting_will_not_help():
    api, _ = client(FakeResponse(
        {"error": {"code": "QUOTA_EXCEEDED", "message": "Monthly request limit reached."}},
        status_code=402,
    ))

    with pytest.raises(OddsPapiQuotaExhausted):
        api.account()


def test_the_api_key_never_reaches_an_error_message():
    api, _ = client(FakeResponse({"error": {"message": "boom secret-key"}}, status_code=500),
                    FakeResponse({"error": {"message": "boom secret-key"}}, status_code=500),
                    FakeResponse({"error": {"message": "boom secret-key"}}, status_code=500))

    with pytest.raises(Exception) as caught:
        api.account()
    assert "secret-key" not in str(caught.value)
    assert "[REDACTED]" in str(caught.value)


# --- request contracts ------------------------------------------------------


def test_odds_sends_fixture_id_singular():
    """``fixtureIds`` is rejected by the API with MISSING_PARAMETER."""
    api, transport = client(FakeResponse({"fixtureId": "id1", "bookmakerOdds": {}}))

    api.odds_for_fixture("id1", bookmaker="superbet")

    params = transport.calls[0][1]["params"]
    assert params["fixtureId"] == "id1"
    assert "fixtureIds" not in params
    assert params["bookmaker"] == "superbet"
    assert params["apiKey"] == "secret-key"


def test_fixtures_sends_the_required_window_and_the_prematch_filters():
    api, transport = client(FakeResponse([]))
    start = datetime(2026, 9, 1, tzinfo=UTC)

    api.fixtures("football", start, start + timedelta(days=1))

    params = transport.calls[0][1]["params"]
    assert params["sportId"] == "10"
    assert (params["from"], params["to"]) == ("2026-09-01T00:00:00Z", "2026-09-02T00:00:00Z")
    assert params["statusId"] == 0
    assert params["hasOdds"] == "true"


def test_fixtures_refuses_a_window_the_api_would_reject():
    api, transport = client(FakeResponse([]))
    start = datetime(2026, 9, 1, tzinfo=UTC)

    with pytest.raises(ValueError, match=str(MAX_FIXTURE_WINDOW_DAYS)):
        api.fixtures("football", start, start + timedelta(days=MAX_FIXTURE_WINDOW_DAYS))
    assert transport.calls == []


def test_tennis_resolves_to_sport_id_12():
    """Only football was mapped before, so tennis could not be asked about."""
    api, transport = client(FakeResponse([]))
    start = datetime(2026, 9, 1, tzinfo=UTC)

    api.fixtures("tennis", start, start + timedelta(days=1))

    assert transport.calls[0][1]["params"]["sportId"] == "12"


def test_odds_by_tournaments_is_the_bulk_form_and_skips_an_empty_list():
    api, transport = client(FakeResponse([{"fixtureId": "id1"}]))

    assert api.odds_by_tournaments([]) == []
    assert transport.calls == []

    api.odds_by_tournaments([7, 8], bookmaker="superbet")
    assert transport.calls[0][1]["params"]["tournamentIds"] == "7,8"


def test_the_pacer_spaces_calls_to_one_endpoint_and_not_across_endpoints():
    slept: list[float] = []
    clock = iter([0.0, 0.0, 0.5, 0.5])
    pacer = _EndpointPacer(2.0, sleep=slept.append, clock=lambda: next(clock))

    pacer.wait("/fixtures")
    pacer.wait("/odds")      # different endpoint: no wait
    pacer.wait("/fixtures")  # same endpoint, 0.5s later: waits the remainder

    assert slept == [pytest.approx(1.5)]


# --- fixtures and the Betradar key ------------------------------------------


def test_fixtures_expose_the_betradar_id_that_joins_to_superbet():
    fixtures = parse_fixtures(load("fixtures_football"))

    assert fixtures, "captured fixture payload is empty"
    assert all(item.betradar_id for item in fixtures), (
        "betradarId was populated on 100% of live soccer fixtures; the identity "
        "bridge is built on that being true"
    )
    west_ham = next(item for item in fixtures if item.home == "West Ham United")
    assert west_ham.betradar_id == "72339758"
    assert west_ham.start_time == datetime(2026, 9, 1, 18, 45, tzinfo=UTC)
    assert west_ham.has_odds is True


def test_fixtures_without_an_id_are_dropped_rather_than_given_a_blank_one():
    assert parse_fixtures([{"participant1Name": "A", "participant2Name": "B"}]) == []


# --- the market dictionary --------------------------------------------------


def test_market_ids_only_decode_through_the_catalogue():
    catalog = MarketCatalog.from_payload(load("markets_catalog"))
    payload = load("odds_superbet")

    rows = decode_bookmaker_odds(payload, bookmaker="superbet", catalog=catalog)

    assert rows, "the captured odds payload decodes to nothing"
    corners = [
        row for row in rows
        if row.market_type == "totals-corners" and row.period == "fulltime"
    ]
    ladder = sorted({row.handicap for row in corners})
    assert 9.5 in ladder
    over_95 = next(
        row for row in corners if row.handicap == 9.5 and row.outcome_name == "Over"
    )
    # Verified live: superbet.pl posted 1.68 for the same outcome at the same
    # moment. Same ladder, ~1% cheaper -- which is precisely why this feed
    # supplies identity and never the price the operator is shown.
    assert over_95.price == pytest.approx(1.69)


def test_an_uncatalogued_market_id_is_skipped_not_guessed():
    catalog = MarketCatalog.from_payload([])
    payload = load("odds_superbet")

    assert decode_bookmaker_odds(payload, bookmaker="superbet", catalog=catalog) == []


def test_asking_for_a_bookmaker_the_payload_does_not_carry_returns_nothing():
    catalog = MarketCatalog.from_payload(load("markets_catalog"))
    payload = load("odds_superbet")

    assert decode_bookmaker_odds(payload, bookmaker="superbet.pl", catalog=catalog) == []


def test_the_bookmaker_fixture_id_is_superbet_s_own_event_id():
    """Verified live: OddsPapi fixture id1000001872339758 -> Superbet 13777819."""
    assert superbet_event_id(load("odds_superbet"), bookmaker="superbet") == "13777819"
    assert superbet_event_id(load("odds_superbet"), bookmaker="superbet.pl") is None
