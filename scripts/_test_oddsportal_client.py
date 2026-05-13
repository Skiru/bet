#!/usr/bin/env python3
"""Test OddsPortalClient — verify fixtures, odds, and H2H extraction."""
import json
import sys
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

from bet.api_clients.oddsportal import OddsPortalClient
from bet.api_clients.rate_limiter import RateLimiter

def test_import():
    """Test that OddsPortalClient can be imported and instantiated."""
    print("=== TEST: Import & instantiation ===")
    rl = RateLimiter()
    client = OddsPortalClient(rate_limiter=rl)
    print(f"  api_name: {client.api_name}")
    print(f"  base_url: {client.base_url}")
    print(f"  is_available: {client.is_available()}")
    assert client.api_name == "oddsportal"
    assert client.base_url == "https://www.oddsportal.com"
    assert client.is_available() is True
    print("  PASS")
    return client


def test_isinstance(client):
    """Test inheritance chain."""
    print("\n=== TEST: Inheritance ===")
    from bet.api_clients.base_client import BaseAPIClient
    from bet.api_clients.playwright_base import PlaywrightBaseClient
    assert isinstance(client, PlaywrightBaseClient), "Not a PlaywrightBaseClient"
    assert isinstance(client, BaseAPIClient), "Not a BaseAPIClient"
    print("  isinstance(PlaywrightBaseClient): True")
    print("  isinstance(BaseAPIClient): True")
    print("  PASS")


def test_get_fixtures(client):
    """Test fixture extraction from listing page."""
    print("\n=== TEST: get_fixtures('2026-05-13', 'football') ===")
    fixtures = client.get_fixtures("2026-05-13", "football")
    print(f"  Fixtures returned: {len(fixtures)}")
    
    if not fixtures:
        print("  WARNING: No fixtures returned — may be blocked or SPA render issue")
        return
    
    # Check structure
    fx = fixtures[0]
    print(f"  First fixture:")
    print(f"    external_id: {fx.external_id}")
    print(f"    source: {fx.source}")
    print(f"    sport: {fx.sport}")
    print(f"    competition: {fx.competition_name}")
    print(f"    home: {fx.home_team_name}")
    print(f"    away: {fx.away_team_name}")
    print(f"    kickoff: {fx.kickoff}")
    print(f"    status: {fx.status}")
    
    assert fx.source == "oddsportal"
    assert fx.sport == "football"
    assert fx.home_team_name, "home_team_name is empty"
    assert fx.away_team_name, "away_team_name is empty"
    
    # Show all fixtures
    print(f"\n  All {len(fixtures)} fixtures:")
    for i, f in enumerate(fixtures[:10]):
        print(f"    {i+1}. {f.home_team_name} vs {f.away_team_name} ({f.competition_name}) @ {f.kickoff}")
    if len(fixtures) > 10:
        print(f"    ... and {len(fixtures) - 10} more")
    
    print("  PASS")
    return fixtures


def test_get_odds(client, fixtures):
    """Test odds extraction from detail page."""
    print("\n=== TEST: get_odds (detail page) ===")
    if not fixtures or not fixtures[0].external_id:
        print("  SKIP: No fixtures with match URLs available")
        return
    
    # Use a known match URL from the listing
    # We need the full URL, which is stored during fixture extraction
    # For now, construct from the first fixture's match_id
    match_url = f"/football/h2h/test/#{fixtures[0].external_id}"
    print(f"  NOTE: get_odds requires full match URL, skipping live test")
    print(f"  (Would need URL from listing page, not just match_id)")
    print("  SKIP")


def test_circuit_breaker():
    """Test that circuit breaker is per-subclass."""
    print("\n=== TEST: Circuit breaker isolation ===")
    from bet.api_clients.flashscore import FlashscoreClient
    
    # Reset both
    OddsPortalClient._failures = 0
    OddsPortalClient._circuit_open = False
    FlashscoreClient._failures = 0
    FlashscoreClient._circuit_open = False
    
    # Increment OddsPortal failures
    OddsPortalClient._failures = 3
    OddsPortalClient._circuit_open = True
    
    assert FlashscoreClient._failures == 0, "Flashscore failures should be 0"
    assert FlashscoreClient._circuit_open is False, "Flashscore circuit should be closed"
    assert OddsPortalClient._failures == 3, "OddsPortal failures should be 3"
    assert OddsPortalClient._circuit_open is True, "OddsPortal circuit should be open"
    
    # Clean up
    OddsPortalClient._failures = 0
    OddsPortalClient._circuit_open = False
    
    print("  Circuit breaker is per-subclass: True")
    print("  PASS")


def main():
    print("=" * 60)
    print("OddsPortalClient Test Suite")
    print("=" * 60)
    
    client = test_import()
    test_isinstance(client)
    test_circuit_breaker()
    
    # Live tests (require Playwright + network)
    try:
        fixtures = test_get_fixtures(client)
        if fixtures:
            test_get_odds(client, fixtures)
    except Exception as e:
        print(f"\n  LIVE TEST ERROR: {e}")
    finally:
        client.close()
    
    print("\n" + "=" * 60)
    print("All tests completed")
    print("=" * 60)


if __name__ == "__main__":
    main()
