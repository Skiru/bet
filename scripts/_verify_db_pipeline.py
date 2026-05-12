#!/usr/bin/env python3
"""Verify that adapter output → normalization → DB save pipeline preserves key fields."""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from adapters import normalize_adapter_output

# Simulate adapter outputs from each enhanced football adapter
print("=== Test 1: Adapter → Normalize field preservation ===")

test_events = [
    {
        "name": "betexplorer",
        "event": {
            "home": "Manchester City", "away": "Crystal Palace",
            "time": "20:00", "league": "England Premier League",
            "sport": "football", "source_type": "betexplorer",
            "source_url": "https://www.betexplorer.com/football/",
            "odds": {"w1": "1.50", "x": "4.20", "w2": "6.00"},
        },
        "required_fields": ["home", "away", "sport", "source_type", "league"],
    },
    {
        "name": "forebet",
        "event": {
            "home": "Brothers Union", "away": "MSC Limited Dhaka",
            "sport": "football", "source_type": "forebet",
            "source_url": "https://www.forebet.com/...",
            "predictions": {"home_pct": 45, "draw_pct": 30, "away_pct": 25},
            "match_url": "https://www.forebet.com/en/football/matches/brothers-union-msc-limited-dhaka-246",
        },
        "required_fields": ["home", "away", "sport", "source_type", "predictions", "match_url"],
    },
    {
        "name": "sofascore",
        "event": {
            "home": "Celta Vigo", "away": "Levante UD",
            "sport": "football", "source_type": "sofascore_api",
            "league": "Spain - LaLiga",
            "match_url": "https://api.sofascore.com/api/v1/event/14023944/statistics",
            "sofascore_id": "14023944",
        },
        "required_fields": ["home", "away", "sport", "source_type", "match_url", "sofascore_id"],
    },
    {
        "name": "soccerway (raw fallback)",
        "event": {
            "home": "Manchester City", "away": "Crystal Palace",
            "time": "20:00", "sport": "football", "source_type": "soccerway",
            "source_url": "https://int.soccerway.com/matches/...",
        },
        "required_fields": ["home", "away", "sport", "source_type"],
    },
    {
        "name": "totalcorner",
        "event": {
            "home": "Arsenal", "away": "Liverpool",
            "time": "15:00", "sport": "football", "source_type": "totalcorner",
            "corner_count": {"home": 5, "away": 4},
            "cards": {"home": 2, "away": 1},
            "match_url": "https://www.totalcorner.com/match/12345",
        },
        "required_fields": ["home", "away", "sport", "source_type", "corners", "match_url"],
    },
    {
        "name": "whoscored",
        "event": {
            "home": "Barcelona", "away": "Real Madrid",
            "sport": "football", "source_type": "whoscored",
            "corners": {"home": 6, "away": None},
            "shots": {"home": 15, "on_target_home": 8, "away": None, "on_target_away": None},
        },
        "required_fields": ["home", "away", "sport", "source_type"],
    },
]

all_pass = True
for test in test_events:
    normalized = normalize_adapter_output(test["event"], test["name"])
    if normalized is None:
        print(f"  ❌ {test['name']}: normalization returned None!")
        all_pass = False
        continue
    missing = [f for f in test["required_fields"] if not normalized.get(f)]
    if missing:
        print(f"  ❌ {test['name']}: missing fields after normalize: {missing}")
        all_pass = False
    else:
        print(f"  ✅ {test['name']}: all required fields preserved")
    # Verify it's JSON-serializable (as it would be stored in DB)
    try:
        json.dumps(normalized)
    except (TypeError, ValueError) as e:
        print(f"  ❌ {test['name']}: NOT JSON-serializable: {e}")
        all_pass = False

print(f"\n{'✅ ALL PASS' if all_pass else '❌ SOME FAILED'}")

# Test 2: _elo_only filtering
print("\n=== Test 2: _elo_only records filtered ===")
elo_event = {
    "home": "Sinner", "elo_rating": 2331.1,
    "_elo_only": True, "source_type": "tennisabstract_elo",
}
result = normalize_adapter_output(elo_event, "tennisabstract.com")
if result is None:
    print("  ✅ _elo_only record correctly filtered (returns None)")
else:
    print("  ❌ _elo_only record NOT filtered — would pollute scan_results!")
    all_pass = False

# Test 3: Check DB schema
print("\n=== Test 3: DB schema check ===")
from bet.db.connection import get_db
with get_db() as conn:
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(scan_results)")
    cols = {row[1]: row[2] for row in cur.fetchall()}
    required_cols = ["home_team", "away_team", "sport", "source_domain", "raw_data", "competition"]
    for col in required_cols:
        if col in cols:
            print(f"  ✅ {col} ({cols[col]})")
        else:
            print(f"  ❌ {col} MISSING")
            all_pass = False

# Test 4: Check existing data in DB
print("\n=== Test 4: Existing scan_results data ===")
with get_db() as conn:
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM scan_results")
    total = cur.fetchone()[0]
    print(f"  Total scan_results rows: {total}")
    
    cur.execute("SELECT sport, COUNT(*) FROM scan_results GROUP BY sport ORDER BY COUNT(*) DESC")
    for row in cur.fetchall():
        print(f"    {row[0]}: {row[1]} rows")
    
    if total > 0:
        cur.execute("SELECT source_domain, COUNT(*) FROM scan_results GROUP BY source_domain ORDER BY COUNT(*) DESC LIMIT 10")
        print("  Top sources:")
        for row in cur.fetchall():
            print(f"    {row[0]}: {row[1]} rows")
        
        # Check a sample raw_data has expected adapter fields
        cur.execute("SELECT raw_data FROM scan_results WHERE sport='football' AND raw_data IS NOT NULL LIMIT 1")
        sample_row = cur.fetchone()
        if sample_row and sample_row[0]:
            try:
                raw = json.loads(sample_row[0])
                print(f"\n  Sample football raw_data keys: {sorted(raw.keys())}")
                print(f"    sport={raw.get('sport')}, source_type={raw.get('source_type')}")
                has_enriched = any(k in raw for k in ["corners", "cards", "predictions", "match_url", "odds"])
                print(f"    Has enriched fields: {has_enriched}")
            except json.JSONDecodeError:
                print("  ⚠️ raw_data not valid JSON")

print(f"\n{'=' * 60}")
print(f"{'✅ ALL PIPELINE CHECKS PASS' if all_pass else '❌ SOME CHECKS FAILED'}")
