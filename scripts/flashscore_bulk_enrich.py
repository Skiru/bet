#!/usr/bin/env python3
"""Flashscore results-page bulk enrichment for today's fixtures.

Uses curl_cffi via flashscore_enricher._try_flashscore() — the proven path.
This script no longer attempts deep Flashscore match-stat enrichment from the
retired tokenized feed. It only writes stats derivable from the stable
Flashscore search/results-page flow.

Usage:
    python3 scripts/flashscore_bulk_enrich.py --date 2026-05-20 --sport football
    python3 scripts/flashscore_bulk_enrich.py --date 2026-05-20 --limit 200
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from bet.db.connection import get_db
from bet.stats.stat_validation import is_valid_stat_key
from bet.stats.value_ranges import SPORT_VALUE_RANGES
from flashscore_enricher import (_try_flashscore,)
from _helpers.football_flashscore_html_enrichment import (
    complete_football_rich_stats,
    get_football_rich_stat_keys,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("fs_bulk")

def _try_flashscore_results_page(team_name: str, sport: str) -> tuple[dict, str | None]:
    """Fetch only stable results-page stats from Flashscore.

    Deep match-stat enrichment via Flashscore's tokenized feed is retired.
    Canonical deep stats now belong to provider-backed enrichment flows.
    """
    return _try_flashscore(team_name, sport)


def get_teams_needing_enrichment(date: str, sport: str | None = None, min_stats: int = 3, limit: int = 0) -> list[dict]:
    """Get teams from today's fixtures missing stats."""
    query = """
        SELECT DISTINCT t.id as team_id, t.name as team_name, s.name as sport, s.id as sport_id
        FROM fixtures f
        JOIN sports s ON f.sport_id = s.id
        JOIN teams t ON (t.id = f.home_team_id OR t.id = f.away_team_id)
        WHERE f.kickoff LIKE ?
        AND s.name != 'tennis'
        AND (SELECT COUNT(*) FROM team_form tf WHERE tf.team_id = t.id AND tf.sport_id = s.id AND tf.l5_avg IS NOT NULL) < ?
    """
    params: list = [f"{date}%", min_stats]
    
    if sport:
        query += " AND s.name = ?"
        params.append(sport)
    
    query += " ORDER BY (SELECT COUNT(*) FROM fixtures f2 WHERE (f2.home_team_id = t.id OR f2.away_team_id = t.id) AND f2.kickoff LIKE ?) DESC"
    params.append(f"{date}%")
    
    if limit:
        query += " LIMIT ?"
        params.append(limit)
    
    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def enrich_and_write(teams: list[dict], verbose: bool = False, deep: bool = True) -> dict:
    """Enrich teams via Flashscore and write stats to DB.
    
    Args:
        deep: Deprecated compatibility flag. Results-page enrichment is always
              used; canonical deep stats belong to provider-backed flows.
    """
    enriched = 0
    failed = 0
    skipped = 0
    stats_written = 0
    flashscore_successes = 0
    flashscore_html_fallback_successes = 0
    unresolved_misses = 0
    flashscore_html_matches_persisted = 0
    start_time = time.time()

    with get_db() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        now = datetime.now(timezone.utc).isoformat()
        
        for i, team in enumerate(teams):
            team_name = team["team_name"]
            sport = team["sport"]
            team_id = team["team_id"]
            sport_id = team["sport_id"]

            stats, error = _try_flashscore_results_page(team_name, sport)
            flashscore_rich_keys = get_football_rich_stat_keys(stats) if sport == "football" else set()
            flashscore_success = bool(stats)
            flashscore_missed = not flashscore_success and not (error and "skipped" in error.lower())
            
            if stats:
                # Write each stat key to team_form
                for stat_key, values in stats.items():
                    if not values:
                        continue
                    
                    # Stat key validation — prevent cross-sport contamination
                    if not is_valid_stat_key(sport, stat_key):
                        if verbose:
                            log.debug("  REJECTED stat_key=%s for sport=%s (contamination)", stat_key, sport)
                        continue
                    
                    # Value range validation
                    ranges = SPORT_VALUE_RANGES.get(sport, {}).get(stat_key)
                    if ranges:
                        lo, hi = ranges
                        values = [v for v in values if lo <= v <= hi]
                        if not values:
                            if verbose:
                                log.debug("  REJECTED stat_key=%s: all values outside range [%s, %s]", stat_key, lo, hi)
                            continue
                    
                    avg = round(sum(values) / len(values), 2)
                    vals_json = json.dumps(values[:10])
                    l5_vals = values[:5]
                    l5_avg = round(sum(l5_vals) / len(l5_vals), 2) if l5_vals else avg
                    
                    conn.execute("""
                        INSERT OR REPLACE INTO team_form (team_id, sport_id, stat_key, l5_avg, l5_values, l10_avg, l10_values, updated_at, source)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (team_id, sport_id, stat_key, l5_avg, json.dumps(l5_vals), avg, vals_json, now, "flashscore"))
                    stats_written += 1
                
                enriched += 1
                flashscore_successes += 1
                if enriched % 10 == 0:
                    conn.commit()
            elif error and "skipped" in error.lower():
                skipped += 1
            else:
                if verbose:
                    log.debug("  [%d/%d] MISS %s: %s", i+1, len(teams), team_name, error)

            flashscore_html_result = None
            if sport == "football" and not flashscore_rich_keys:
                flashscore_html_result = complete_football_rich_stats(team_name, sport, max_fixtures=5)
                if flashscore_html_result.get("rich_keys_found"):
                    flashscore_html_fallback_successes += 1
                    flashscore_html_matches_persisted += flashscore_html_result.get("matches_persisted", 0)
                    if not flashscore_success:
                        enriched += 1
                else:
                    unresolved_misses += 1

            if flashscore_missed and not (flashscore_html_result and flashscore_html_result.get("rich_keys_found")):
                failed += 1

            if sport == "football" and flashscore_success and not flashscore_rich_keys and flashscore_html_result and flashscore_html_result.get("rich_keys_found"):
                log.debug("  [%d/%d] Flashscore HTML fallback added rich keys for %s: %s", i + 1, len(teams), team_name, flashscore_html_result.get("rich_keys_found"))
            
            if (i + 1) % 20 == 0:
                elapsed = time.time() - start_time
                rate = (i + 1) / elapsed if elapsed > 0 else 0
                eta = (len(teams) - i - 1) / rate if rate > 0 else 0
                log.info(
                    "[%d/%d] enriched=%d failed=%d (%.1f/min, ETA %.0fs)",
                    i + 1, len(teams), enriched, failed, rate * 60, eta
                )
        
        conn.commit()
    
    elapsed = time.time() - start_time
    return {
        "enriched": enriched,
        "failed": failed,
        "skipped": skipped,
        "flashscore_successes": flashscore_successes,
        "flashscore_html_fallback_successes": flashscore_html_fallback_successes,
        "unresolved_misses": unresolved_misses,
        "flashscore_html_matches_persisted": flashscore_html_matches_persisted,
        "stats_written": stats_written,
        "elapsed_seconds": round(elapsed, 1),
    }


def main():
    parser = argparse.ArgumentParser(description="Flashscore results-page bulk enrichment")
    parser.add_argument("--date", required=True)
    parser.add_argument("--sport", help="Filter by sport")
    parser.add_argument("--limit", type=int, default=0, help="Max teams to process")
    parser.add_argument("--min-stats", type=int, default=3)
    parser.add_argument(
        "--deep",
        action="store_true",
        default=True,
        help="Deprecated compatibility flag. Flashscore deep match stats are retired.",
    )
    parser.add_argument(
        "--shallow",
        action="store_true",
        help="Deprecated compatibility flag. Results-page enrichment is always used.",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    deep = not args.shallow
    if deep:
        log.info(
            "Flashscore deep match stats retired; using results-page enrichment only. "
            "Use provider-backed enrichment for canonical deep stats."
        )
    elif args.shallow:
        log.debug("Results-page enrichment only mode selected")
    
    teams = get_teams_needing_enrichment(args.date, args.sport, args.min_stats, args.limit)
    log.info("Teams to enrich: %d (mode=results-page-only)", len(teams))
    
    if not teams:
        print("AGENT_SUMMARY:" + json.dumps({"verdict": "OK", "message": "All teams enriched"}))
        return
    
    result = enrich_and_write(teams, verbose=args.verbose, deep=deep)
    
    log.info("=" * 60)
    log.info("DONE in %.1fs: enriched=%d, failed=%d, stats=%d",
             result["elapsed_seconds"], result["enriched"], result["failed"], result["stats_written"])
    
    print("\nAGENT_SUMMARY:" + json.dumps({
        "verdict": "OK" if result["enriched"] > 50 else "PARTIAL",
        "enriched": result["enriched"],
        "failed": result["failed"],
        "skipped": result["skipped"],
        "flashscore_successes": result["flashscore_successes"],
        "flashscore_html_fallback_successes": result["flashscore_html_fallback_successes"],
        "unresolved_misses": result["unresolved_misses"],
        "flashscore_html_matches_persisted": result["flashscore_html_matches_persisted"],
        "stats_written": result["stats_written"],
        "elapsed_seconds": result["elapsed_seconds"],
        "total_teams": len(teams),
    }))


if __name__ == "__main__":
    main()
