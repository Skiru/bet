from __future__ import annotations

import pytest

from bet.api_clients.oddspapi import OddspapiConfig, OddsPapiClient, OddsPapiError, normalize_oddspapi_payload


class FakeResponse:
    headers = {}

    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


class FakeTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0)


def test_normalize_oddspapi_nested_superbet_payload():
    payload = {
        "data": [
            {
                "id": "evt-1",
                "sport": "football",
                "startTime": "2026-06-26T18:00:00Z",
                "homeTeam": "Team A",
                "awayTeam": "Team B",
                "odds": {
                    "Superbet PL": {
                        "name": "Superbet PL",
                        "markets": {
                            "moneyline": {"Team A": 1.91, "Draw": 3.4, "Team B": 4.2},
                            "over_under": {
                                "Over 2.5": {"odds": 2.05, "line": 2.5},
                                "Under 2.5": {"odds": 1.82, "line": 2.5},
                            },
                        },
                    }
                },
            }
        ]
    }

    events = normalize_oddspapi_payload(payload, sport_key="football")

    assert len(events) == 1
    event = events[0].as_existing_pipeline_dict()
    assert event["bookmakers"][0]["key"] == "superbet_pl"
    assert [market["key"] for market in event["bookmakers"][0]["markets"]] == ["h2h", "totals"]
    assert event["bookmakers"][0]["markets"][0]["outcomes"][0] == {"name": "Team A", "price": 1.91}


def test_normalize_oddspapi_documented_bookmaker_odds_shape():
    payload = [
        {
            "fixtureId": "id1000001764618978",
            "sportId": 10,
            "startTime": "2025-12-08T20:00:00.000Z",
            "participants": {
                "home": {"name": "Arsenal"},
                "away": {"name": "Chelsea"},
            },
            "bookmakerOdds": {
                "superbet.pl": {
                    "bookmakerIsActive": True,
                    "updatedAt": "2025-12-07T22:50:48.812Z",
                    "markets": {
                        "101": {
                            "outcomes": {
                                "101": {"players": {"0": {"bookmakerOutcomeId": "home", "price": 1.91}}},
                                "102": {"players": {"0": {"bookmakerOutcomeId": "draw", "price": 3.50}}},
                                "103": {"players": {"0": {"bookmakerOutcomeId": "away", "price": 4.20}}},
                            }
                        }
                    },
                }
            },
        }
    ]

    events = normalize_oddspapi_payload(payload, sport_key="football")

    assert len(events) == 1
    event = events[0].as_existing_pipeline_dict()
    assert event["id"] == "id1000001764618978"
    assert event["home_team"] == "Arsenal"
    assert event["away_team"] == "Chelsea"
    assert event["bookmakers"][0]["key"] == "superbet.pl"
    assert event["bookmakers"][0]["markets"][0]["key"] == "h2h"
    assert event["bookmakers"][0]["markets"][0]["outcomes"] == [
        {"name": "home", "price": 1.91},
        {"name": "draw", "price": 3.5},
        {"name": "away", "price": 4.2},
    ]


def test_get_account_sends_account_query_api_key_and_timeout():
    transport = FakeTransport([FakeResponse({"data": {"requestLimit": 250}})])
    client = OddsPapiClient(OddspapiConfig(api_key="secret-token"), transport=transport)

    payload = client.get_account()

    assert payload == {"data": {"requestLimit": 250}}
    url, kwargs = transport.calls[0]
    assert url.endswith("/account")
    assert kwargs["params"]["apiKey"] == "secret-token"
    assert kwargs["timeout"] == 20.0


def test_summarize_account_omits_email_and_subscription_id():
    client = OddsPapiClient(OddspapiConfig(api_key="secret-token"), transport=FakeTransport([]))

    summary = client.summarize_account(
        {
            "data": {
                "email": "private@example.com",
                "currentSubscriptionId": "sub_123",
                "requestLimit": 250,
                "requestCount": 17,
                "currentSubscriptionActive": True,
                "subscriptions": [{"bookmakers": ["superbet.pl"], "sportIds": [10]}],
            }
        }
    )

    assert summary["current_subscription_active"] is True
    assert summary["request_limit"] == 250
    assert summary["request_count"] == 17
    assert summary["subscription_count"] == 1
    assert summary["has_superbet_pl"] is True
    assert summary["has_sport_10"] is True
    assert "email" not in summary
    assert "subscription_id" not in summary
    assert "private@example.com" not in repr(summary)
    assert "sub_123" not in repr(summary)


def test_fetch_fixtures_sends_documented_contract_params():
    transport = FakeTransport([FakeResponse({"fixtures": [{"fixtureId": "fx-1"}]})])
    client = OddsPapiClient(OddspapiConfig(api_key="secret-token"), transport=transport)

    fixtures = client.fetch_fixtures(
        "football",
        "2026-06-26T00:00:00Z",
        "2026-06-27T00:00:00Z",
    )

    assert fixtures == [{"fixtureId": "fx-1"}]
    url, kwargs = transport.calls[0]
    assert url.endswith("/fixtures")
    assert kwargs["params"]["sportId"] == "10"
    assert kwargs["params"]["statusId"] == 0
    assert kwargs["params"]["hasOdds"] == "true"
    assert kwargs["params"]["bookmakers"] == "superbet.pl"
    assert kwargs["params"]["from"] == "2026-06-26T00:00:00Z"
    assert kwargs["params"]["to"] == "2026-06-27T00:00:00Z"


def test_fetch_fixture_odds_sends_fixture_id_and_bookmaker():
    transport = FakeTransport([FakeResponse({"data": []})])
    client = OddsPapiClient(OddspapiConfig(api_key="secret-token"), transport=transport)

    assert client.fetch_fixture_odds("fx-1") == []

    url, kwargs = transport.calls[0]
    assert url.endswith("/odds")
    assert kwargs["params"]["fixtureId"] == "fx-1"
    assert kwargs["params"]["bookmakers"] == "superbet.pl"
    assert kwargs["params"]["oddsFormat"] == "decimal"


def test_fetch_odds_uses_fixtures_then_fixture_odds():
    transport = FakeTransport(
        [
            FakeResponse({"fixtures": [{"fixtureId": "fx-1"}, {"fixtureId": "fx-2"}]}),
            FakeResponse(
                {
                    "data": [
                        {
                            "fixtureId": "fx-1",
                            "sportId": 10,
                            "participants": {"home": {"name": "A"}, "away": {"name": "B"}},
                            "bookmakerOdds": {
                                "superbet.pl": {
                                    "markets": {
                                        "101": {
                                            "outcomes": {
                                                "101": {"players": {"0": {"bookmakerOutcomeId": "home", "price": 1.9}}},
                                                "102": {"players": {"0": {"bookmakerOutcomeId": "draw", "price": 3.4}}},
                                                "103": {"players": {"0": {"bookmakerOutcomeId": "away", "price": 4.1}}},
                                            }
                                        }
                                    }
                                }
                            },
                        }
                    ]
                }
            ),
        ]
    )
    client = OddsPapiClient(OddspapiConfig(api_key="secret-token"), transport=transport)

    events = client.fetch_odds(
        sport="football",
        from_dt="2026-06-26T00:00:00Z",
        to_dt="2026-06-28T00:00:00Z",
        max_fixtures=1,
        allow_wide_window=True,
    )

    assert len(events) == 1
    assert len(transport.calls) == 2
    assert transport.calls[0][0].endswith("/fixtures")
    assert transport.calls[1][0].endswith("/odds")


def test_fetch_odds_returns_empty_when_no_fixtures():
    transport = FakeTransport([FakeResponse({"fixtures": []})])
    client = OddsPapiClient(OddspapiConfig(api_key="secret-token"), transport=transport)

    assert client.fetch_odds(
        sport="football",
        from_dt="2026-06-26T00:00:00Z",
        to_dt="2026-06-27T00:00:00Z",
    ) == []
    assert len(transport.calls) == 1
    assert transport.calls[0][0].endswith("/fixtures")


def test_provider_errors_redact_api_key():
    transport = FakeTransport([FakeResponse({"error": "forbidden"}, status_code=403)])
    client = OddsPapiClient(OddspapiConfig(api_key="secret-token"), transport=transport)

    with pytest.raises(OddsPapiError) as excinfo:
        client.get_account()

    assert excinfo.value.http_status == 403
    assert "secret-token" not in str(excinfo.value)
    assert "HTTP 403" in str(excinfo.value)
