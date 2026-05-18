"""Comprehensive SerpAPI sports query test — different patterns, sports, upcoming matches.

Tests multiple query patterns to find what gives DEEPEST data.
Each query costs 1 SerpAPI credit (250/month budget).
"""

import json
import sys
import time
from pathlib import Path

import requests

# Load API key
config_path = Path(__file__).parent.parent / "config" / "api_keys.json"
with open(config_path) as f:
    keys = json.load(f)

SERPAPI_KEY = keys.get("serpapi", "")
OUTPUT_DIR = Path(__file__).parent.parent / "betting" / "data" / "stats_cache" / "serpapi_tests"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def serpapi_query(query: str, extra_params: dict = None) -> dict:
    """Execute SerpAPI query and return parsed JSON."""
    params = {
        "q": query,
        "api_key": SERPAPI_KEY,
        "engine": "google",
    }
    if extra_params:
        params.update(extra_params)

    response = requests.get("https://serpapi.com/search.json", params=params, timeout=20)
    if response.status_code != 200:
        print(f"  ❌ HTTP {response.status_code}: {response.text[:200]}")
        return {}
    return response.json()


def analyze_sports_data(data: dict, label: str) -> dict:
    """Extract and summarize sports data from SerpAPI response."""
    sr = data.get("sports_results", {})
    kg = data.get("knowledge_graph", {})
    
    summary = {
        "label": label,
        "has_sports_results": bool(sr),
        "has_knowledge_graph": bool(kg),
        "sports_results_keys": list(sr.keys()) if sr else [],
        "knowledge_graph_keys": list(kg.keys())[:15] if kg else [],
    }
    
    if sr:
        spotlight = sr.get("game_spotlight", sr.get("match", {}))
        if spotlight:
            teams = spotlight.get("teams", [])
            summary["teams"] = [t.get("name", "") for t in teams]
            summary["scores"] = [t.get("score", "") for t in teams]
            summary["status"] = spotlight.get("status", "")
            summary["league"] = spotlight.get("league", "")
            summary["date"] = spotlight.get("date", "")
            summary["stadium"] = spotlight.get("stadium", "")
            
            # Check for statistics
            if "statistics" in spotlight or "stats" in spotlight:
                summary["has_match_stats"] = True
                summary["stats_data"] = spotlight.get("statistics", spotlight.get("stats"))
            
            # Check for goal details
            for team in teams:
                goals = team.get("goal_summary", [])
                if goals:
                    summary.setdefault("goal_details", []).extend([
                        f"{g['player']['name']} {g['goals'][0]['in_game_time']['minute']}'"
                        for g in goals if "player" in g and "goals" in g
                    ])
        
        # Check for other sports_results sub-keys
        for key in ["games", "standings", "game_results", "tournament", "statistics",
                    "match_statistics", "head_to_head", "previous_encounters"]:
            if key in sr:
                summary[f"has_{key}"] = True
                val = sr[key]
                if isinstance(val, list):
                    summary[f"{key}_count"] = len(val)
                elif isinstance(val, dict):
                    summary[f"{key}_keys"] = list(val.keys())[:10]
    
    return summary


# ============================================================
# TEST QUERIES — different patterns and sports
# ============================================================
TEST_QUERIES = [
    # Football — tomorrow's likely matches (May 18, 2026 is a Sunday — big football day)
    ("Barcelona vs Real Sociedad", {}),
    ("Manchester City vs Arsenal", {}),
    # Football — with "statistics" keyword
    ("PSG vs Paris FC statistics", {}),
    # Tennis — Roland Garros should be starting soon
    ("Djokovic vs Alcaraz", {}),
    # Basketball — NBA playoffs
    ("Lakers vs Celtics", {}),
    # Hockey — NHL playoffs  
    ("Oilers vs Panthers", {}),
    # With hl=pl (Polish) to see if we get different data
    ("Real Madrid vs Barcelona", {"hl": "pl"}),
]

print(f"\n{'='*70}")
print(f"SerpAPI COMPREHENSIVE SPORTS QUERY TEST")
print(f"Testing {len(TEST_QUERIES)} queries — will cost {len(TEST_QUERIES)} credits")
print(f"{'='*70}\n")

all_results = {}
all_summaries = []

for i, (query, extra_params) in enumerate(TEST_QUERIES):
    print(f"\n[{i+1}/{len(TEST_QUERIES)}] Query: '{query}' {extra_params or ''}")
    print(f"{'─'*50}")
    
    data = serpapi_query(query, extra_params)
    if not data:
        print("  ⚠️  Empty response")
        continue
    
    # Save full response
    safe_name = query.lower().replace(" ", "_").replace("/", "_")[:50]
    with open(OUTPUT_DIR / f"{safe_name}.json", "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    # Analyze
    summary = analyze_sports_data(data, query)
    all_summaries.append(summary)
    all_results[query] = data
    
    # Print summary
    if summary["has_sports_results"]:
        print(f"  ✅ SPORTS RESULTS found!")
        print(f"     Keys: {summary['sports_results_keys']}")
        if "teams" in summary:
            print(f"     Teams: {summary['teams']}")
            print(f"     Scores: {summary['scores']}")
            print(f"     Status: {summary['status']}")
            print(f"     League: {summary['league']}")
        if summary.get("has_match_stats"):
            print(f"     🎯 MATCH STATISTICS FOUND!")
            print(f"     Stats: {json.dumps(summary.get('stats_data', ''))[:200]}")
        if "goal_details" in summary:
            print(f"     Goals: {summary['goal_details']}")
        for key in summary:
            if key.startswith("has_") and key != "has_sports_results" and key != "has_knowledge_graph" and key != "has_match_stats":
                print(f"     📊 {key}: {summary.get(key)}")
    else:
        print(f"  ⚠️  No sports_results")
    
    if summary["has_knowledge_graph"]:
        print(f"  📖 Knowledge Graph: {summary['knowledge_graph_keys'][:8]}")
    
    # Rate limit courtesy
    time.sleep(1)

# ============================================================
# SUMMARY
# ============================================================
print(f"\n\n{'='*70}")
print("SUMMARY OF ALL QUERIES")
print(f"{'='*70}")
for s in all_summaries:
    emoji = "✅" if s["has_sports_results"] else "❌"
    stats = "📊" if s.get("has_match_stats") else "  "
    print(f"  {emoji} {stats} {s['label']}")
    if s.get("teams"):
        print(f"       {' vs '.join(s['teams'])} | {':'.join(s['scores'])} | {s['status']}")

# Save all summaries
with open(OUTPUT_DIR / "_all_summaries.json", "w") as f:
    json.dump(all_summaries, f, indent=2, ensure_ascii=False)

print(f"\n\nAll results saved to: {OUTPUT_DIR}")
print(f"Total credits used: {len(TEST_QUERIES)}")
