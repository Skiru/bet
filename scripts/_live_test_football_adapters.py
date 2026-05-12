#!/usr/bin/env python3
"""Live test for all football adapters — fetches real pages, parses, reports.

Usage: .venv/bin/python scripts/_live_test_football_adapters.py
"""
import sys
import os
import logging
import time

# Ensure scripts dir is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

import requests

logging.basicConfig(level=logging.INFO, format="%(name)s | %(message)s")
logger = logging.getLogger("live_test_football")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
}

# Test URLs per adapter (football-focused)
TEST_CONFIGS = [
    {
        "name": "betexplorer",
        "url": "https://www.betexplorer.com/football/",
        "adapter": "betexplorer_adapter",
        "min_matches": 1,
    },
    {
        "name": "sofascore (API)",
        "url": "https://www.sofascore.com/football/2026-05-12",
        "adapter": "sofascore_adapter",
        "min_matches": 1,
    },
    {
        "name": "forebet",
        "url": "https://www.forebet.com/en/football-tips-and-predictions-for-today",
        "adapter": "forebet_adapter",
        "min_matches": 1,
    },
    {
        "name": "oddsportal",
        "url": "https://www.oddsportal.com/football/",
        "adapter": "oddsportal_adapter",
        "min_matches": 0,  # OddsPortal is SPA, HTML may be empty
    },
    {
        "name": "flashscore",
        "url": "https://www.flashscore.com/football/",
        "adapter": "flashscore_adapter",
        "min_matches": 0,  # Flashscore is SPA
    },
]

# These adapters need Playwright (JS-rendered pages) or may block requests
PLAYWRIGHT_NOTE_ADAPTERS = [
    {
        "name": "soccerway",
        "url": "https://int.soccerway.com/matches/2026/05/12/",
        "adapter": "soccerway_adapter",
        "note": "May require Playwright for full rendering",
    },
    {
        "name": "whoscored",
        "url": "https://www.whoscored.com/LiveScores",
        "adapter": "whoscored_adapter",
        "note": "Heavy JS rendering, likely needs Playwright",
    },
    {
        "name": "soccerstats",
        "url": "https://www.soccerstats.com/latest.asp",
        "adapter": "soccerstats_adapter",
        "note": "May have limited HTML content",
    },
    {
        "name": "totalcorner",
        "url": "https://www.totalcorner.com/",
        "adapter": "totalcorner_adapter",
        "note": "May block direct HTTP requests",
    },
]


def test_adapter(config: dict) -> dict:
    """Test a single adapter against a live URL."""
    name = config["name"]
    url = config["url"]
    adapter_name = config["adapter"]
    min_matches = config.get("min_matches", 0)
    note = config.get("note", "")

    result = {
        "name": name,
        "url": url,
        "status": "UNKNOWN",
        "matches": 0,
        "deep_links": 0,
        "fields": [],
        "error": None,
        "note": note,
        "fetch_time_ms": 0,
        "parse_time_ms": 0,
    }

    # Import adapter
    try:
        mod = __import__(f"adapters.{adapter_name}", fromlist=["parse"])
        parse_fn = mod.parse
        get_deep_links_fn = getattr(mod, "get_deep_links", None)
    except Exception as e:
        result["status"] = "IMPORT_ERROR"
        result["error"] = str(e)
        return result

    # Fetch HTML
    try:
        t0 = time.time()
        resp = requests.get(url, headers=HEADERS, timeout=20)
        result["fetch_time_ms"] = int((time.time() - t0) * 1000)

        if resp.status_code != 200:
            result["status"] = f"HTTP_{resp.status_code}"
            result["error"] = f"HTTP {resp.status_code}"
            return result

        html = resp.text
        result["html_size"] = len(html)
    except Exception as e:
        result["status"] = "FETCH_ERROR"
        result["error"] = str(e)
        return result

    # Parse
    try:
        t0 = time.time()
        matches = parse_fn(html, url)
        result["parse_time_ms"] = int((time.time() - t0) * 1000)
        result["matches"] = len(matches)

        if matches:
            # Sample first match fields
            first = matches[0]
            result["fields"] = sorted(first.keys())
            result["sample"] = {
                "home": first.get("home", ""),
                "away": first.get("away", ""),
                "sport": first.get("sport", ""),
                "source_type": first.get("source_type", ""),
                "league": first.get("league", ""),
                "has_match_url": bool(first.get("match_url")),
                "has_odds": bool(first.get("odds")),
            }

            # Check required fields
            missing_fields = []
            for req in ["home", "away", "sport", "source_type"]:
                if not first.get(req):
                    missing_fields.append(req)
            if missing_fields:
                result["missing_fields"] = missing_fields
    except Exception as e:
        result["status"] = "PARSE_ERROR"
        result["error"] = str(e)
        return result

    # Test deep links
    if get_deep_links_fn:
        try:
            deep = get_deep_links_fn(html, url)
            result["deep_links"] = len(deep)
            if deep:
                result["sample_deep_link"] = deep[0]
        except Exception as e:
            result["deep_links_error"] = str(e)

    # Determine status
    if result["matches"] >= min_matches and not result.get("missing_fields"):
        result["status"] = "PASS"
    elif result["matches"] > 0:
        result["status"] = "PARTIAL"
    else:
        result["status"] = "NO_DATA"

    return result


def main():
    print("=" * 80)
    print("FOOTBALL ADAPTER LIVE TEST")
    print("=" * 80)

    all_results = []

    # Test direct HTTP adapters
    print("\n--- Direct HTTP Adapters ---")
    for config in TEST_CONFIGS:
        print(f"\nTesting: {config['name']}...")
        r = test_adapter(config)
        all_results.append(r)
        _print_result(r)

    # Test adapters that may need Playwright
    print("\n--- Adapters That May Need Playwright ---")
    for config in PLAYWRIGHT_NOTE_ADAPTERS:
        print(f"\nTesting: {config['name']} ({config.get('note', '')})...")
        r = test_adapter(config)
        all_results.append(r)
        _print_result(r)

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    passed = sum(1 for r in all_results if r["status"] == "PASS")
    partial = sum(1 for r in all_results if r["status"] == "PARTIAL")
    failed = sum(1 for r in all_results if r["status"] not in ("PASS", "PARTIAL"))

    for r in all_results:
        status_icon = {"PASS": "✓", "PARTIAL": "~", "NO_DATA": "○"}.get(r["status"], "✗")
        dl = f"deep_links={r['deep_links']}" if r["deep_links"] else "no deep_links"
        note = f" [{r['note']}]" if r.get("note") else ""
        print(f"  {status_icon} {r['name']:20s} matches={r['matches']:3d}  {dl}{note}")

    print(f"\nPassed: {passed}  Partial: {partial}  Failed/NoData: {failed}")
    print(f"Total adapters tested: {len(all_results)}")


def _print_result(r):
    """Print a single test result."""
    print(f"  Status: {r['status']}")
    print(f"  Matches: {r['matches']}")
    if r.get("html_size"):
        print(f"  HTML size: {r['html_size']} bytes")
    print(f"  Fetch: {r['fetch_time_ms']}ms  Parse: {r['parse_time_ms']}ms")
    if r.get("deep_links"):
        print(f"  Deep links: {r['deep_links']}")
        if r.get("sample_deep_link"):
            print(f"    Sample: {r['sample_deep_link'][:80]}")
    if r.get("sample"):
        s = r["sample"]
        print(f"  Sample: {s['home']} vs {s['away']} ({s['sport']}/{s['source_type']})")
        print(f"    league={s['league'][:50] if s['league'] else 'N/A'}  match_url={s['has_match_url']}  odds={s['has_odds']}")
    if r.get("missing_fields"):
        print(f"  ⚠ Missing fields: {r['missing_fields']}")
    if r.get("fields"):
        print(f"  Fields: {r['fields']}")
    if r.get("error"):
        print(f"  Error: {r['error']}")


if __name__ == "__main__":
    main()
