"""Quick live test: SerpAPI 'team vs team' query to see actual JSON structure.

Usage: PYTHONPATH=src .venv/bin/python scripts/test_serpapi_vs_query.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import requests

# Load API key
config_path = Path(__file__).parent.parent / "config" / "api_keys.json"
with open(config_path) as f:
    keys = json.load(f)

SERPAPI_KEY = keys.get("serpapi", "")
if not SERPAPI_KEY:
    print("ERROR: No SerpAPI key found")
    sys.exit(1)

# Test query: PSG vs Paris FC (from user's Google search)
query = "PSG vs Paris FC"
print(f"\n{'='*60}")
print(f"Testing SerpAPI query: '{query}'")
print(f"{'='*60}\n")

response = requests.get(
    "https://serpapi.com/search.json",
    params={
        "q": query,
        "api_key": SERPAPI_KEY,
        "engine": "google",
    },
    timeout=20,
)

print(f"HTTP Status: {response.status_code}")
if response.status_code != 200:
    print(f"Error: {response.text[:500]}")
    sys.exit(1)

data = response.json()

# Save full response for inspection
output_path = Path(__file__).parent.parent / "betting" / "data" / "stats_cache" / "serpapi_vs_test.json"
output_path.parent.mkdir(parents=True, exist_ok=True)
with open(output_path, "w") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
print(f"\nFull response saved to: {output_path}")

# Extract and display the interesting parts
print(f"\n{'='*60}")
print("TOP-LEVEL KEYS:")
print(f"{'='*60}")
for key in data.keys():
    val = data[key]
    if isinstance(val, dict):
        print(f"  {key}: dict with {len(val)} keys → {list(val.keys())[:8]}")
    elif isinstance(val, list):
        print(f"  {key}: list with {len(val)} items")
    elif isinstance(val, str) and len(val) > 100:
        print(f"  {key}: str ({len(val)} chars)")
    else:
        print(f"  {key}: {val}")

# Focus on sports_results
sr = data.get("sports_results", {})
if sr:
    print(f"\n{'='*60}")
    print("SPORTS_RESULTS:")
    print(f"{'='*60}")
    print(json.dumps(sr, indent=2, ensure_ascii=False)[:3000])
else:
    print("\n⚠️  No 'sports_results' key found!")
    # Check other possible containers
    for candidate in ["knowledge_graph", "answer_box", "sports_card"]:
        if candidate in data:
            print(f"\n  Found '{candidate}':")
            print(json.dumps(data[candidate], indent=2, ensure_ascii=False)[:2000])

# Check knowledge_graph too
kg = data.get("knowledge_graph", {})
if kg:
    print(f"\n{'='*60}")
    print("KNOWLEDGE_GRAPH:")
    print(f"{'='*60}")
    print(json.dumps(kg, indent=2, ensure_ascii=False)[:2000])

print(f"\n{'='*60}")
print("DONE — Check betting/data/stats_cache/serpapi_vs_test.json for full response")
print(f"{'='*60}")
