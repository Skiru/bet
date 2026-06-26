from __future__ import annotations

from bet.api_clients.the_odds_api_betclic import TheOddsApiBetclicClient, TheOddsApiConfig


class FakeResponse:
    headers = {}

    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


class FakeTransport:
    def __init__(self, statuses=None):
        self.calls = []
        self.statuses = list(statuses or [200])

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        status = self.statuses.pop(0) if self.statuses else 200
        return FakeResponse([
            {
                "id": "odds-api-evt-1",
                "home_team": "Team A",
                "away_team": "Team B",
                "commence_time": "2026-06-26T18:00:00Z",
                "bookmakers": [{"key": "betclic_fr", "markets": [{"key": "h2h", "outcomes": []}]}],
            }
        ], status_code=status)


def test_the_odds_api_betclic_uses_bookmaker_filter_decimal_odds_and_date_window():
    transport = FakeTransport()
    client = TheOddsApiBetclicClient(TheOddsApiConfig(api_key="secret"), transport=transport)

    events = client.fetch_sport_key(
        "soccer_france_ligue_one",
        commence_time_from="2026-06-26T00:00:00Z",
        commence_time_to="2026-06-27T23:59:59Z",
    )

    assert events[0]["_odds_source"] == "the-odds-api-betclic"
    url, kwargs = transport.calls[0]
    assert url.endswith("/sports/soccer_france_ligue_one/odds")
    assert kwargs["params"]["bookmakers"] == "betclic_fr"
    assert kwargs["params"]["regions"] == "eu"
    assert kwargs["params"]["markets"] == "h2h,spreads,totals"
    assert kwargs["params"]["oddsFormat"] == "decimal"
    assert kwargs["params"]["commenceTimeFrom"] == "2026-06-26T00:00:00Z"
    assert kwargs["params"]["commenceTimeTo"] == "2026-06-27T23:59:59Z"


def test_the_odds_api_betclic_retries_transient_http_errors(monkeypatch):
    monkeypatch.setattr("bet.api_clients.the_odds_api_betclic.time.sleep", lambda _: None)
    transport = FakeTransport(statuses=[429, 200])
    client = TheOddsApiBetclicClient(TheOddsApiConfig(api_key="secret", max_retries=1), transport=transport)

    assert client.fetch_sport_key("soccer_france_ligue_one")
    assert len(transport.calls) == 2
