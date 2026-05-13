#!/usr/bin/env python3
"""Post-review validation: registry, rate limiting, SSRF guards across all clients."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

errors = []

def check(name, condition, detail=""):
    if condition:
        print(f"  ✅ {name}")
    else:
        print(f"  ❌ {name} — {detail}")
        errors.append(f"{name}: {detail}")

# ── 1. Registry completeness ──────────────────────────────────────────
print("=== CLIENT_REGISTRY completeness ===")
from bet.api_clients import CLIENT_REGISTRY
expected = ["flashscore", "oddsportal", "totalcorner", "scores24", "soccerway", "betexplorer",
            "api-football", "api-basketball", "api-hockey", "api-volleyball"]
for name in expected:
    check(f"'{name}' registered", name in CLIENT_REGISTRY, f"missing from CLIENT_REGISTRY")

# ── 2. Rate limiter entries ───────────────────────────────────────────
print("\n=== Rate limiter entries ===")
from bet.api_clients.rate_limiter import API_DAILY_LIMITS
rate_expected = {
    "flashscore-scraper": 200,
    "oddsportal-scraper": 50,
    "betexplorer-scraper": 50,
    "totalcorner-scraper": 50,
    "scores24-scraper": 100,
    "soccerway-scraper": 100,
}
for name, limit in rate_expected.items():
    check(f"'{name}' = {limit}/day", 
          API_DAILY_LIMITS.get(name) == limit,
          f"got {API_DAILY_LIMITS.get(name)}")

# ── 3. SSRF protection (urlparse usage) ──────────────────────────────
print("\n=== SSRF protection (urlparse imports) ===")
import inspect

from bet.api_clients.oddsportal import OddsPortalClient
src_oddsportal = inspect.getsource(OddsPortalClient.get_odds)
check("oddsportal.get_odds uses urlparse", "urlparse" in src_oddsportal, "substring check only")

src_h2h_op = inspect.getsource(OddsPortalClient.get_h2h)
check("oddsportal.get_h2h uses urlparse", "urlparse" in src_h2h_op, "substring check only")

from bet.api_clients.soccerway import SoccerwayClient
src_soc_md = inspect.getsource(SoccerwayClient.get_match_detail)
check("soccerway.get_match_detail uses urlparse", "urlparse" in src_soc_md, "missing domain check")

from bet.api_clients.scores24 import Scores24Client
src_s24_md = inspect.getsource(Scores24Client.get_match_detail)
check("scores24.get_match_detail uses urlparse", "urlparse" in src_s24_md, "missing domain check")

src_s24_tr = inspect.getsource(Scores24Client.get_trends)
check("scores24.get_trends uses urlparse", "urlparse" in src_s24_tr, "missing domain check")

from bet.api_clients.totalcorner import TotalCornerClient
src_tc_cp = inspect.getsource(TotalCornerClient.get_corner_predictions)
check("totalcorner.get_corner_predictions uses urlparse", "urlparse" in src_tc_cp, "missing domain check")

# ── 4. Rate limiting in method source ────────────────────────────────
print("\n=== Rate limiting in methods ===")
from bet.api_clients.flashscore import FlashscoreClient

for cls, methods in [
    (FlashscoreClient, ["get_fixtures", "get_fixture_stats", "get_h2h", "get_match_preview"]),
    (OddsPortalClient, ["get_fixtures", "get_odds", "get_h2h", "get_dropping_odds"]),
    (SoccerwayClient, ["get_fixtures", "get_h2h", "get_match_detail"]),
    (TotalCornerClient, ["get_fixtures", "get_corner_predictions"]),
    (Scores24Client, ["get_fixtures", "get_match_detail", "get_trends"]),
]:
    for method_name in methods:
        method = getattr(cls, method_name)
        src = inspect.getsource(method)
        has_can = "can_request" in src
        has_rec = "record_request" in src
        check(f"{cls.__name__}.{method_name} rate limited",
              has_can or has_rec,
              f"can_request={has_can}, record_request={has_rec}")

# BetExplorer uses requests, not Playwright — check differently
from bet.api_clients.betexplorer import BetExplorerClient
src_be = inspect.getsource(BetExplorerClient.get_fixtures)
check("BetExplorerClient.get_fixtures rate limited",
      "can_request" in src_be and "record_request" in src_be,
      "missing can_request or record_request")

# ── 5. Event ID validation ──────────────────────────────────────────
print("\n=== Event ID validation ===")
import bet.api_clients.flashscore as fs_mod
check("flashscore has _VALID_EVENT_ID", hasattr(fs_mod, '_VALID_EVENT_ID'))

import bet.api_clients.soccerway as sw_mod
check("soccerway has _VALID_EVENT_ID", hasattr(sw_mod, '_VALID_EVENT_ID'))

# ── 6. Unified.py routing completeness ───────────────────────────────
print("\n=== UnifiedAPIClient routing ===")
from bet.api_clients.unified import UnifiedAPIClient, SOURCE_PRIORITY

check("football includes soccerway", "soccerway" in SOURCE_PRIORITY.get("football", []))
check("tennis includes scores24", "scores24" in SOURCE_PRIORITY.get("tennis", []))
check("basketball includes scores24", "scores24" in SOURCE_PRIORITY.get("basketball", []))

u = UnifiedAPIClient()
for name in ["flashscore", "betexplorer", "oddsportal", "soccerway", "scores24", "totalcorner"]:
    client = u._create_client(name)
    check(f"UnifiedAPIClient._create_client('{name}')", client is not None or name == "espn",
          f"returned None")
u.close()

# ── 7. BetExplorer _load_api_key ─────────────────────────────────────
print("\n=== BetExplorer API key ===")
be = BetExplorerClient(rate_limiter=None)
check("BetExplorer api_key is 'no-key'", be.api_key == "no-key", f"got {be.api_key!r}")

# ── Summary ──────────────────────────────────────────────────────────
print(f"\n{'='*60}")
if errors:
    print(f"❌ {len(errors)} FAILURES:")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)
else:
    print("🎉 All checks passed!")
    sys.exit(0)
