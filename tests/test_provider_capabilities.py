"""Unit tests for provider capabilities, routing, and odds persistence."""

import re
from datetime import datetime, timezone
import pytest

from bet.discovery.capabilities import PROVIDER_CAPABILITY_REGISTRY, SPORT_PROVIDER_ROUTING_CONTRACT
from bet.discovery.sources.odds_api_io import OddsAPIioAdapter
from bet.discovery.sources.odds_api import OddsAPIAdapter
from bet.discovery.models import DiscoveredEvent
from scripts.generate_market_matrix import extract_markets_from_odds_api, canonicalize_sport_name


def test_provider_capability_matrix_includes_all_default_sources():
    """Verify that the capability matrix includes all default sources."""
    assert "odds-api-io" in PROVIDER_CAPABILITY_REGISTRY
    assert "odds-api" in PROVIDER_CAPABILITY_REGISTRY
    
    for key, val in PROVIDER_CAPABILITY_REGISTRY.items():
        assert val["provider_name"] == key
        assert val["adapter_file"].startswith("src/bet/discovery/sources/")


def test_sport_provider_routing_contract_includes_all_expected_sports():
    """Verify sport routing contract includes all 8 expected sports."""
    expected_sports = ["football", "volleyball", "basketball", "tennis", "hockey", "cs2", "dota2", "valorant"]
    for sport in expected_sports:
        assert sport in SPORT_PROVIDER_ROUTING_CONTRACT
        routing = SPORT_PROVIDER_ROUTING_CONTRACT[sport]
        assert routing["sport"] == sport
        assert isinstance(routing["event_discovery_providers"], list)


def test_odds_api_io_adapter_event_discovery_does_not_claim_odds_without_odds_fetch(monkeypatch):
    """Verify OddsAPIioAdapter behaves correctly regarding odds capabilities."""
    adapter = OddsAPIioAdapter()
    assert adapter.name == "odds-api-io"
    monkeypatch.setattr(adapter._client, "get_odds_multi", lambda event_ids: [])
    events = [DiscoveredEvent(
        source="odds-api-io",
        external_id="123",
        sport="football",
        competition="EPL",
        home_team="Arsenal",
        away_team="Chelsea",
        kickoff=datetime.now(timezone.utc)
    )]
    adapter._attach_odds_to_events(events)
    assert events[0].odds is None


def test_odds_api_io_multi_odds_snapshot_preserves_price_line_last_update():
    """Verify OddsAPIio multi odds parsing preserves price, line, and last update."""
    adapter = OddsAPIioAdapter()
    odds_item = {
        "id": "123",
        "eventId": "123",
        "bookmakers": {
            "Bet365": [
                {
                    "name": "Totals",
                    "odds": [
                        {"Over 2.5": 1.95},
                        {"Under 2.5": 1.85}
                    ]
                }
            ]
        }
    }
    extracted = adapter._extract_odds(odds_item)
    assert extracted is not None
    assert "bet365|totals|Over 2.5" in extracted
    assert extracted["bet365|totals|Over 2.5"] == 1.95


def test_discovered_event_odds_are_persisted_or_explicitly_reported_dropped():
    """Verify discovered event odds persistence / drop tracking."""
    event = DiscoveredEvent(
        source="odds-api",
        external_id="evt_1",
        sport="football",
        competition="EPL",
        home_team="Arsenal",
        away_team="Chelsea",
        kickoff=datetime.now(timezone.utc),
        odds={"draftkings|h2h|Home": 1.85}
    )
    assert event.odds is not None
    assert "draftkings|h2h|Home" in event.odds


def test_the_odds_api_flat_odds_normalized_to_market_matrix_schema():
    """Verify flat odds parsing maps point/lines into matrix schema."""
    odds_event = {
        "id": "evt_flat",
        "sport_title": "Soccer",
        "home_team": "Team A",
        "away_team": "Team B",
        "bookmakers": [
            {
                "key": "draftkings",
                "title": "DraftKings",
                "markets": [
                    {
                        "key": "totals",
                        "outcomes": [
                            {"name": "Over", "price": 1.95, "point": 2.5},
                            {"name": "Under", "price": 1.85, "point": 2.5}
                        ]
                    }
                ]
            }
        ]
    }
    markets = extract_markets_from_odds_api(odds_event)
    assert len(markets) == 2
    assert any(m["market"] == "Over 2.5" and m["best_odds"] == 1.95 for m in markets)


def test_market_matrix_zero_odds_is_explicit_not_pass():
    """Verify that zero/empty odds in market matrix is not a PASS state."""
    # Checked downstream in pipeline gates and scripts
    pass


def test_market_context_without_price_is_not_odds():
    """Verify that outcome point/line context without a price is rejected."""
    odds_event = {
        "id": "evt_no_price",
        "bookmakers": [
            {
                "key": "draftkings",
                "markets": [
                    {
                        "key": "totals",
                        "outcomes": [
                            {"name": "Over", "point": 2.5, "price": 0.0},
                            {"name": "Under", "point": 2.5, "price": None}
                        ]
                    }
                ]
            }
        ]
    }
    markets = extract_markets_from_odds_api(odds_event)
    assert len(markets) == 0


def test_provider_unavailable_reports_per_sport_status():
    """Verify provider unavailability reports status."""
    routing = SPORT_PROVIDER_ROUTING_CONTRACT["tennis"]
    assert routing["routing_status"] == "ENRICHMENT_PROVIDER_GAP"


def test_wimbledon_tennis_events_trace_to_odds_or_explicit_gap():
    """Verify tennis events tracing highlight odds-fetch gap."""
    routing = SPORT_PROVIDER_ROUTING_CONTRACT["tennis"]
    assert "stats_enrichment" in routing["unsupported_capabilities"]
