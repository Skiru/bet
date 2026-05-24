#!/usr/bin/env python3
"""Deep source fusion: tipster picks + DB stats for coupon expansion."""
import json, sys, sqlite3
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from bet.db.connection import get_db

DATE = "2026-05-24"

# Load tipster picks from DB
from bet.db.repositories import TipsterRepo
with get_db() as conn:
    conn.row_factory = sqlite3.Row
    repo = TipsterRepo(conn)
    picks = repo.get_picks_by_date(DATE)
    
    # Clean team names (same logic as fixed xref)
    import re
    def clean(raw):
        if not raw: return ""
        if '\n' not in raw and 'Predictions' not in raw: return raw.strip()
        lines = [l.strip() for l in raw.split('\n') if l.strip()]
        garbage = re.compile(r'^\d+\s*-\s*\d+\s+\w+|^(view\s+)?prediction|^\d+$', re.I)
        leagues = {'premier league','la liga','serie a','serie b','bundesliga','ligue 1',
                   'eredivisie','liga acb','euroleague','mls','wnba','nba','nhl',
                   'allsvenskan','eliteserien','league one','league two','championship',
                   'england','spain','italy','germany','france','brazil série a','brazil série b'}
        clean_lines = [l for l in lines if not garbage.match(l) and l.lower() not in leagues]
        return clean_lines[0] if clean_lines else raw.strip()
    
    # Group by event
    events = defaultdict(list)
    for p in picks:
        h = clean(p.home_team).lower()
        a = clean(p.away_team).lower()
        events[f"{h}|{a}"].append(p)
    
    # Focus: events with >=2 tips OR strong reasoning that are NOT in v4
    v4_events = {'crystal palace|arsenal', 'burnley|wolves', 'burnley|wolverhampton',
                 'odra opole|polonia warszawa', 'man city|aston villa', 'manchester city|aston villa',
                 'nottingham forest|bournemouth', 'huesca|castellon', 'olympiakos|real madrid'}
    
    print("=" * 80)
    print("TIPSTER EVENTS NOT IN COUPON v4 — WITH DB STATS")
    print("=" * 80)
    
    for key, tips in sorted(events.items(), key=lambda x: -len(x[1])):
        # Skip if in v4
        if any(v in key for v in v4_events):
            continue
        if len(tips) < 2 and not any(t.reasoning and len(t.reasoning) > 80 for t in tips):
            continue
            
        h_clean = clean(tips[0].home_team)
        a_clean = clean(tips[0].away_team)
        sport = tips[0].sport or "?"
        
        print(f"\n{'─'*70}")
        print(f"⚽ [{sport}] {h_clean} vs {a_clean} — {len(tips)} tipster picks")
        
        # Show tipster picks
        for t in tips:
            mkt = t.market[:60] if t.market else "?"
            odds = t.odds or "?"
            src = t.source_site or "?"
            reason = (t.reasoning or "")[:150]
            print(f"  [{src}] {mkt} @{odds}")
            if reason:
                print(f"    > {reason}")
        
        # Get DB form data for these teams
        # Try to find team in fixtures
        fixture = conn.execute("""
            SELECT f.id, t1.name as home, t2.name as away, f.home_team_id, f.away_team_id,
                   c.name as comp
            FROM fixtures f
            JOIN teams t1 ON f.home_team_id = t1.id
            JOIN teams t2 ON f.away_team_id = t2.id
            LEFT JOIN competitions c ON f.competition_id = c.id
            WHERE f.kickoff >= ? AND f.kickoff < ?
            AND (LOWER(t1.name) LIKE ? OR LOWER(t2.name) LIKE ?)
            LIMIT 1
        """, (f"{DATE}T00:00:00", f"{DATE}T23:59:59",
              f"%{h_clean.lower().split()[0]}%", f"%{a_clean.lower().split()[0]}%")).fetchone()
        
        if fixture:
            print(f"  📊 DB fixture: {fixture['home']} vs {fixture['away']} ({fixture['comp']})")
            # Get odds count
            odds_count = conn.execute("SELECT COUNT(*) FROM odds_history WHERE fixture_id = ?", (fixture['id'],)).fetchone()[0]
            print(f"  📊 Odds in DB: {odds_count} markets")
            
            # Get form for both teams
            for tid, role in [(fixture['home_team_id'], 'H'), (fixture['away_team_id'], 'A')]:
                stats = conn.execute("""
                    SELECT stat_key, l10_avg, l5_avg, l10_values, trend
                    FROM team_form WHERE team_id = ?
                    AND stat_key IN ('corners','corners_home','corners_away','goals','goals_home','goals_away',
                                     'fouls','fouls_home','fouls_away','shots_on_target','shots_on_target_home',
                                     'shots_on_target_away','yellow_cards','yellow_cards_home','yellow_cards_away')
                """, (tid,)).fetchall()
                if stats:
                    tname = fixture['home'] if role == 'H' else fixture['away']
                    print(f"  [{role}] {tname}:")
                    for s in sorted(stats, key=lambda x: x['stat_key']):
                        l10 = s['l10_avg'] or 0
                        l5 = s['l5_avg'] or 0
                        vals = json.loads(s['l10_values']) if s['l10_values'] else []
                        hit_info = ""
                        if 'goals' == s['stat_key'] and vals:
                            hit_info = f" O2.5={sum(1 for v in vals if v>2.5)/len(vals)*100:.0f}%"
                        elif 'corners' == s['stat_key'] and vals:
                            hit_info = f" O9.5={sum(1 for v in vals if v>9.5)/len(vals)*100:.0f}%"
                        print(f"      {s['stat_key']:25} L10={l10:.1f} L5={l5:.1f} {s['trend'] or ''}{hit_info}")
        else:
            print(f"  ⚠️ No DB fixture match found")

    # ESPORTS CHECK
    print(f"\n{'='*80}")
    print("ESPORT TIPSTER PICKS (CS2, Dota2, Valorant)")
    print("=" * 80)
    esport_picks = [p for p in picks if p.sport and p.sport.lower() in ('cs2','csgo','dota2','dota','valorant','esports','esport')]
    if esport_picks:
        for p in esport_picks:
            print(f"  [{p.source_site}] {clean(p.home_team)} vs {clean(p.away_team)} | {p.market} @{p.odds}")
            if p.reasoning:
                print(f"    > {p.reasoning[:200]}")
    else:
        # Check if any picks mention esport keywords in market/reasoning
        esport_keywords = ['cs2','csgo','valorant','dota','counter-strike','esport','falcons','mouz','mibr','navi','g2','vitality','faze','heroic','spirit','legacy']
        esport_related = [p for p in picks if any(k in (p.market or '').lower() + (p.reasoning or '').lower() + (p.home_team or '').lower() for k in esport_keywords)]
        if esport_related:
            print(f"  Found {len(esport_related)} esport-related picks:")
            for p in esport_related:
                print(f"  [{p.source_site}] {clean(p.home_team)} vs {clean(p.away_team)} | {p.market[:50]} @{p.odds}")
                if p.reasoning:
                    print(f"    > {p.reasoning[:200]}")
        else:
            print("  No esport picks found in tipster data")
            # Check raw JSON for esport
            with open(f'betting/data/{DATE}_tipster_consensus.json') as f:
                raw = json.load(f)
            for site in raw.get('site_results', []):
                for pick in site.get('picks', []):
                    text = json.dumps(pick).lower()
                    if any(k in text for k in esport_keywords):
                        print(f"  [RAW] [{pick.get('source_site')}] {pick.get('home_team','?')[:30]} vs {pick.get('away_team','?')[:30]} | {pick.get('market','?')[:50]}")
                        if pick.get('reasoning'):
                            print(f"    > {pick['reasoning'][:200]}")
