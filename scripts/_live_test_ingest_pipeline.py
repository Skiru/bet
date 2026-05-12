#!/usr/bin/env python3
"""Live integration test: adapter → normalizer → ingest → DB/cache.

Fetches real data from a working adapter, normalizes it, ingests it,
and verifies the enriched fields land in the stats cache and DB.

Usage:
    python3 scripts/_live_test_ingest_pipeline.py [--verbose]
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

import requests
from adapters import ADAPTERS, normalize_adapter_output
from adapters.totalcorner_adapter import parse as totalcorner_parse


def main():
    verbose = "--verbose" in sys.argv or "-v" in sys.argv

    print("=" * 70)
    print("LIVE INTEGRATION TEST: Adapter → Normalizer → Ingest → DB")
    print("=" * 70)

    # Step 1: Fetch real data from totalcorner (best enriched source: corners + cards)
    print("\n[1] Fetching real data from totalcorner.com...")
    url = "https://www.totalcorner.com/match/today"
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(3000)
            html = page.content()
            browser.close()
    except Exception as e:
        print(f"  ❌ Playwright fetch failed: {e}")
        print("  Falling back to requests...")
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        html = resp.text

    print(f"  Fetched {len(html)} bytes")

    # Step 2: Parse through adapter
    print("\n[2] Parsing through totalcorner adapter...")
    raw_events = totalcorner_parse(html, url)
    print(f"  Parsed {len(raw_events)} raw events")

    if not raw_events:
        print("  ❌ No events parsed — cannot continue test")
        return

    # Step 3: Normalize
    print("\n[3] Normalizing events...")
    events = []
    for ev in raw_events[:20]:  # Take first 20 for speed
        events.append(normalize_adapter_output(ev, source_type="totalcorner.com"))
    print(f"  Normalized {len(events)} events")

    # Check enrichment quality
    enriched_counts = {}
    for ev in events:
        for key in ["corners", "cards", "standings", "sport", "source_type", "league"]:
            val = ev.get(key)
            if val is not None and val != {} and val != "":
                enriched_counts[key] = enriched_counts.get(key, 0) + 1

    print(f"  Enrichment breakdown: {json.dumps(enriched_counts)}")

    if verbose:
        sample = events[0]
        print(f"  Sample event:")
        for k in ["home", "away", "time", "league", "sport", "source_type", "corners", "cards", "standings"]:
            print(f"    {k}: {sample.get(k)}")

    # Step 4: Test ingest with these events
    print("\n[4] Testing ingest pipeline...")
    import ingest_scan_stats as iss

    # Use a temp cache dir to avoid polluting real cache
    import tempfile
    tmp_cache = Path(tempfile.mkdtemp(prefix="live_test_ingest_"))
    original_cache_dir = iss.CACHE_DIR
    iss.CACHE_DIR = tmp_cache

    ingested = 0
    enriched_stats_found = 0
    for ev in events[:5]:  # Ingest first 5 events
        try:
            result = iss.ingest_event(url, ev)
            ingested += 1

            # Check if cache files were created with enriched stats
            home = ev.get("home", "")
            if home:
                # Cache files are in sport subdirs with slug names
                slug = home.lower().replace(" ", "-")
                matching = list(tmp_cache.rglob(f"*{slug}*.json"))
                for cache_file in matching:
                    data = json.loads(cache_file.read_text())
                    scan_stats = data.get("scan_stats", {})
                    enriched_keys = [k for k in ["corners_per_game", "yellow_cards_per_game",
                                                  "fouls_per_game", "shots_per_game",
                                                  "league_position", "dangerous_attacks"]
                                     if k in scan_stats]
                    if enriched_keys:
                        enriched_stats_found += 1
                        if verbose:
                            print(f"    {home}: enriched stats = {enriched_keys}")
                            for k in enriched_keys:
                                print(f"      {k}: {scan_stats[k]}")
        except Exception as e:
            print(f"  ⚠️ Ingest error for {ev.get('home', '?')} vs {ev.get('away', '?')}: {e}")

    print(f"  Ingested: {ingested} events")
    print(f"  Events with enriched stats in cache: {enriched_stats_found}")

    # Step 5: List cache files (they're in sport subdirectories with slug names)
    cache_files = list(tmp_cache.rglob("*.json"))
    print(f"\n[5] Cache files created: {len(cache_files)}")
    if verbose and cache_files:
        for f in cache_files[:5]:
            data = json.loads(f.read_text())
            scan = data.get("scan_stats", {})
            enriched = {k: v for k, v in scan.items()
                        if k in ["corners_per_game", "yellow_cards_per_game", "red_cards_per_game",
                                 "fouls_per_game", "shots_per_game", "league_position",
                                 "dangerous_attacks", "prob_home", "prob_draw", "prob_away"]}
            print(f"  {f.name}: {len(scan)} total stats, enriched={enriched}")

    # Cleanup
    iss.CACHE_DIR = original_cache_dir
    import shutil
    shutil.rmtree(tmp_cache, ignore_errors=True)

    # Verdict
    print("\n" + "=" * 70)
    if ingested > 0 and enriched_stats_found > 0:
        print(f"✅ PASS: Pipeline works end-to-end. {ingested} ingested, {enriched_stats_found} with enriched stats.")
    elif ingested > 0:
        print(f"⚠️ PARTIAL: {ingested} ingested but 0 with enriched stats — check ingest_event enriched handling.")
    else:
        print(f"❌ FAIL: 0 events ingested.")

    print("AGENT_SUMMARY:" + json.dumps({
        "verdict": "PASS" if enriched_stats_found > 0 else "PARTIAL" if ingested > 0 else "FAIL",
        "events_fetched": len(raw_events),
        "events_normalized": len(events),
        "events_ingested": ingested,
        "enriched_stats_found": enriched_stats_found,
    }))


if __name__ == "__main__":
    main()
