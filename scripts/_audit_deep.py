#!/usr/bin/env python3
"""Deep audit: scan_results garbage data and pipeline data flow."""
import sys
import os
import json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from bet.db.connection import get_db

DATE = sys.argv[1] if len(sys.argv) > 1 else "2026-05-11"

KNOWN_GARBAGE_PATTERNS = [
    "1xbet", "bet365", "unibet", "betway", "pinnacle", "betclic",
    "info", "- - - -", "division", "round", "matchday", "gameweek",
]


def main():
    with get_db() as conn:
        print("=" * 80)
        print("DEEP SCAN_RESULTS QUALITY AUDIT")
        print("=" * 80)

        # 1. Garbage team names
        all_rows = conn.execute(
            'SELECT home_team, away_team, sport, source_domain, competition FROM scan_results WHERE betting_date=?',
            (DATE,)
        ).fetchall()

        garbage_home = []
        garbage_away = []
        empty_team = 0
        short_team = 0  # team name < 2 chars
        source_breakdown = {}

        for row in all_rows:
            home, away, sport, source, comp = row
            src = source or "unknown"
            source_breakdown[src] = source_breakdown.get(src, 0) + 1

            if not home or len(home.strip()) < 2:
                empty_team += 1
            if not away or len(away.strip()) < 2:
                empty_team += 1

            home_lower = (home or "").lower().strip()
            away_lower = (away or "").lower().strip()

            for pattern in KNOWN_GARBAGE_PATTERNS:
                if pattern in home_lower and len(home_lower) < 20:
                    garbage_home.append((home, away, sport, src, comp))
                    break
            for pattern in KNOWN_GARBAGE_PATTERNS:
                if pattern in away_lower and len(away_lower) < 20:
                    garbage_away.append((home, away, sport, src, comp))
                    break

        total = len(all_rows)
        print(f"\nTotal events: {total}")
        print(f"Empty/short team names: {empty_team}")
        print(f"Garbage home_team: {len(garbage_home)}")
        print(f"Garbage away_team: {len(garbage_away)}")
        print(f"Total garbage: {len(garbage_home) + len(garbage_away)} ({100*(len(garbage_home)+len(garbage_away))/total:.1f}%)")

        print(f"\n--- Garbage home samples ---")
        for g in garbage_home[:15]:
            print(f"  '{g[0]}' vs '{g[1]}' [{g[2]}] src={g[3]} comp={g[4]}")

        print(f"\n--- Garbage away samples ---")
        for g in garbage_away[:15]:
            print(f"  '{g[0]}' vs '{g[1]}' [{g[2]}] src={g[3]} comp={g[4]}")

        # 2. Source breakdown
        print(f"\n--- Source breakdown ---")
        for src, cnt in sorted(source_breakdown.items(), key=lambda x: -x[1]):
            print(f"  {src}: {cnt}")

        # 3. Duplicate detection
        fixture_counts = {}
        for row in all_rows:
            key = f"{row[0]}|{row[1]}|{row[2]}"
            fixture_counts[key] = fixture_counts.get(key, 0) + 1

        dupes = {k: v for k, v in fixture_counts.items() if v > 1}
        print(f"\n--- Duplicate fixtures ---")
        print(f"Unique fixtures: {len(fixture_counts)}")
        print(f"Fixtures with duplicates: {len(dupes)}")
        total_dupes = sum(v - 1 for v in dupes.values())
        print(f"Total duplicate rows: {total_dupes}")
        for k, v in sorted(dupes.items(), key=lambda x: -x[1])[:15]:
            parts = k.split("|")
            print(f"  {v}x: {parts[0]} vs {parts[1]} [{parts[2]}]")

        # 4. Check data flow: shortlist JSON
        shortlist_path = f"betting/data/{DATE}_s2_shortlist.json"
        if os.path.exists(shortlist_path):
            with open(shortlist_path) as f:
                sl_data = json.load(f)
            candidates = sl_data.get("candidates", sl_data.get("shortlist", []))
            print(f"\n--- Shortlist JSON ---")
            print(f"Candidates: {len(candidates)}")
            # Check for garbage in shortlist
            sl_garbage = 0
            for c in candidates:
                home = (c.get("home_team", "") or "").lower()
                away = (c.get("away_team", "") or "").lower()
                for p in KNOWN_GARBAGE_PATTERNS:
                    if p in home or p in away:
                        sl_garbage += 1
                        break
            print(f"Garbage in shortlist: {sl_garbage}")
        else:
            print(f"\nShortlist JSON not found: {shortlist_path}")

        # 5. Check gate results JSON
        gate_path = f"betting/data/{DATE}_s7_gate_results.json"
        if os.path.exists(gate_path):
            with open(gate_path) as f:
                gate_data = json.load(f)
            approved = gate_data.get("gate_results", {}).get("approved", [])
            print(f"\n--- Gate Results JSON ---")
            print(f"Approved: {len(approved)}")
            # Check for garbage in gate results
            gt_garbage = 0
            phantom_teams = set()
            for c in approved:
                home = (c.get("home_team", "") or "").lower()
                away = (c.get("away_team", "") or "").lower()
                for p in KNOWN_GARBAGE_PATTERNS:
                    if p in home or p in away:
                        gt_garbage += 1
                        break
                # Check for phantom (same team in 2 approved picks)
                for team in [c.get("home_team", ""), c.get("away_team", "")]:
                    if team in phantom_teams:
                        pass
                    phantom_teams.add(team)
            print(f"Garbage in gate results: {gt_garbage}")

            # Check for Goals O9.0 in gate results
            weird_lines = 0
            for c in approved:
                bm = c.get("best_market", {}) or {}
                line = bm.get("line", 0)
                name = bm.get("name", "").lower()
                if "goal" in name and isinstance(line, (int, float)) and line > 5:
                    weird_lines += 1
                    print(f"  WEIRD: {c.get('home_team')} vs {c.get('away_team')} — {bm.get('name')} {bm.get('direction')} {line}")
            print(f"Weird goal lines in gate results: {weird_lines}")
        else:
            print(f"\nGate results JSON not found: {gate_path}")

        # 6. Deep stats JSON
        ds_path = f"betting/data/{DATE}_s3_deep_stats.json"
        if os.path.exists(ds_path):
            with open(ds_path) as f:
                ds_data = json.load(f)
            total_c = ds_data.get("total_candidates", 0)
            with_data = ds_data.get("candidates_with_data", 0)
            analyses = ds_data.get("analyses", [])
            no_market = sum(1 for a in analyses if not a.get("best_market"))
            print(f"\n--- Deep Stats JSON ---")
            print(f"Total candidates: {total_c}")
            print(f"With data: {with_data}")
            print(f"No market found: {no_market}")
            print(f"Data yield: {100*with_data/total_c:.1f}%" if total_c > 0 else "N/A")
        else:
            print(f"\nDeep stats JSON not found: {ds_path}")


if __name__ == "__main__":
    main()
