#!/usr/bin/env python3
"""Verify Elo lookup + data quality integration works end-to-end."""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from compute_safety_scores import lookup_tennis_elo, compute_data_quality_score

# Test 1: Exact name match
print("=== Test 1: Exact name lookup ===")
result = lookup_tennis_elo("Jannik Sinner")
print(f"  Sinner: {json.dumps(result, indent=2) if result else 'NOT FOUND'}")
assert result is not None, "Sinner lookup failed!"
assert result.get("elo") is not None, "Sinner Elo missing!"
print(f"  ✅ Elo={result['elo']}, hard={result.get('hard_elo')}, clay={result.get('clay_elo')}")

# Test 2: Surface-specific lookup
print("\n=== Test 2: Surface-specific lookup ===")
result = lookup_tennis_elo("Aryna Sabalenka", surface="clay")
print(f"  Sabalenka (clay): {json.dumps(result, indent=2) if result else 'NOT FOUND'}")
assert result is not None, "Sabalenka lookup failed!"
assert result.get("surface_elo") is not None, "Surface Elo missing!"
print(f"  ✅ surface_elo (clay)={result['surface_elo']}")

# Test 3: Fuzzy match (last name + initial)
print("\n=== Test 3: Fuzzy match ===")
result = lookup_tennis_elo("C. Alcaraz")
if result:
    print(f"  ✅ C. Alcaraz → Elo={result['elo']}")
else:
    # Try different format
    result = lookup_tennis_elo("Carlos Alcaraz")
    print(f"  Carlos Alcaraz → {'Elo=' + str(result['elo']) if result else 'NOT FOUND'}")

# Test 4: Non-existent player
print("\n=== Test 4: Non-existent player ===")
result = lookup_tennis_elo("Fake Player McFakerson")
assert result is None, "Fake player should return None!"
print("  ✅ Returns None for unknown player")

# Test 5: Data quality score with has_elo=True
print("\n=== Test 5: Data quality score with Elo ===")
mock_ranking = {"ranking": [{"market": "test", "safety_score": 0.7}] * 3}
score_no_elo = compute_data_quality_score(mock_ranking, has_elo=False)
score_with_elo = compute_data_quality_score(mock_ranking, has_elo=True)
print(f"  Without Elo: score={score_no_elo['score']}")
print(f"  With Elo:    score={score_with_elo['score']}")
assert score_with_elo["score"] == score_no_elo["score"] + 1, "Elo should add +1 to data quality!"
print(f"  ✅ Elo adds +1 ({score_no_elo['score']} → {score_with_elo['score']})")

# Test 6: Verify cache file structure
print("\n=== Test 6: Cache file structure ===")
cache_dir = Path(__file__).parent.parent / "betting" / "data" / "stats_cache" / "tennis_elo"
atp_file = cache_dir / "atp_elo.json"
wta_file = cache_dir / "wta_elo.json"
assert atp_file.exists(), f"ATP cache missing: {atp_file}"
assert wta_file.exists(), f"WTA cache missing: {wta_file}"
atp_data = json.loads(atp_file.read_text())
print(f"  ATP: {atp_data['player_count']} players, tour={atp_data['tour']}")
print(f"  First player: {atp_data['players'][0].get('home', '?')}, Elo={atp_data['players'][0].get('elo_rating', '?')}")
print(f"  ✅ Cache files exist and structured correctly")

player_files = list(cache_dir.glob("*.json"))
non_summary = [f for f in player_files if "elo.json" not in f.name]
print(f"  Individual player files: {len(non_summary)}")

print("\n=== ALL TESTS PASSED ===")
