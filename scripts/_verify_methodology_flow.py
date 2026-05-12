#!/usr/bin/env python3
"""End-to-end methodology data flow verification for tennis adapters."""
import sys, json, requests
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}

# Test 1: TennisExplorer parsing → normalization → verify no _elo_only leaks
print("=== Test 1: TennisExplorer → normalize → verify data quality ===")
from adapters.tennisexplorer_adapter import parse as te_parse
from adapters import normalize_adapter_output

resp = requests.get("https://www.tennisexplorer.com/matches/", headers=HEADERS, timeout=30)
te_events = te_parse(resp.text, "https://www.tennisexplorer.com/matches/")
print(f"  TennisExplorer raw: {len(te_events)} matches")
if te_events:
    sample = te_events[0]
    print(f"  Sample: {sample.get('home')} vs {sample.get('away')}, league={sample.get('league')}")
    normalized = normalize_adapter_output(sample, "tennisexplorer")
    assert normalized is not None, "Tennis match should NOT be filtered!"
    print(f"  ✅ Normalization passes (not filtered)")
    print(f"  home={normalized.get('home')}, away={normalized.get('away')}, sport={normalized.get('sport')}")
    print(f"  match_url={normalized.get('match_url', 'N/A')}")
    print(f"  surface={normalized.get('surface', 'N/A')}")

# Test 2: TennisAbstract Elo → normalize → verify _elo_only IS filtered
print("\n=== Test 2: TennisAbstract Elo → normalize → verify filtered ===")
from adapters.tennisabstract_adapter import parse as ta_parse

resp = requests.get("https://www.tennisabstract.com/reports/atp_elo_ratings.html", headers=HEADERS, timeout=30)
ta_events = ta_parse(resp.text, "https://www.tennisabstract.com/reports/atp_elo_ratings.html")
print(f"  TennisAbstract raw: {len(ta_events)} Elo records")
if ta_events:
    sample = ta_events[0]
    print(f"  Sample: {sample.get('home')}, _elo_only={sample.get('_elo_only')}")
    normalized = normalize_adapter_output(sample, "tennisabstract.com")
    assert normalized is None, "Elo records SHOULD be filtered out!"
    print(f"  ✅ Elo record correctly filtered (returns None)")

# Test 3: normalize_batch filters correctly
print("\n=== Test 3: normalize_batch mixed input ===")
from adapters import normalize_batch

mixed = []
if te_events:
    mixed.extend(te_events[:2])  # 2 real matches
if ta_events:
    mixed.extend(ta_events[:3])  # 3 elo records
print(f"  Input: {len(mixed)} items ({sum(1 for e in mixed if not e.get('_elo_only'))} matches + {sum(1 for e in mixed if e.get('_elo_only'))} elo)")
batch_result = normalize_batch(mixed, "mixed")
print(f"  Output: {len(batch_result)} items (Elo filtered out)")
assert all(r is not None for r in batch_result), "No None values should be in batch result!"
elo_in_output = sum(1 for r in batch_result if r.get("_elo_only"))
assert elo_in_output == 0, f"Found {elo_in_output} Elo records in output!"
print(f"  ✅ Batch filtering works correctly")

# Test 4: Deep link patterns for TennisExplorer
print("\n=== Test 4: Deep link discovery patterns ===")
from deep_link_discovery import DOMAIN_PATTERNS
import re

te_patterns = DOMAIN_PATTERNS.get("tennisexplorer.com", {})
include = te_patterns.get("include", [])
exclude = te_patterns.get("exclude", [])
print(f"  TennisExplorer: {len(include)} include patterns, {len(exclude)} exclude patterns")

test_urls = [
    ("/match-detail/abc123", True),
    ("/match-detail/?id=456", True),
    ("/head-to-head/player1-vs-player2/", True),
    ("/atp-roland-garros/", True),
    ("/news/some-article", False),
    ("/player/jannik-sinner/", False),
]
for url, should_match in test_urls:
    matched = any(p.search(url) for p in include)
    excluded = any(p.search(url) for p in exclude)
    result = matched and not excluded
    status = "✅" if result == should_match else "❌"
    print(f"  {status} {url} → {'INCLUDE' if result else 'EXCLUDE'} (expected: {'INCLUDE' if should_match else 'EXCLUDE'})")

# Test 5: Tennis scanner stat keys alignment
print("\n=== Test 5: Tennis scanner stat keys ===")
from scanners.tennis_scanner import TennisScanner
scanner = TennisScanner()
print(f"  required_stat_keys: {scanner.required_stat_keys}")
print(f"  desired_stat_keys: {scanner.desired_stat_keys}")
# Verify these match what ESPN actually produces
espn_keys = {"games_won", "sets_won", "total_games"}
required = set(scanner.required_stat_keys)
assert required == espn_keys, f"Mismatch: {required} vs {espn_keys}"
print(f"  ✅ Required keys match ESPN linescore output")

print("\n=== ALL METHODOLOGY TESTS PASSED ===")
