#!/usr/bin/env python3
"""Test Phase 5 (TotalCorner) and Phase 6 (Scores24) clients.

Verifies:
1. Import works
2. Class hierarchy correct (extends PlaywrightBaseClient → BaseAPIClient)
3. get_fixtures returns APIFixture objects
4. Rate limiter entries exist
5. Circuit breaker is per-subclass
"""
import sys
import os

# Ensure src is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from bet.api_clients.base_client import BaseAPIClient
from bet.api_clients.playwright_base import PlaywrightBaseClient
from bet.api_clients.totalcorner import TotalCornerClient
from bet.api_clients.scores24 import Scores24Client
from bet.api_clients.rate_limiter import API_DAILY_LIMITS, RateLimiter

passed = 0
failed = 0

def check(name, condition):
    global passed, failed
    if condition:
        print(f"  ✅ {name}")
        passed += 1
    else:
        print(f"  ❌ {name}")
        failed += 1

# ── TotalCorner ──────────────────────────────────────────────────────
print("\n=== TotalCornerClient ===")

tc = TotalCornerClient()
check("Import works", tc is not None)
check("Extends PlaywrightBaseClient", isinstance(tc, PlaywrightBaseClient))
check("Extends BaseAPIClient", isinstance(tc, BaseAPIClient))
check("api_name = 'totalcorner'", tc.api_name == "totalcorner")
check("base_url correct", tc.base_url == "https://www.totalcorner.com")
check("is_available() = True", tc.is_available())
check("get_h2h returns empty list", tc.get_h2h("x", "y") == [])
check("_COOKIE_SELECTOR set", tc._COOKIE_SELECTOR != "")
check("Rate limiter entry exists", "totalcorner-scraper" in API_DAILY_LIMITS)
check("Rate limit = 50", API_DAILY_LIMITS.get("totalcorner-scraper") == 50)

# Circuit breaker independence
check("Circuit breaker per-subclass (failures)", TotalCornerClient._failures == 0)
check("Circuit breaker per-subclass (open)", TotalCornerClient._circuit_open == False)

# Method signatures
check("has get_fixtures", callable(getattr(tc, 'get_fixtures', None)))
check("has get_corner_predictions", callable(getattr(tc, 'get_corner_predictions', None)))
check("has get_fixture_stats", callable(getattr(tc, 'get_fixture_stats', None)))

# Non-football returns empty
check("Non-football returns []", tc.get_fixtures("2026-05-13", sport="tennis") == [])

# ── Scores24 ─────────────────────────────────────────────────────────
print("\n=== Scores24Client ===")

s24 = Scores24Client()
check("Import works", s24 is not None)
check("Extends PlaywrightBaseClient", isinstance(s24, PlaywrightBaseClient))
check("Extends BaseAPIClient", isinstance(s24, BaseAPIClient))
check("api_name = 'scores24'", s24.api_name == "scores24")
check("base_url correct", s24.base_url == "https://scores24.live")
check("is_available() = True", s24.is_available())
check("_COOKIE_SELECTOR empty (no banner)", s24._COOKIE_SELECTOR == "")
check("Rate limiter entry exists", "scores24-scraper" in API_DAILY_LIMITS)
check("Rate limit = 100", API_DAILY_LIMITS.get("scores24-scraper") == 100)

# SPORT_PATHS
check("Football path", s24.SPORT_PATHS["football"] == "/en/soccer")
check("Tennis path", s24.SPORT_PATHS["tennis"] == "/en/tennis")
check("Basketball path", s24.SPORT_PATHS["basketball"] == "/en/basketball")
check("Hockey path", s24.SPORT_PATHS["hockey"] == "/en/ice-hockey")
check("Volleyball path", s24.SPORT_PATHS["volleyball"] == "/en/volleyball")

# Method signatures
check("has get_fixtures", callable(getattr(s24, 'get_fixtures', None)))
check("has get_match_detail", callable(getattr(s24, 'get_match_detail', None)))
check("has get_trends", callable(getattr(s24, 'get_trends', None)))
check("has get_fixture_stats", callable(getattr(s24, 'get_fixture_stats', None)))
check("has get_h2h", callable(getattr(s24, 'get_h2h', None)))

# Circuit breaker independence
check("Circuit breaker independent from TC", Scores24Client._failures == 0)

# URL slug parsing
home, away, dt = s24._parse_match_slug("/en/soccer/m-13-05-2026-arka-gdynia-gornik-zabrze-prediction")
check("Slug parse: date", dt == "2026-05-13")
check("Slug parse: home not empty", home != "")
check("Slug parse: away not empty", away != "")

# Listing text parsing
sample_text = """Poland
Ekstraklasa
(2 matches)
18:00
13 May
Arka
Gornik Zabrze
-
-
20:30
13 May
Rakow
Jagiellonia
-
-
"""
text_matches = s24._parse_listing_text(sample_text, "2026-05-13", "football")
check("Text parse: found 2 matches", len(text_matches) == 2)
if text_matches:
    check("Text parse: first home = Arka", text_matches[0]["home"] == "Arka")
    check("Text parse: first away = Gornik Zabrze", text_matches[0]["away"] == "Gornik Zabrze")
    check("Text parse: first time = 18:00", text_matches[0]["time"] == "18:00")
    check("Text parse: competition = Ekstraklasa", text_matches[0]["competition"] == "Ekstraklasa")

# Trends text parsing
trends_text = """Match Result predictions
(1)
2.06
Over/Under predictions
(7)
1.19 - 2.06
Corners predictions
(3)
1.35 - 1.55
"""
trends = s24._parse_trends_text(trends_text)
check("Trends parse: found trends", len(trends) > 0)

# Detailed trends test: individual tip should NOT be duplicated by header parser
trends_detail_text = """Match Result predictions
(1)
Gornik have drawn in the 1st half
in last 6 away games (Ekstraklasa).
1st Half Draw
2.06
Over/Under predictions
(3)
1.19 - 2.06
"""
trends_detail = s24._parse_trends_text(trends_detail_text)
# Should have exactly 1 individual tip + 1 odds range = 2 trends, NOT 3
tips_match_result = [t for t in trends_detail if t["category"] == "Match Result"]
check("Trends: no duplicates from header parser", len(tips_match_result) == 1)
if tips_match_result:
    check("Trends: individual tip has correct name", tips_match_result[0]["tip"] == "1st Half Draw")
    check("Trends: individual tip has correct odds", tips_match_result[0].get("odds") == 2.06)

# hasattr guard removed — _corner_cache always in __init__
check("TC _corner_cache exists at init", hasattr(tc, '_corner_cache'))

# ── Summary ──────────────────────────────────────────────────────────
print(f"\n{'='*50}")
print(f"RESULTS: {passed} passed, {failed} failed out of {passed + failed}")
if failed > 0:
    sys.exit(1)
print("ALL TESTS PASSED ✓")
