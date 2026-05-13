#!/usr/bin/env python3
"""Phase 9+10 verification — registry completeness + debug script existence.

Verifies:
1. All 5 new clients registered in CLIENT_REGISTRY
2. Rate limiter entries exist for all scrapers
3. unified.py has SOURCE_PRIORITY, ODDS_PRIORITY, STATS_PRIORITY
4. All 5 debug scripts exist
"""
import sys
import os

# Ensure src/ is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def test_registry():
    """Verify all 5 new clients are registered."""
    from bet.api_clients import CLIENT_REGISTRY
    
    expected = ["betexplorer", "oddsportal", "totalcorner", "scores24", "soccerway"]
    missing = [name for name in expected if name not in CLIENT_REGISTRY]
    
    print(f"CLIENT_REGISTRY keys: {sorted(CLIENT_REGISTRY.keys())}")
    print(f"Expected new clients: {expected}")
    
    if missing:
        print(f"FAIL: Missing from registry: {missing}")
        return False
    
    # Verify each is a proper class
    for name in expected:
        cls = CLIENT_REGISTRY[name]
        print(f"  {name} → {cls.__name__} (module: {cls.__module__})")
    
    print("PASS: All 5 new clients registered")
    return True


def test_rate_limiter():
    """Verify rate limiter entries."""
    from bet.api_clients.rate_limiter import API_DAILY_LIMITS
    
    expected = {
        "totalcorner-scraper": 50,
        "scores24-scraper": 100,
        "soccerway-scraper": 100,
        "betexplorer-scraper": 50,
        "oddsportal-scraper": 50,
    }
    
    missing = []
    for name, limit in expected.items():
        if name not in API_DAILY_LIMITS:
            missing.append(name)
            print(f"  FAIL: {name} not in API_DAILY_LIMITS")
        elif API_DAILY_LIMITS[name] != limit:
            print(f"  WARN: {name} limit={API_DAILY_LIMITS[name]}, expected={limit}")
        else:
            print(f"  OK: {name} = {limit}/day")
    
    if missing:
        print(f"FAIL: Missing rate limiter entries: {missing}")
        return False
    
    print("PASS: All rate limiter entries present")
    return True


def test_unified_priorities():
    """Verify unified.py has all priority dicts."""
    from bet.api_clients.unified import SOURCE_PRIORITY, ODDS_PRIORITY, STATS_PRIORITY
    
    print(f"SOURCE_PRIORITY sports: {sorted(SOURCE_PRIORITY.keys())}")
    print(f"ODDS_PRIORITY sports: {sorted(ODDS_PRIORITY.keys())}")
    print(f"STATS_PRIORITY sports: {sorted(STATS_PRIORITY.keys())}")
    
    # Check SOURCE_PRIORITY content
    expected_sources = {
        "football": ["flashscore", "betexplorer", "soccerway", "espn"],
        "tennis": ["flashscore", "scores24", "espn"],
        "basketball": ["flashscore", "betexplorer", "scores24", "espn"],
        "hockey": ["flashscore", "betexplorer", "scores24", "espn"],
        "volleyball": ["flashscore", "betexplorer", "scores24", "espn"],
    }
    for sport, chain in expected_sources.items():
        actual = SOURCE_PRIORITY.get(sport, [])
        if actual != chain:
            print(f"  FAIL: SOURCE_PRIORITY[{sport}] = {actual}, expected {chain}")
            return False
        print(f"  SOURCE_PRIORITY[{sport}] = {actual} ✓")
    
    # Check ODDS_PRIORITY
    for sport in ["football", "tennis", "basketball", "hockey", "volleyball"]:
        chain = ODDS_PRIORITY.get(sport, [])
        if "oddsportal" not in chain or "betexplorer" not in chain:
            print(f"  FAIL: ODDS_PRIORITY[{sport}] missing oddsportal or betexplorer: {chain}")
            return False
        print(f"  ODDS_PRIORITY[{sport}] = {chain} ✓")
    
    # Check STATS_PRIORITY
    football_stats = STATS_PRIORITY.get("football", [])
    if "totalcorner" not in football_stats:
        print(f"  FAIL: STATS_PRIORITY[football] missing totalcorner: {football_stats}")
        return False
    print(f"  STATS_PRIORITY[football] = {football_stats} ✓")
    
    print("PASS: All priority dicts correct")
    return True


def test_debug_scripts():
    """Verify all 5 debug scripts exist."""
    scripts_dir = os.path.join(os.path.dirname(__file__))
    expected = [
        "_debug_betexplorer.py",
        "_debug_oddsportal.py",
        "_debug_totalcorner.py",
        "_debug_scores24.py",
        "_debug_soccerway.py",
    ]
    
    missing = []
    for script in expected:
        path = os.path.join(scripts_dir, script)
        if os.path.exists(path):
            size = os.path.getsize(path)
            print(f"  OK: {script} ({size} bytes)")
        else:
            missing.append(script)
            print(f"  FAIL: {script} not found")
    
    if missing:
        print(f"FAIL: Missing debug scripts: {missing}")
        return False
    
    print("PASS: All 5 debug scripts exist")
    return True


def test_unified_methods():
    """Verify UnifiedAPIClient has get_odds and updated get_fixture_stats."""
    from bet.api_clients.unified import UnifiedAPIClient
    
    client = UnifiedAPIClient()
    
    # Check get_odds exists
    if not hasattr(client, "get_odds"):
        print("FAIL: UnifiedAPIClient missing get_odds method")
        return False
    print("  OK: get_odds method exists")
    
    # Check get_fixture_stats accepts sport parameter
    import inspect
    sig = inspect.signature(client.get_fixture_stats)
    params = list(sig.parameters.keys())
    if "sport" not in params:
        print(f"FAIL: get_fixture_stats missing 'sport' parameter. Params: {params}")
        return False
    print(f"  OK: get_fixture_stats params: {params}")
    
    client.close()
    print("PASS: UnifiedAPIClient methods correct")
    return True


if __name__ == "__main__":
    results = []
    
    print("=" * 60)
    print("PHASE 9+10 VERIFICATION")
    print("=" * 60)
    
    print("\n--- Test 1: CLIENT_REGISTRY ---")
    results.append(test_registry())
    
    print("\n--- Test 2: Rate Limiter ---")
    results.append(test_rate_limiter())
    
    print("\n--- Test 3: Unified Priorities ---")
    results.append(test_unified_priorities())
    
    print("\n--- Test 4: Debug Scripts ---")
    results.append(test_debug_scripts())
    
    print("\n--- Test 5: Unified Methods ---")
    results.append(test_unified_methods())
    
    print("\n" + "=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"RESULT: {passed}/{total} tests passed")
    
    if all(results):
        print("ALL PHASE 9+10 CHECKS PASS ✓")
    else:
        print("SOME CHECKS FAILED ✗")
        sys.exit(1)
