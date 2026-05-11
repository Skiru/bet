#!/usr/bin/env python3
"""Audit DB data quality for today's pipeline run."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from bet.db.connection import get_db

DATE = sys.argv[1] if len(sys.argv) > 1 else "2026-05-11"

def main():
    with get_db() as conn:
        # 1. Count scan_results
        r = conn.execute('SELECT COUNT(*), COUNT(DISTINCT sport) FROM scan_results WHERE betting_date=?', (DATE,)).fetchone()
        print(f"scan_results: {r[0]} events, {r[1]} sports")

        # 2. Sport breakdown
        rows = conn.execute('SELECT sport, COUNT(*) as c FROM scan_results WHERE betting_date=? GROUP BY sport ORDER BY c DESC', (DATE,)).fetchall()
        for row in rows:
            print(f"  {row[0]}: {row[1]}")

        # 3. Phantom fixtures (same team in 2+ matches as home OR away)
        phantoms_home = conn.execute('''
            SELECT home_team, COUNT(*) as c FROM scan_results
            WHERE betting_date=? GROUP BY home_team HAVING c > 1 ORDER BY c DESC LIMIT 15
        ''', (DATE,)).fetchall()
        phantoms_away = conn.execute('''
            SELECT away_team, COUNT(*) as c FROM scan_results
            WHERE betting_date=? GROUP BY away_team HAVING c > 1 ORDER BY c DESC LIMIT 15
        ''', (DATE,)).fetchall()
        print(f"\nPhantom check — home_team duplicates: {len(phantoms_home)}")
        for p in phantoms_home[:10]:
            print(f"  {p[0]}: {p[1]} matches")
        print(f"Phantom check — away_team duplicates: {len(phantoms_away)}")
        for p in phantoms_away[:10]:
            print(f"  {p[0]}: {p[1]} matches")

        # Cross-check: team appearing as BOTH home and away
        cross = conn.execute('''
            SELECT s1.home_team, s1.away_team, s2.home_team as h2, s2.away_team as a2
            FROM scan_results s1
            JOIN scan_results s2 ON s1.home_team = s2.away_team AND s1.rowid != s2.rowid
            WHERE s1.betting_date=? AND s2.betting_date=?
            LIMIT 20
        ''', (DATE, DATE)).fetchall()
        print(f"\nCross phantom (home in one, away in another): {len(cross)}")
        for c in cross[:10]:
            print(f"  {c[0]} vs {c[1]}  <->  {c[2]} vs {c[3]}")

        # 4. Missing data
        nulls = conn.execute('''
            SELECT
                SUM(CASE WHEN competition IS NULL OR competition='' THEN 1 ELSE 0 END),
                SUM(CASE WHEN kickoff IS NULL OR kickoff='' THEN 1 ELSE 0 END),
                SUM(CASE WHEN raw_data IS NULL OR raw_data='{}' OR raw_data='' THEN 1 ELSE 0 END)
            FROM scan_results WHERE betting_date=?
        ''', (DATE,)).fetchone()
        print(f"\nMissing data: competition={nulls[0]}, kickoff={nulls[1]}, raw_data={nulls[2]}")

        # 5. Check key tables
        for table in ['shortlist', 'deep_stats', 'gate_results', 'safety_scores', 
                       'tipster_picks', 'enrichment_cache', 'odds_snapshots']:
            try:
                cnt = conn.execute(f'SELECT COUNT(*) FROM {table} WHERE betting_date=?', (DATE,)).fetchone()
                print(f"{table}: {cnt[0]} entries")
            except Exception:
                try:
                    cnt = conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()
                    print(f"{table}: {cnt[0]} entries (no betting_date column)")
                except Exception:
                    print(f"{table}: TABLE NOT FOUND")

        # 6. Data quality in raw_data — check for Goals O9.0 anomaly
        import json
        goals_weird = conn.execute('''
            SELECT home_team, away_team, sport, raw_data FROM scan_results
            WHERE betting_date=? AND sport='football'
            LIMIT 500
        ''', (DATE,)).fetchall()
        weird_goals = 0
        for row in goals_weird:
            try:
                data = json.loads(row[3])
                dp = data.get('deep_parse', {}) or {}
                if isinstance(dp, str):
                    dp = {}
                raw = data.get('raw', {}) or {}
                if isinstance(raw, str):
                    raw = {}
                # Check for absurd total goals lines
                for key in ['total_goals', 'goals_total', 'total']:
                    val = dp.get(key) or raw.get(key)
                    if val and isinstance(val, (int, float)) and val > 6:
                        weird_goals += 1
                        print(f"  WEIRD GOALS LINE: {row[0]} vs {row[1]} — {key}={val}")
            except (json.JSONDecodeError, TypeError):
                pass
        print(f"\nFootball events with weird goals lines (>6): {weird_goals}")

        # 7. All tables
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
        print(f"\nAll tables ({len(tables)}): {[t[0] for t in tables]}")


if __name__ == "__main__":
    main()
