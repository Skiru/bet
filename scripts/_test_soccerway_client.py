#!/usr/bin/env python3
"""Quick test for SoccerwayClient import and basic functionality."""
import sys
sys.path.insert(0, "src")

from bet.api_clients.soccerway import SoccerwayClient
from bet.api_clients.base_client import BaseAPIClient
from bet.api_clients.playwright_base import PlaywrightBaseClient

# 1. Import check
print("✅ SoccerwayClient imported successfully")

# 2. Inheritance check
mro = [c.__name__ for c in SoccerwayClient.__mro__]
print(f"   MRO: {mro}")
assert "PlaywrightBaseClient" in mro, "Must extend PlaywrightBaseClient"
assert "BaseAPIClient" in mro, "Must extend BaseAPIClient"
print("✅ Inheritance chain correct")

# 3. Instantiation check
client = SoccerwayClient()
print(f"   api_name: {client.api_name}")
print(f"   base_url: {client.base_url}")
print(f"   is_available: {client.is_available()}")
assert client.api_name == "soccerway"
assert client.is_available() is True
print("✅ Client instantiation OK")

# 4. Rate limiter check
from bet.api_clients.rate_limiter import API_DAILY_LIMITS
assert "soccerway-scraper" in API_DAILY_LIMITS, "soccerway-scraper not in rate limits"
print(f"✅ Rate limit entry: soccerway-scraper = {API_DAILY_LIMITS['soccerway-scraper']}/day")

# 5. Date validation check
fixtures = client.get_fixtures("invalid-date")
assert fixtures == [], "Should return empty for invalid date"
print("✅ Date validation works")

# 6. Circuit breaker isolation
assert SoccerwayClient._failures == 0
assert SoccerwayClient._circuit_open is False
print("✅ Circuit breaker per-subclass")

print("\n🎉 All checks passed!")
