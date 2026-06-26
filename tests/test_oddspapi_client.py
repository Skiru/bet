from __future__ import annotations

from bet.api_clients.oddspapi import OddspapiConfig, OddsPapiClient, normalize_oddspapi_payload


class FakeResponse:
    status_code = 200
    headers = {}

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class FakeTransport:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeResponse(self.payload)


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


def test_oddspapi_client_sends_api_key_query_parameter_superbet_pl_sport_id():
    payload = {"data": []}
    transport = FakeTransport(payload)
    client = OddsPapiClient(OddspapiConfig(api_key="secret-token"), transport=transport)

    assert client.fetch_odds(sport="football") == []

    url, kwargs = transport.calls[0]
    assert url.endswith("/odds")
    assert kwargs["params"]["apiKey"] == "secret-token"
    assert kwargs["params"]["bookmakers"] == "superbet.pl"
    assert kwargs["params"]["sportsbooks"] == "superbet.pl"
    assert kwargs["params"]["sportId"] == "10"
    assert "sport" not in kwargs["params"]
    assert kwargs["headers"]["Authorization"] == "Bearer secret-token"
    assert kwargs["timeout"] == 20.0
