#!/usr/bin/env python3
"""Integration verification for Phase 11 — API Client DB Integration.

Tests that all integration points work correctly with real DB.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from bet.db.connection import get_db

passed = 0
failed = 0

def check(name, condition, detail=""):
    global passed, failed
    if condition:
        print(f"  ✅ {name}")
        passed += 1
    else:
        print(f"  ❌ {name}{' — ' + detail if detail else ''}")
        failed += 1


print("=" * 60)
print("Phase 11 — DB Integration Verification")
print("=" * 60)

# 1. deep_data_db_writer imports and works
print("\n[1] deep_data_db_writer module")
try:
    from _helpers.deep_data_db_writer import persist_deep_data_to_db
    check("Import", True)
    
    # Test with mock data
    with get_db() as conn:
        # Get any fixture to test with
        row = conn.execute(
            "SELECT f.id, f.home_team_id, f.away_team_id, f.sport_id "
            "FROM fixtures f LIMIT 1"
        ).fetchone()
        if row:
            fid = row["id"] if isinstance(row, dict) else row[0]
            hid = row["home_team_id"] if isinstance(row, dict) else row[1]
            aid = row["away_team_id"] if isinstance(row, dict) else row[2]
            sid = row["sport_id"] if isinstance(row, dict) else row[3]
            
            # Test with empty deep_data — should not crash
            result = persist_deep_data_to_db(
                conn, fid, hid, aid, sid,
                {"stats": [], "form": {}, "h2h": {}, "odds": []},
                "test"
            )
            check("Empty data handling", result["match_stats_saved"] == 0 and result["team_form_saved"] == 0)
            
            # Test with sample stats
            result = persist_deep_data_to_db(
                conn, fid, hid, aid, sid,
                {"stats": [{"key": "test_corners", "home": "7", "away": "3"}], "form": {}, "h2h": {}, "odds": []},
                "test-integration"
            )
            check("Stats persistence", result["match_stats_saved"] == 2, f"saved={result['match_stats_saved']}")
            
            # Clean up test data
            conn.execute("DELETE FROM match_stats WHERE source='test-integration'")
            conn.commit()
            check("Cleanup", True)
        else:
            check("Has fixtures", False, "no fixtures in DB")
except Exception as e:
    check("Import/Run", False, str(e))

# 2. deep_data_db_writer import works
print("\n[2] deep_data_db_writer _helpers import path")
try:
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_helpers.deep_data_db_writer",
        str(ROOT / "scripts" / "_helpers" / "deep_data_db_writer.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    check("Direct import", hasattr(mod, 'persist_deep_data_to_db'))
except Exception as e:
    check("Direct import", False, str(e))

# 3. UnifiedAPIClient methods exist
print("\n[3] UnifiedAPIClient new methods")
try:
    from bet.api_clients.unified import UnifiedAPIClient
    client = UnifiedAPIClient()
    check("get_corner_predictions exists", hasattr(client, 'get_corner_predictions'))
    check("get_trends exists", hasattr(client, 'get_trends'))
    check("get_dropping_odds exists", hasattr(client, 'get_dropping_odds'))
    client.close()
except Exception as e:
    check("UnifiedAPIClient", False, str(e))

# 4. Odds sources register correctly
print("\n[4] Odds source adapters")
try:
    from odds_sources.oddsportal_source import SOURCE as op_source
    check("OddsPortal source loads", op_source.name == "oddsportal")
    check("OddsPortal sports", len(op_source.supported_sports()) == 5)
except Exception as e:
    check("OddsPortal source", False, str(e))

try:
    from odds_sources.betexplorer_source import SOURCE as be_source
    check("BetExplorer source loads", be_source.name == "betexplorer")
    check("BetExplorer sports", len(be_source.supported_sports()) == 5)
except Exception as e:
    check("BetExplorer source", False, str(e))

# 5. fetch_odds_multi.py source registry
print("\n[5] fetch_odds_multi source registry")
try:
    sys.path.insert(0, str(ROOT / "scripts"))
    from fetch_odds_multi import _SOURCE_MODULES
    check("oddsportal in registry", "oddsportal" in _SOURCE_MODULES)
    check("betexplorer in registry", "betexplorer" in _SOURCE_MODULES)
except Exception as e:
    check("Source registry", False, str(e))

# 6. odds_sources/__init__.py priority chains
print("\n[6] Sport source priority chains")
try:
    from odds_sources import SPORT_SOURCE_PRIORITY
    for sport in ["football", "tennis", "basketball", "hockey", "volleyball"]:
        has_op = "oddsportal" in SPORT_SOURCE_PRIORITY.get(sport, [])
        has_be = "betexplorer" in SPORT_SOURCE_PRIORITY.get(sport, [])
        check(f"{sport}: oddsportal+betexplorer in chain", has_op and has_be)
except Exception as e:
    check("Priority chains", False, str(e))

# 7. data_enrichment_agent client singleton
print("\n[7] data_enrichment_agent client integration")
try:
    from data_enrichment_agent import _get_unified_client, _try_client_enrichment
    check("_get_unified_client exists", callable(_get_unified_client))
    check("_try_client_enrichment exists", callable(_try_client_enrichment))
except Exception as e:
    check("Enrichment agent", False, str(e))

# 8. DB tables have expected columns
print("\n[8] DB schema compatibility")
try:
    with get_db() as conn:
        # Check match_stats has expected columns
        row = conn.execute("PRAGMA table_info(match_stats)").fetchall()
        col_names = [r["name"] if isinstance(r, dict) else r[1] for r in row]
        check("match_stats.fixture_id", "fixture_id" in col_names)
        check("match_stats.team_id", "team_id" in col_names)
        check("match_stats.stat_key", "stat_key" in col_names)
        check("match_stats.stat_value", "stat_value" in col_names)
        check("match_stats.source", "source" in col_names)
        
        # Check team_form has expected columns
        row = conn.execute("PRAGMA table_info(team_form)").fetchall()
        col_names = [r["name"] if isinstance(r, dict) else r[1] for r in row]
        check("team_form.stat_key", "stat_key" in col_names)
        check("team_form.l10_values", "l10_values" in col_names)
        check("team_form.source", "source" in col_names)
except Exception as e:
    check("DB schema", False, str(e))

print("\n" + "=" * 60)
print(f"Results: {passed} passed, {failed} failed")
print("=" * 60)
sys.exit(1 if failed else 0)
