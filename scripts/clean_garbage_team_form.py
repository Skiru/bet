#!/usr/bin/env python3
import json
import argparse
import logging
import sqlite3
import sys
from pathlib import Path

# Add project root and scripts dir to path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from bet.db.connection import get_db

try:
    from data_enrichment_agent import SPORT_VALUE_RANGES
except ImportError:
    # fallback
    SPORT_VALUE_RANGES = {
        "football": {
            "corners": (0, 20),
            "fouls": (0, 35),
            "yellow_cards": (0, 12),
            "red_cards": (0, 4),
            "shots": (0, 40),
            "goals": (0, 12),
            "possession": (20, 80)
        }
    }

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

def _safe_avg(vals: list[int]) -> float:
    return float(sum(vals))/len(vals) if vals else 0.0

def main():
    parser = argparse.ArgumentParser(description="Clean garbage data in team_form table")
    parser.add_argument("--dry-run", action="store_true", help="Don't write DB changes")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    deleted_rows = 0
    updated_rows = 0
    
    with get_db() as conn:
        conn.row_factory = sqlite3.Row
        
        for sport, ranges in SPORT_VALUE_RANGES.items():
            for stat_key, bounds in ranges.items():
                lo, hi = bounds
                
                query = """
                SELECT tf.id, t.name as team_name, tf.stat_key, tf.l10_values, tf.l5_values, tf.l10_avg
                FROM team_form tf
                JOIN teams t ON t.id = tf.team_id
                JOIN sports sp ON sp.id = tf.sport_id
                WHERE sp.name = ? AND tf.stat_key = ?
                  AND (tf.l10_avg > ? OR tf.l10_avg < ?)
                """
                rows = conn.execute(query, (sport, stat_key, hi, lo)).fetchall()
                
                for r in rows:
                    l10_values = json.loads(r['l10_values']) if r['l10_values'] else []
                    l5_values = json.loads(r['l5_values']) if r['l5_values'] else []
                    
                    new_l10 = [v for v in l10_values if lo <= v <= hi]
                    new_l5 = [v for v in l5_values if lo <= v <= hi]
                    
                    if not new_l10:
                        if args.verbose:
                            logger.debug("Will DELETE %s / %s (avg: %s, vals: %s)", r['team_name'], stat_key, r['l10_avg'], l10_values)
                        if not args.dry_run:
                            conn.execute("DELETE FROM team_form WHERE id = ?", (r['id'],))
                        deleted_rows += 1
                    else:
                        new_avg_10 = _safe_avg(new_l10)
                        new_avg_5 = _safe_avg(new_l5)
                        if args.verbose:
                            logger.debug("Will UPDATE %s / %s (old vals: %s, new vals: %s)", r['team_name'], stat_key, l10_values, new_l10)
                        if not args.dry_run:
                            conn.execute("""
                                UPDATE team_form 
                                SET l10_values = ?, l5_values = ?, l10_avg = ?, l5_avg = ?
                                WHERE id = ?
                            """, (json.dumps(new_l10), json.dumps(new_l5), new_avg_10, new_avg_5, r['id']))
                        updated_rows += 1
                        
        if not args.dry_run:
            conn.commit()
            
    summary = {
        "verdict": "OK",
        "deleted": deleted_rows,
        "updated": updated_rows,
        "dry_run": args.dry_run
    }
    print(f"AGENT_SUMMARY:{json.dumps(summary)}")

if __name__ == "__main__":
    main()
