"""Diagnostic part 2: Deep analysis of raw_data quality in scan_results."""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from bet.db.connection import get_db

TODAY = "2026-05-11"

def main():
    with get_db() as conn:
        # Full scan of all raw_data for today
        c = conn.execute("SELECT sport, raw_data FROM scan_results WHERE betting_date=?", (TODAY,))
        
        stats = {
            'total': 0, 'has_deep_parse': 0, 'deep_parse_non_empty': 0,
            'has_odds_raw': 0, 'has_odds_deep': 0,
            'has_form_raw': 0, 'has_form_deep': 0,
            'has_h2h': 0, 'has_standings': 0,
            'has_corners': 0, 'has_cards': 0,
        }
        by_sport = {}
        deep_keys_all = set()
        raw_keys_all = set()
        
        for row in c:
            sport = row[0]
            stats['total'] += 1
            if sport not in by_sport:
                by_sport[sport] = {'total': 0, 'deep_non_empty': 0, 'has_odds': 0, 'has_form': 0}
            by_sport[sport]['total'] += 1
            
            try:
                data = json.loads(row[1])
            except (json.JSONDecodeError, TypeError):
                continue
            
            raw = data.get('raw', {}) or {}
            if isinstance(raw, str):
                raw = {}
            dp = data.get('deep_parse', {}) or {}
            if isinstance(dp, str):
                dp = {}
            raw_keys_all.update(raw.keys())
            
            if dp:
                stats['has_deep_parse'] += 1
                deep_keys_all.update(dp.keys())
                # Check if non-empty (has any truthy values)
                if any(v for v in dp.values() if v and v != {} and v != []):
                    stats['deep_parse_non_empty'] += 1
                    by_sport[sport]['deep_non_empty'] += 1
            
            # Odds
            if raw.get('odds'):
                stats['has_odds_raw'] += 1
                by_sport[sport]['has_odds'] += 1
            elif dp.get('odds'):
                stats['has_odds_deep'] += 1
                by_sport[sport]['has_odds'] += 1
            
            # Form
            if raw.get('form_home') or raw.get('form_away'):
                stats['has_form_raw'] += 1
                by_sport[sport]['has_form'] += 1
            elif dp.get('form') or dp.get('form_home') or dp.get('form_away'):
                stats['has_form_deep'] += 1
                by_sport[sport]['has_form'] += 1
            
            # H2H
            if dp.get('h2h') or raw.get('h2h'):
                stats['has_h2h'] += 1
            
            # Standings
            if dp.get('standings') or dp.get('league_standings'):
                stats['has_standings'] += 1
            
            # Corners/cards
            if 'corner' in json.dumps(dp).lower():
                stats['has_corners'] += 1
            if 'card' in json.dumps(dp).lower():
                stats['has_cards'] += 1
        
        print("=" * 70)
        print("SCAN RESULTS RAW_DATA QUALITY ANALYSIS")
        print("=" * 70)
        
        t = stats['total']
        if t == 0:
            print("\nNo events found for today. Exiting.")
            return
        print(f"\nTotal events today:           {t}")
        print(f"With deep_parse field:        {stats['has_deep_parse']} ({100*stats['has_deep_parse']/t:.1f}%)")
        print(f"Deep_parse NON-EMPTY:         {stats['deep_parse_non_empty']} ({100*stats['deep_parse_non_empty']/t:.1f}%)")
        print(f"With odds (from raw):         {stats['has_odds_raw']} ({100*stats['has_odds_raw']/t:.1f}%)")
        print(f"With odds (from deep_parse):  {stats['has_odds_deep']} ({100*stats['has_odds_deep']/t:.1f}%)")
        print(f"With form (from raw):         {stats['has_form_raw']} ({100*stats['has_form_raw']/t:.1f}%)")
        print(f"With form (from deep_parse):  {stats['has_form_deep']} ({100*stats['has_form_deep']/t:.1f}%)")
        print(f"With H2H:                     {stats['has_h2h']} ({100*stats['has_h2h']/t:.1f}%)")
        print(f"With standings:               {stats['has_standings']} ({100*stats['has_standings']/t:.1f}%)")
        print(f"With corners:                 {stats['has_corners']} ({100*stats['has_corners']/t:.1f}%)")
        print(f"With cards:                   {stats['has_cards']} ({100*stats['has_cards']/t:.1f}%)")
        
        print(f"\nraw keys seen:       {sorted(raw_keys_all)}")
        print(f"deep_parse keys seen: {sorted(deep_keys_all)}")
        
        print(f"\n{'='*70}")
        print("BY SPORT BREAKDOWN")
        print(f"{'='*70}")
        for sport, s in sorted(by_sport.items(), key=lambda x: -x[1]['total']):
            st = s['total']
            print(f"\n  {sport} ({st} events):")
            print(f"    Deep parse non-empty: {s['deep_non_empty']:>5} ({100*s['deep_non_empty']/st:.1f}%)")
            print(f"    Has odds:             {s['has_odds']:>5} ({100*s['has_odds']/st:.1f}%)")
            print(f"    Has form:             {s['has_form']:>5} ({100*s['has_form']/st:.1f}%)")
        
        # Sample a few events to show what's missing
        print(f"\n{'='*70}")
        print("SAMPLE EVENTS — showing data richness")
        print(f"{'='*70}")
        c = conn.execute("SELECT home_team, away_team, sport, raw_data FROM scan_results WHERE betting_date=? ORDER BY RANDOM() LIMIT 5", (TODAY,))
        for row in c:
            data = json.loads(row[3])
            raw = data.get('raw', {}) or {}
            dp = data.get('deep_parse', {}) or {}
            dp_summary = {k: ('...' if v else None) for k, v in dp.items()} if dp else {}
            print(f"\n  {row[0]} vs {row[1]} ({row[2]})")
            print(f"    raw keys:  {list(raw.keys())}")
            print(f"    deep_parse: {dp_summary}")

if __name__ == "__main__":
    main()
