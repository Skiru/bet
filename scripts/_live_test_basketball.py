#!/usr/bin/env python3
"""Live test for basketball adapters — verifies parsing, verbosity, and data quality.

Usage:
    python3 scripts/_live_test_basketball.py [--adapter ADAPTER] [--verbose]

Tests:
    1. Basketball-Reference: schedule page, box score page, team stats page
    2. API-Basketball: season computation, stat mapping
    3. ESPN Basketball: fixture fetch, stat keys
    4. Fallback chain verification
"""

import argparse
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import requests


def test_basketball_reference_schedule(verbose: bool = False):
    """Test Basketball-Reference schedule page parsing."""
    print("\n" + "=" * 60)
    print("TEST 1: Basketball-Reference Schedule Page")
    print("=" * 60)

    from adapters.basketball_reference_adapter import parse, get_deep_links

    url = "https://www.basketball-reference.com/leagues/NBA_2025_games-may.html"
    print(f"  Fetching: {url}")

    try:
        resp = requests.get(url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
        }, timeout=20)
        resp.raise_for_status()
        html = resp.text
        print(f"  HTML size: {len(html)} bytes")
    except Exception as e:
        print(f"  FETCH FAILED: {e}")
        return False

    results = parse(html, url)
    print(f"  Parsed events: {len(results)}")

    if results:
        sample = results[0]
        print(f"  Sample: {sample.get('away')} @ {sample.get('home')} — {sample.get('time')}")
        has_match_url = bool(sample.get("match_url"))
        print(f"  Has match_url (deep link): {has_match_url}")
        if verbose and has_match_url:
            print(f"    match_url: {sample['match_url']}")

    deep_links = get_deep_links(html, url)
    print(f"  Deep links found: {len(deep_links)}")
    if deep_links and verbose:
        for dl in deep_links[:3]:
            print(f"    {dl}")

    ok = len(results) > 0
    print(f"  RESULT: {'PASS' if ok else 'FAIL'}")
    return ok


def test_basketball_reference_boxscore(verbose: bool = False):
    """Test Basketball-Reference box score page parsing."""
    print("\n" + "=" * 60)
    print("TEST 2: Basketball-Reference Box Score Page")
    print("=" * 60)

    from adapters.basketball_reference_adapter import parse

    # Use a known completed game
    url = "https://www.basketball-reference.com/boxscores/202505010DET.html"
    print(f"  Fetching: {url}")

    try:
        resp = requests.get(url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
        }, timeout=20)
        resp.raise_for_status()
        html = resp.text
        print(f"  HTML size: {len(html)} bytes")
    except Exception as e:
        print(f"  FETCH FAILED: {e}")
        return False

    results = parse(html, url)
    print(f"  Parsed results: {len(results)}")

    if not results:
        print("  RESULT: FAIL — no data parsed")
        return False

    result = results[0]
    print(f"  Home: {result.get('home')}")
    print(f"  Away: {result.get('away')}")
    print(f"  Source type: {result.get('source_type')}")

    stats = result.get("stats", {})
    print(f"  Stat keys ({len(stats)}): {list(stats.keys())}")

    expected_keys = [
        "points", "rebounds", "offensive_rebounds", "defensive_rebounds",
        "assists", "steals", "blocks", "turnovers", "fouls",
        "fg_pct", "three_pct", "ft_pct"
    ]
    missing = [k for k in expected_keys if k not in stats]
    if missing:
        print(f"  MISSING KEYS: {missing}")

    if verbose:
        for k, v in stats.items():
            print(f"    {k}: home={v.get('home')}, away={v.get('away')}")

    non_zero_stats = sum(1 for k, v in stats.items()
                         if v.get("home", 0) != 0 or v.get("away", 0) != 0)
    print(f"  Non-zero stats: {non_zero_stats}/{len(stats)}")

    ok = len(stats) >= 10 and non_zero_stats >= 6 and not missing
    print(f"  RESULT: {'PASS' if ok else 'FAIL'}")
    return ok


def test_basketball_reference_team_stats(verbose: bool = False):
    """Test Basketball-Reference team stats page parsing."""
    print("\n" + "=" * 60)
    print("TEST 3: Basketball-Reference Team Stats Page")
    print("=" * 60)

    from adapters.basketball_reference_adapter import parse

    url = "https://www.basketball-reference.com/teams/BOS/2025.html"
    print(f"  Fetching: {url}")

    try:
        resp = requests.get(url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
        }, timeout=20)
        resp.raise_for_status()
        html = resp.text
        print(f"  HTML size: {len(html)} bytes")
    except Exception as e:
        print(f"  FETCH FAILED: {e}")
        return False

    results = parse(html, url)
    print(f"  Parsed results: {len(results)}")

    if not results:
        print("  RESULT: FAIL — no data parsed")
        return False

    result = results[0]
    print(f"  Team: {result.get('team')}")
    averages = result.get("season_averages", {})
    print(f"  Season average keys ({len(averages)}): {list(averages.keys())}")

    if verbose:
        for k, v in averages.items():
            print(f"    {k}: {v}")

    ok = len(averages) >= 8 and result.get("team") != "Unknown"
    print(f"  RESULT: {'PASS' if ok else 'FAIL'}")
    return ok


def test_api_basketball_season(verbose: bool = False):
    """Test API-Basketball dynamic season computation."""
    print("\n" + "=" * 60)
    print("TEST 4: API-Basketball Season Computation")
    print("=" * 60)

    from datetime import datetime

    now = datetime.now()
    season_start = now.year if now.month >= 10 else now.year - 1
    expected_season = f"{season_start}-{season_start + 1}"

    print(f"  Current date: {now.strftime('%Y-%m-%d')}")
    print(f"  Expected season: {expected_season}")

    # Verify by reading the source
    src = Path(PROJECT_ROOT / "src/bet/api_clients/api_basketball.py").read_text()
    has_hardcoded = '"2024-2025"' in src
    has_dynamic = "now.month >= 10" in src or "now.month>=10" in src

    if has_hardcoded:
        print("  WARNING: Still has hardcoded '2024-2025' in source!")
    if has_dynamic:
        print("  Dynamic season computation: CONFIRMED")

    ok = has_dynamic and not has_hardcoded
    print(f"  RESULT: {'PASS' if ok else 'FAIL'}")
    return ok


def test_api_basketball_stat_mapping(verbose: bool = False):
    """Test API-Basketball has all required stat keys in mapping."""
    print("\n" + "=" * 60)
    print("TEST 5: API-Basketball Stat Mapping")
    print("=" * 60)

    src = Path(PROJECT_ROOT / "src/bet/api_clients/api_basketball.py").read_text()

    required_keys = [
        "offensive_rebounds", "defensive_rebounds",
        "fast_break_points", "points_in_paint", "fouls",
    ]
    original_keys = [
        "points", "rebounds", "assists", "steals",
        "blocks", "turnovers", "fg_pct", "three_pct", "ft_pct",
    ]
    all_keys = original_keys + required_keys

    found = []
    missing = []
    for key in all_keys:
        if f'"{key}"' in src:
            found.append(key)
        else:
            missing.append(key)

    print(f"  Found keys ({len(found)}): {found}")
    if missing:
        print(f"  MISSING keys: {missing}")

    ok = not missing
    print(f"  RESULT: {'PASS' if ok else 'FAIL'}")
    return ok


def test_fallback_chain(verbose: bool = False):
    """Test basketball fallback chain includes nba-api."""
    print("\n" + "=" * 60)
    print("TEST 6: Basketball Fallback Chain")
    print("=" * 60)

    src = Path(PROJECT_ROOT / "scripts/fetch_api_stats.py").read_text()

    # Find the basketball chain
    import ast
    for line in src.split("\n"):
        if '"basketball"' in line and "[" in line:
            print(f"  Chain: {line.strip()}")
            break

    has_nba_api = '"nba-api"' in src
    has_espn_first = src.index('"espn-basketball"') < src.index('"nba-api"') if has_nba_api else False
    has_api_bball_after = src.index('"nba-api"') < src.index('"api-basketball"') if has_nba_api else False

    print(f"  nba-api in chain: {has_nba_api}")
    print(f"  ESPN first: {has_espn_first}")
    print(f"  nba-api before api-basketball: {has_api_bball_after}")

    ok = has_nba_api and has_espn_first and has_api_bball_after
    print(f"  RESULT: {'PASS' if ok else 'FAIL'}")
    return ok


def test_balldontlie_deprecated(verbose: bool = False):
    """Test BallDontLie is properly deprecated."""
    print("\n" + "=" * 60)
    print("TEST 7: BallDontLie Deprecation")
    print("=" * 60)

    init_src = Path(PROJECT_ROOT / "scripts/api_clients/__init__.py").read_text()
    bdl_src = Path(PROJECT_ROOT / "scripts/api_clients/balldontlie.py").read_text()

    in_registry = 'CLIENT_REGISTRY["balldontlie"]' in init_src
    has_deprecation = "DEPRECATED" in bdl_src
    has_host_broken = "_HOST_BROKEN = True" in bdl_src

    print(f"  In CLIENT_REGISTRY: {in_registry} (should be False)")
    print(f"  Has deprecation notice: {has_deprecation}")
    print(f"  Has _HOST_BROKEN flag: {has_host_broken}")

    ok = not in_registry and has_deprecation and has_host_broken
    print(f"  RESULT: {'PASS' if ok else 'FAIL'}")
    return ok


def main():
    parser = argparse.ArgumentParser(description="Live test basketball adapters")
    parser.add_argument("--adapter", help="Test specific adapter only")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed output")
    args = parser.parse_args()

    tests = [
        ("bball-ref-schedule", test_basketball_reference_schedule),
        ("bball-ref-boxscore", test_basketball_reference_boxscore),
        ("bball-ref-team", test_basketball_reference_team_stats),
        ("api-basketball-season", test_api_basketball_season),
        ("api-basketball-stats", test_api_basketball_stat_mapping),
        ("fallback-chain", test_fallback_chain),
        ("balldontlie-deprecated", test_balldontlie_deprecated),
    ]

    if args.adapter:
        tests = [(name, fn) for name, fn in tests if args.adapter in name]
        if not tests:
            print(f"No test matching '{args.adapter}'")
            sys.exit(1)

    results = {}
    for name, fn in tests:
        try:
            results[name] = fn(verbose=args.verbose)
        except Exception as e:
            print(f"  EXCEPTION: {e}")
            results[name] = False
        time.sleep(1)

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    for name, ok in results.items():
        print(f"  {'✅' if ok else '❌'} {name}")
    print(f"\n  {passed}/{total} passed")

    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
