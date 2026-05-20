from bet.api_clients.rate_limiter import RateLimiter
from bet.api_clients.sofascore_tennis import SofascoreTennisClient


def test_sofascore_tennis_get_fixture_stats_maps_service_and_return_metrics(monkeypatch):
    client = SofascoreTennisClient(rate_limiter=RateLimiter())

    def fake_request(path: str):
        if path == "/event/123/statistics":
            return {
                "statistics": [
                    {
                        "period": "ALL",
                        "groups": [
                            {
                                "groupName": "Service",
                                "statisticsItems": [
                                    {"name": "Aces", "home": "7", "away": "4"},
                                    {"name": "Double Faults", "home": "2", "away": "5"},
                                    {"name": "First Serve Percentage", "home": "68%", "away": "61%"},
                                    {"name": "First Serve Points Won", "home": "74%", "away": "69%"},
                                    {"name": "Second Serve Points Won", "home": "51%", "away": "46%"},
                                    {"name": "Break Points Saved", "home": "80%", "away": "63%"},
                                    {"name": "Break Points Converted", "home": "42%", "away": "31%"},
                                    {"name": "Service Games Won", "home": "88%", "away": "79%"},
                                ],
                            }
                        ],
                    }
                ]
            }
        if path == "/event/123":
            return {
                "event": {
                    "homeTeam": {"name": "Iga Swiatek"},
                    "awayTeam": {"name": "Aryna Sabalenka"},
                    "startTimestamp": 1779235200,
                }
            }
        raise AssertionError(f"Unexpected SofaScore request: {path}")

    monkeypatch.setattr(client._sofa, "_request", fake_request)

    match = client.get_fixture_stats("123")

    assert match is not None
    assert match.fixture_id == "123"
    assert match.home_team == "Iga Swiatek"
    assert match.away_team == "Aryna Sabalenka"
    assert match.stats["home_aces"] == 7
    assert match.stats["away_double_faults"] == 5
    assert match.stats["home_first_serve_pct"] == 68
    assert match.stats["away_break_pct"] == 31
    assert match.stats["home_hold_pct"] == 88