#!/usr/bin/env python3
"""Live test: fetch real pages with Playwright, parse through adapters, verify enriched output.

Usage:
    python3 scripts/_live_test_adapters.py [--adapter NAME] [--verbose]

Tests each adapter against a real URL, checks enriched fields are populated.
"""
import argparse
import json
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from adapters import ADAPTERS, normalize_adapter_output

# Test URLs — one per adapter (real, public pages with data)
# Keys must match ADAPTERS domain keys
TEST_URLS = {
    "flashscore.com": "https://www.flashscore.com/football/",
    "totalcorner.com": "https://www.totalcorner.com/match/today",
    "forebet.com": "https://www.forebet.com/en/football-tips-and-predictions-for-today",
    "betexplorer.com": "https://www.betexplorer.com/football/",
    "soccerstats.com": "https://www.soccerstats.com/matches.asp?matchday=1",
    "sofascore.com": "https://api.sofascore.com/api/v1/sport/football/scheduled-events/2026-05-12",
    "covers.com": "https://www.covers.com/nba/matchups",
    "basketball-reference.com": "https://www.basketball-reference.com/boxscores/",
    "hockey-reference.com": "https://www.hockey-reference.com/boxscores/",
    "soccerway.com": "https://int.soccerway.com/matches/2026/05/12/",
    "whoscored.com": "https://www.whoscored.com/LiveScores",
    "oddsportal.com": "https://www.oddsportal.com/football/",
    "scores24.live": "https://scores24.live/en/soccer",
    "naturalstattrick.com": "https://www.naturalstattrick.com/teamtable.php?fromseason=20252026&thession=20252026&stype=2&sit=5v5&score=all&rate=n&team=all&loc=B&gpf=410&fd=&td=",
    "dailyfaceoff.com": "https://www.dailyfaceoff.com/starting-goalies/",
}

# Volleyball-specific test URLs (used with --sport volleyball)
VOLLEYBALL_TEST_URLS = {
    "flashscore.com": "https://www.flashscore.com/volleyball/",
    "sofascore.com": "https://api.sofascore.com/api/v1/sport/volleyball/scheduled-events/{today}",
    "oddsportal.com": "https://www.oddsportal.com/volleyball/",
    "betexplorer.com": "https://www.betexplorer.com/volleyball/",
    "forebet.com": "https://www.forebet.com/en/volleyball/predictions-today",
    "scores24.live": "https://scores24.live/en/volleyball",
}

# Adapters that need Playwright (full browser rendering)
PLAYWRIGHT_ADAPTERS = {
    "flashscore.com", "totalcorner.com", "forebet.com", "soccerstats.com", "covers.com",
    "soccerway.com", "whoscored.com", "oddsportal.com", "naturalstattrick.com", "dailyfaceoff.com",
    "scores24.live",
}

# Adapters that can use simple HTTP requests
API_ADAPTERS = {"sofascore.com", "betexplorer.com", "basketball-reference.com", "hockey-reference.com"}

# Expected enriched fields per adapter
EXPECTED_FIELDS = {
    "flashscore.com": ["sport", "source_type", "match_id", "status"],
    "totalcorner.com": ["sport", "source_type", "corners", "cards"],
    "forebet.com": ["sport", "source_type", "predictions"],
    "betexplorer.com": ["source_type", "odds"],
    "soccerstats.com": ["sport", "source_type"],
    "sofascore.com": ["sport", "source_type"],
    "covers.com": ["source_type", "source_url"],
    "basketball-reference.com": ["source_type"],
    "hockey-reference.com": ["source_type", "sport", "league"],
    "naturalstattrick.com": ["source_type", "sport", "stats"],
    "dailyfaceoff.com": ["source_type", "sport"],
    "soccerway.com": ["source_type"],
    "whoscored.com": ["source_type"],
    "oddsportal.com": ["sport", "source_type"],
}

VOLLEYBALL_EXPECTED_FIELDS = {
    "flashscore.com": ["sport", "source_type", "match_id"],
    "sofascore.com": ["sport", "source_type"],
    "oddsportal.com": ["sport", "source_type"],
    "betexplorer.com": ["source_type"],
    "forebet.com": ["sport", "source_type"],
    "scores24.live": ["sport", "source_type"],
}


def fetch_with_requests(url: str, timeout: int = 15) -> str | None:
    """Fetch page with requests (for API/simple HTML sources)."""
    import requests
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36"
        }
        resp = requests.get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        return None


def fetch_with_playwright(url: str, timeout: int = 20000) -> str | None:
    """Fetch page with Playwright (for JS-heavy sites)."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            page.wait_for_timeout(3000)  # Wait for dynamic content
            html = page.content()
            browser.close()
            return html
    except Exception as e:
        return None


def test_adapter(name: str, verbose: bool = False, url_override: str | None = None, expected_override: list | None = None) -> dict:
    """Test a single adapter against its test URL."""
    result = {
        "adapter": name,
        "status": "SKIP",
        "events": 0,
        "enriched_fields": [],
        "sample": None,
        "error": None,
    }

    if name not in ADAPTERS:
        result["status"] = "NOT_REGISTERED"
        result["error"] = f"Adapter '{name}' not in ADAPTERS registry"
        return result

    url = url_override or TEST_URLS.get(name)
    if url and "{today}" in url:
        from datetime import date
        url = url.replace("{today}", date.today().isoformat())
    if not url:
        result["status"] = "NO_URL"
        result["error"] = f"No test URL configured for '{name}'"
        return result

    # Fetch HTML
    if name in API_ADAPTERS:
        html = fetch_with_requests(url)
        if html is None:
            # Try Playwright as fallback
            html = fetch_with_playwright(url)
    else:
        html = fetch_with_playwright(url)
        if html is None:
            # Try requests as fallback
            html = fetch_with_requests(url)

    if html is None:
        result["status"] = "FETCH_FAIL"
        result["error"] = "Could not fetch page (both requests and playwright failed)"
        return result

    if verbose:
        print(f"  Fetched {len(html)} bytes from {url}")

    # Parse through adapter
    parse_fn = ADAPTERS[name]
    try:
        import inspect
        sig = inspect.signature(parse_fn)
        if len(sig.parameters) >= 2:
            events = parse_fn(html, url)
        else:
            events = parse_fn(html)
    except Exception as e:
        result["status"] = "PARSE_ERROR"
        result["error"] = str(e)
        return result

    if not events:
        result["status"] = "EMPTY"
        result["error"] = "Adapter returned 0 events"
        return result

    # Normalize events
    normalized = []
    for ev in events:
        normalized.append(normalize_adapter_output(ev, source_type=name))

    result["events"] = len(normalized)

    # Check enriched fields on first event
    sample = normalized[0]
    enriched = []
    standard_keys = [
        "home", "away", "time", "league", "sport", "source_type", "source_url",
        "corners", "cards", "fouls", "shots", "standings", "predictions",
        "dangerous_attacks", "match_id", "match_url", "odds", "status",
        "is_live", "scores", "period_scores", "country", "raw",
    ]
    for key in standard_keys:
        val = sample.get(key)
        if val is not None and val != "" and val != {} and val != []:
            enriched.append(key)

    result["enriched_fields"] = enriched
    result["status"] = "OK" if len(enriched) >= 3 else "SPARSE"

    # Check expected fields
    expected = expected_override or EXPECTED_FIELDS.get(name, [])
    missing = [f for f in expected if f not in enriched]
    if missing:
        result["status"] = "MISSING_EXPECTED"
        result["error"] = f"Missing expected fields: {missing}"

    if verbose:
        result["sample"] = {k: v for k, v in sample.items() if k in enriched[:8]}

    return result


def test_api_clients(verbose: bool = False) -> list[dict]:
    """Test API clients (fallback chain sources) via the proper CLIENT_REGISTRY."""
    from api_clients import get_client, CLIENT_REGISTRY, RateLimiter

    results = []
    rl = RateLimiter()

    # Test all registered clients
    for api_name in sorted(CLIENT_REGISTRY.keys()):
        try:
            client = get_client(api_name, rate_limiter=rl)
            available = client.is_available()
            is_broken = getattr(client, "_HOST_BROKEN", False)

            if is_broken:
                status = "CORRECTLY_BROKEN" if not available else "UNEXPECTEDLY_ALIVE"
            elif available:
                status = "AVAILABLE"
            else:
                status = "UNAVAILABLE"

            results.append({
                "client": api_name,
                "status": status,
                "events": -1,
                "error": f"_HOST_BROKEN={is_broken}" if is_broken else None,
            })
        except Exception as e:
            results.append({"client": api_name, "status": "ERROR", "events": 0, "error": str(e)})

    # Quick live fetch test for ESPN (free, no quota)
    for espn_name in [n for n in CLIENT_REGISTRY if n.startswith("espn-")]:
        try:
            client = get_client(espn_name, rate_limiter=rl)
            if client.is_available():
                from datetime import date
                today = date.today().isoformat()
                data = client.get_fixtures(today)
                # Update the existing entry
                for r in results:
                    if r["client"] == espn_name:
                        r["status"] = "OK" if data else "EMPTY"
                        r["events"] = len(data) if data else 0
                        if verbose and data:
                            sample = data[0] if data else {}
                            r["error"] = f"sample keys: {list(sample.keys())[:8]}"
                        break
        except Exception as e:
            for r in results:
                if r["client"] == espn_name:
                    r["status"] = "FETCH_ERROR"
                    r["error"] = str(e)
                    break

    return results


def main():
    parser = argparse.ArgumentParser(description="Live test adapters and API clients")
    parser.add_argument("--adapter", help="Test specific adapter only")
    parser.add_argument("--sport", help="Use sport-specific test URLs (e.g. volleyball)")
    parser.add_argument("--api-only", action="store_true", help="Test only API clients")
    parser.add_argument("--adapters-only", action="store_true", help="Test only adapters")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed output")
    args = parser.parse_args()

    print("=" * 70)
    print("LIVE SOURCE TEST — Adapters + API Clients")
    print("=" * 70)

    # --- API Clients ---
    if not args.adapters_only and not args.adapter:
        print("\n--- API CLIENTS ---")
        api_results = test_api_clients(args.verbose)
        for r in api_results:
            status_icon = "✅" if r["status"] in ("OK", "AVAILABLE", "CORRECTLY_BROKEN") else "❌"
            print(f"  {status_icon} {r['client']:20s} | {r['status']:20s} | events={r['events']}")
            if r["error"] and args.verbose:
                print(f"     └─ {r['error']}")

    # --- Adapters ---
    if not args.api_only:
        print("\n--- SCAN ADAPTERS ---")
        adapter_names = [args.adapter] if args.adapter else sorted(ADAPTERS.keys())

        # Override with sport-specific URLs if requested
        active_urls = dict(TEST_URLS)
        active_expected = dict(EXPECTED_FIELDS)
        if args.sport == "volleyball":
            active_urls.update(VOLLEYBALL_TEST_URLS)
            active_expected.update(VOLLEYBALL_EXPECTED_FIELDS)
            # Replace {today} placeholder in sofascore URL
            from datetime import date
            today_str = date.today().isoformat()
            for domain in active_urls:
                if type(active_urls[domain]) is str:
                    active_urls[domain] = active_urls[domain].replace("{today}", today_str)

        for name in adapter_names:
            print(f"\n  Testing: {name}...")
            start = time.time()
            result = test_adapter(name, verbose=args.verbose, 
                                  url_override=active_urls.get(name),
                                  expected_override=active_expected.get(name))
            elapsed = time.time() - start

            status_icon = "✅" if result["status"] == "OK" else "⚠️" if result["status"] in ("SPARSE", "EMPTY") else "❌"
            print(f"  {status_icon} {name:25s} | {result['status']:18s} | events={result['events']:4d} | {elapsed:.1f}s")
            print(f"     └─ enriched: {', '.join(result['enriched_fields'][:10])}")
            if result["error"]:
                print(f"     └─ error: {result['error']}")
            if args.verbose and result.get("sample"):
                for k, v in result["sample"].items():
                    val_str = str(v)[:80]
                    print(f"     └─ {k}: {val_str}")

    # Summary
    print("\n" + "=" * 70)
    api_count = len(api_results) if not args.adapters_only and not args.adapter else 0
    adapter_count = len(adapter_names) if not args.api_only else 0
    print("AGENT_SUMMARY:" + json.dumps({
        "verdict": "COMPLETE",
        "api_clients": api_count,
        "adapters_tested": adapter_count,
    }))


if __name__ == "__main__":
    main()
