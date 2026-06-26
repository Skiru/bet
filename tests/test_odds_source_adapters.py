from __future__ import annotations

import scripts.odds_sources as odds_sources
from scripts.odds_sources.oddspapi import OddsPapiSource
from scripts.odds_sources.the_odds_api_betclic import TheOddsApiBetclicSource


class FakeOddsPapiClient:
    def __init__(self):
        self.calls = []

    def fetch_odds(self, **kwargs):
        self.calls.append(kwargs)
        return []


class FakeBetclicClient:
    def __init__(self):
        self.calls = []

    def fetch_odds(self, sport, **kwargs):
        self.calls.append((sport, kwargs))
        return []


def test_oddspapi_source_accepts_existing_date_from_date_to_signature():
    client = FakeOddsPapiClient()
    source = OddsPapiSource(client=client)

    assert source.fetch_odds("football", "2026-06-26", "2026-06-27") == []

    assert client.calls[0]["from_dt"] == "2026-06-26"
    assert client.calls[0]["to_dt"] == "2026-06-27"


def test_betclic_source_accepts_existing_date_from_date_to_signature():
    client = FakeBetclicClient()
    source = TheOddsApiBetclicSource(client=client)

    assert source.fetch_odds("football", "2026-06-26", "2026-06-27") == []

    sport, kwargs = client.calls[0]
    assert sport == "football"
    assert kwargs["commence_time_from"] == "2026-06-26T00:00:00Z"
    assert kwargs["commence_time_to"] == "2026-06-27T23:59:59Z"


def test_odds_sources_merge_event_odds_preserves_same_bookmaker_h2h_and_totals():
    existing = {
        "bookmakers": [
            {
                "key": "superbet.pl",
                "markets": [{"key": "h2h", "outcomes": [{"name": "Team A", "price": 1.91}]}],
            }
        ]
    }
    new = {
        "bookmakers": [
            {
                "key": "superbet.pl",
                "markets": [
                    {"key": "totals", "outcomes": [{"name": "Over 2.5", "price": 2.05, "point": 2.5}]}
                ],
            }
        ]
    }

    merged = odds_sources.merge_event_odds(existing, new)

    assert [market["key"] for market in merged["bookmakers"][0]["markets"]] == ["h2h", "totals"]


def test_odds_sources_merge_event_odds_dedupes_duplicate_outcome_by_name_and_point():
    existing = {
        "bookmakers": [
            {
                "key": "superbet.pl",
                "markets": [
                    {"key": "totals", "outcomes": [{"name": "Over 2.5", "price": 1.91, "point": 2.5}]}
                ],
            }
        ]
    }
    new = {
        "bookmakers": [
            {
                "key": "superbet.pl",
                "markets": [
                    {"key": "totals", "outcomes": [{"name": "Over 2.5", "price": 1.95, "point": 2.5}]}
                ],
            }
        ]
    }

    merged = odds_sources.merge_event_odds(existing, new)

    outcomes = merged["bookmakers"][0]["markets"][0]["outcomes"]
    assert outcomes == [{"name": "Over 2.5", "price": 1.95, "point": 2.5}]
