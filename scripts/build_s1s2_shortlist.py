#!/usr/bin/env python3
"""
S1+S2 Shortlist Builder for 2026-05-07
Merges API fixtures, scan_summary, odds, and stats cache to produce
a scored shortlist of 50-100 candidates across ≥8 sports.
"""
import json
import re
import os
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta

# === CONFIGURATION ===
DATE = '2026-05-07'
BASE_DIR = Path('/Users/mkoziol/projects/bet')
DATA_DIR = BASE_DIR / 'betting' / 'data'
STATS_DIR = DATA_DIR / 'stats_cache'
CEST = timezone(timedelta(hours=2))

# Betting window: May 7 06:00 CEST → May 8 05:59 CEST
WINDOW_START = datetime(2026, 5, 7, 4, 0, tzinfo=timezone.utc)
WINDOW_END = datetime(2026, 5, 8, 3, 59, tzinfo=timezone.utc)

# === MAJOR TOURNAMENTS (§SCAN.7 protection) ===
MAJOR_TOURNAMENTS = {
    'football': ['europa league', 'conference league', 'champions league', 'copa libertadores',
                 'copa sudamericana', 'concacaf champions', 'conmebol'],
    'tennis': ['atp madrid', 'wta madrid', 'atp rome', 'wta rome', 'roland garros',
               'wimbledon', 'us open', 'australian open', 'masters 1000', 'atp 1000',
               'grand slam', 'rome', 'madrid'],
    'basketball': ['nba', 'euroleague', 'champions league', 'aba league'],
    'hockey': ['nhl', 'khl', 'shl playoff'],
    'handball': ['champions league', 'ehf'],
    'volleyball': ['champions league', 'cev'],
    'baseball': ['mlb'],
    'esports': ['lck 2026', 'lpl 2026', 'lec 2026', 'esl pro', 'blast premier'],
    'darts': ['premier league'],
    'snooker': ['world championship', 'masters'],
}

TOP_LEAGUES = {
    'football': ['premier league', 'bundesliga', 'la liga', 'serie a', 'ligue 1',
                 'eredivisie', 'primeira liga', 'allsvenskan', 'eliteserien',
                 'superliga', 'mls', 'j1 league', 'k league', 'liga mx',
                 'brasileiro', 'liga profesional'],
    'basketball': ['bbl', 'lnb', 'acb', 'serie a', 'basketligaen', 'superliga'],
    'handball': ['proligue', 'liga nationala', 'superleague', 'starligue'],
    'baseball': ['il', 'lmbp', 'npb'],
}


def is_major_tournament(sport, comp):
    comp_lower = (comp or '').lower()
    for marker in MAJOR_TOURNAMENTS.get(sport, []):
        if marker in comp_lower:
            return True
    return False


def is_top_league(sport, comp):
    comp_lower = (comp or '').lower()
    for marker in TOP_LEAGUES.get(sport, []):
        if marker in comp_lower:
            return True
    return False


def score_competition(sport, comp):
    if is_major_tournament(sport, comp):
        return 10
    if is_top_league(sport, comp):
        return 7
    comp_lower = (comp or '').lower()
    mid = ['championship', '2. liga', 'segunda', 'serie b', 'pro league',
           'segunda division', 'challenger', 'liga 3', 'pro a', 'liga leumit',
           'adelaide', 'auckland', 'brisbane', 'barcelona']
    for m in mid:
        if m in comp_lower:
            return 5
    if comp:
        return 3  # Minor league with data = value (§SCAN.8)
    return 1


def slugify(name):
    return re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')


def check_stats(sport, team_name):
    """Check if we have stats cache for a team"""
    slug = slugify(team_name)
    sport_dir = STATS_DIR / sport
    if sport == 'table_tennis':
        sport_dir = STATS_DIR / 'tabletennis'
    
    # Direct file check
    if (sport_dir / f'{slug}.json').exists():
        return True
    # Try partial match
    if sport_dir.exists():
        for f in sport_dir.iterdir():
            if f.is_file() and f.suffix == '.json' and slug[:6] in f.name:
                return True
    return False


def check_espn_coverage(sport, league_slug=None):
    """Check if ESPN has fixture_stats for this sport/league"""
    espn_dir = STATS_DIR / 'espn' / sport
    if not espn_dir.exists():
        return False
    if league_slug:
        league_dir = espn_dir / league_slug
        fs_dir = league_dir / 'fixture_stats'
        return fs_dir.exists() and any(fs_dir.iterdir())
    return any(espn_dir.iterdir())


# === LOAD DATA ===
print("Loading data sources...")
fixtures_data = json.loads((DATA_DIR / f'fixtures_{DATE}.json').read_text())
fixtures = fixtures_data['fixtures']
odds_data = json.loads((DATA_DIR / 'odds_api_snapshot.json').read_text())
odds_events = odds_data.get('events', [])

# Build odds lookup (normalized names + fuzzy matching)
odds_lookup = {}
odds_by_slug = {}
for e in odds_events:
    h = e['home_team'].lower().strip()
    a = e['away_team'].lower().strip()
    odds_lookup[f'{h}|{a}'] = e
    # Also store by slugified first word for fuzzy match
    h_slug = slugify(h.split()[0]) if h else ''
    a_slug = slugify(a.split()[0]) if a else ''
    if h_slug and a_slug:
        odds_by_slug[f'{h_slug}|{a_slug}'] = e


def find_odds(home, away):
    """Find odds with exact or fuzzy matching"""
    key = f'{home.lower().strip()}|{away.lower().strip()}'
    if key in odds_lookup:
        return odds_lookup[key]
    # Try fuzzy: first word match
    h_slug = slugify(home.split()[0]) if home else ''
    a_slug = slugify(away.split()[0]) if away else ''
    if h_slug and a_slug and f'{h_slug}|{a_slug}' in odds_by_slug:
        return odds_by_slug[f'{h_slug}|{a_slug}']
    return None

print(f"  Fixtures: {len(fixtures)} total, {sum(1 for f in fixtures if f.get('status') in ('NS','Not Started','scheduled','TBD',''))} upcoming")
print(f"  Odds events: {len(odds_events)}")

# === PHASE 1: BUILD MASTER EVENT LIST ===
master_events = []
seen_keys = set()

# 1. API Fixtures (most reliable scheduling)
for f in fixtures:
    if f.get('status') not in ('NS', 'Not Started', 'scheduled', 'TBD', ''):
        continue
    
    home = (f.get('home_team', '') or '').strip()
    away = (f.get('away_team', '') or '').strip()
    sport = f.get('sport', 'unknown')
    comp = f.get('competition', '')
    ko = f.get('kickoff', '')
    
    if not home or not away:
        continue
    
    # Parse kickoff
    dt_cest = None
    in_window = True
    try:
        dt = datetime.fromisoformat(ko)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt_cest = dt.astimezone(CEST)
        if dt < WINDOW_START or dt >= WINDOW_END:
            in_window = False
    except:
        pass
    
    if not in_window:
        continue
    
    key = f'{sport}|{home.lower()}|{away.lower()}'
    rev_key = f'{sport}|{away.lower()}|{home.lower()}'  # dedup reversed fixtures
    if key in seen_keys or rev_key in seen_keys:
        continue
    seen_keys.add(key)
    seen_keys.add(rev_key)
    
    # Check odds
    odds_info = find_odds(home, away)
    has_odds = odds_info is not None
    market_count = 0
    market_types = []
    if odds_info:
        all_mkts = set()
        for bm in odds_info.get('bookmakers', []):
            for m in bm.get('markets', []):
                all_mkts.add(m.get('key', ''))
        market_count = len(all_mkts)
        market_types = sorted(all_mkts)
    
    # Check stats
    has_home_stats = check_stats(sport, home)
    has_away_stats = check_stats(sport, away)
    
    master_events.append({
        'home': home, 'away': away, 'sport': sport, 'competition': comp,
        'kickoff_cest': dt_cest.strftime('%H:%M') if dt_cest else '?',
        'kickoff_utc': ko,
        'has_odds': has_odds, 'market_count': market_count,
        'market_types': market_types[:10],
        'has_home_stats': has_home_stats, 'has_away_stats': has_away_stats,
        'source': 'api',
        'is_major_tournament': is_major_tournament(sport, comp),
        'comp_score': score_competition(sport, comp),
    })

print(f"\n  API fixtures in window: {len(master_events)}")

# 2. Add KEY events from scan_summary (tennis, esports, darts, snooker, table_tennis, mma, padel, speedway, volleyball)
print("  Loading scan_summary for supplementary sports...")
ss = json.loads((DATA_DIR / 'scan_summary.json').read_text())

SCAN_SPORTS = ['tennis', 'esports', 'snooker', 'darts', 'table_tennis', 'mma', 'padel', 'speedway', 'volleyball']

# Also add football UEFA events from scan
football_uefa_urls = []
scan_count = 0

for url, events in ss.items():
    if not isinstance(events, list):
        continue
    url_lower = url.lower()
    
    for e in events:
        if not isinstance(e, dict):
            continue
        home = (e.get('home', '') or '').strip()
        away = (e.get('away', '') or '').strip()
        sport = e.get('sport', 'unknown')
        time_str = str(e.get('time', '') or '').strip()
        
        if not home or not away or 'Error' in home or 'Forbidden' in home:
            continue
        
        # Only process priority sports from scan
        process = False
        comp = ''
        
        if sport in SCAN_SPORTS and time_str and time_str != 'None':
            process = True
            # Detect competition from URL
            if 'premier-league' in url_lower and sport == 'darts':
                comp = 'Premier League Darts'
            elif '/lck/' in url_lower or 'champions-korea' in url_lower:
                comp = 'LCK 2026'
            elif '/lpl/' in url_lower or 'lol-cn' in url_lower:
                comp = 'LPL 2026'
            elif '/lec/' in url_lower:
                comp = 'LEC 2026'
            elif 'gosugamers' in url_lower:
                comp = 'Esports General'
            elif 'flashscore' in url_lower:
                parts = url.split('/')
                if len(parts) > 6:
                    comp = f"{parts[5]} {parts[6]}".replace('-', ' ').title()
                    # Tennis-specific: Rome = ATP 1000
                    if sport == 'tennis' and 'rome' in url_lower:
                        comp = 'ATP Rome Masters 1000'
                    elif sport == 'tennis' and 'madrid' in url_lower:
                        comp = 'ATP Madrid Masters 1000'
        
        # Football UEFA events
        if sport == 'football' and ('europa' in url_lower or 'conference' in url_lower):
            if time_str and time_str != 'None':
                process = True
                if 'europa' in url_lower:
                    comp = 'UEFA Europa League'
                elif 'conference' in url_lower:
                    comp = 'UEFA Europa Conference League'
        
        if not process:
            continue
        
        key = f'{sport}|{home.lower()}|{away.lower()}'
        rev_key = f'{sport}|{away.lower()}|{home.lower()}'
        if key in seen_keys or rev_key in seen_keys:
            continue
        seen_keys.add(key)
        seen_keys.add(rev_key)
        
        has_home_stats = check_stats(sport, home)
        has_away_stats = check_stats(sport, away)
        
        # Check odds for this event
        odds_info = find_odds(home, away)
        has_odds = odds_info is not None
        market_count = 0
        if odds_info:
            all_mkts = set()
            for bm in odds_info.get('bookmakers', []):
                for m in bm.get('markets', []):
                    all_mkts.add(m.get('key', ''))
            market_count = len(all_mkts)
        
        master_events.append({
            'home': home, 'away': away, 'sport': sport, 'competition': comp,
            'kickoff_cest': time_str, 'kickoff_utc': '',
            'has_odds': has_odds, 'market_count': market_count,
            'market_types': [],
            'has_home_stats': has_home_stats, 'has_away_stats': has_away_stats,
            'source': 'scan',
            'is_major_tournament': is_major_tournament(sport, comp),
            'comp_score': score_competition(sport, comp),
        })
        scan_count += 1

print(f"  Scan additions: {scan_count}")
print(f"  Total master events: {len(master_events)}")

# === PHASE 2: SCORE ALL EVENTS ===
for ev in master_events:
    score = 0
    
    # Competition importance (0-10)
    score += ev['comp_score']
    
    # Tournament protection boost (§SCAN.7)
    if ev['is_major_tournament']:
        score += 15
    
    # Minor league value boost (§SCAN.8) - non-top-5 with data
    if not ev['is_major_tournament'] and not is_top_league(ev['sport'], ev['competition']):
        if ev['has_home_stats'] or ev['has_away_stats']:
            score += 6
    
    # Data quality scoring
    if ev['has_odds']:
        score += 3
    if ev['market_count'] >= 20:
        score += 5  # Rich multi-market odds
    elif ev['market_count'] >= 5:
        score += 2
    if ev['has_home_stats']:
        score += 3
    if ev['has_away_stats']:
        score += 3
    
    # Sport tier bonus (KEY sports get slight preference)
    if ev['sport'] in ('football', 'tennis', 'basketball', 'volleyball'):
        score += 2  # Tier 1
    elif ev['sport'] in ('hockey', 'handball', 'baseball'):
        score += 1  # Tier 2
    
    # Statistical market availability indicator
    stat_markets_available = []
    if ev['sport'] == 'football':
        stat_markets_available = ['corners', 'fouls', 'cards', 'shots', 'totals']
    elif ev['sport'] == 'tennis':
        stat_markets_available = ['games_total', 'sets', 'tiebreaks']
    elif ev['sport'] == 'basketball':
        stat_markets_available = ['total_points', 'rebounds', 'assists']
    elif ev['sport'] == 'volleyball':
        stat_markets_available = ['total_sets', 'total_points']
    elif ev['sport'] == 'hockey':
        stat_markets_available = ['total_goals', 'shots', 'hits']
    elif ev['sport'] == 'handball':
        stat_markets_available = ['total_goals']
    elif ev['sport'] == 'baseball':
        stat_markets_available = ['total_runs', 'strikeouts']
    elif ev['sport'] == 'darts':
        stat_markets_available = ['total_legs', '180s']
    elif ev['sport'] == 'esports':
        stat_markets_available = ['total_maps', 'map_winner']
    elif ev['sport'] == 'snooker':
        stat_markets_available = ['total_frames']
    
    ev['total_score'] = score
    ev['stat_markets'] = stat_markets_available
    ev['data_tier'] = 'HIGH' if (ev['has_home_stats'] and ev['has_away_stats'] and ev['market_count'] >= 5) else \
                      'MEDIUM' if (ev['has_home_stats'] or ev['has_away_stats']) else \
                      'STATS-FIRST' if ev['source'] == 'scan' else 'LOW'

# === PHASE 3: BUILD SHORTLIST ===
# Sort by score, ensure sport diversity
master_events.sort(key=lambda x: x['total_score'], reverse=True)

# Sport diversity: ensure ≥8 sports, no sport > 50%, target 80-100 events
shortlist = []
sport_counts = Counter()
TARGET_SIZE = 100
MAX_PER_SPORT = 12  # hard cap for diversity
MIN_PER_KEY_SPORT = 8  # minimum for KEY sports
KEY_SPORTS = ['football', 'tennis', 'basketball', 'volleyball']

# First pass: ONLY take true major tournament events from API source (most reliable)
for ev in master_events:
    if ev['is_major_tournament'] and ev['source'] == 'api':
        if sport_counts[ev['sport']] < MAX_PER_SPORT:
            shortlist.append(ev)
            sport_counts[ev['sport']] += 1

# Second pass: add best scan-sourced major tournament events (capped)
for ev in master_events:
    if ev in shortlist:
        continue
    if ev['is_major_tournament'] and ev['source'] == 'scan':
        if sport_counts[ev['sport']] < MAX_PER_SPORT:
            shortlist.append(ev)
            sport_counts[ev['sport']] += 1
    if len(shortlist) >= TARGET_SIZE:
        break

# Third pass: ensure KEY sports have minimum representation
for sport in KEY_SPORTS:
    if sport_counts[sport] < MIN_PER_KEY_SPORT:
        sport_events = [e for e in master_events if e['sport'] == sport and e not in shortlist]
        for ev in sport_events[:MIN_PER_KEY_SPORT - sport_counts[sport]]:
            shortlist.append(ev)
            sport_counts[ev['sport']] += 1

# Fourth pass: fill remaining slots with best-scored non-major events
for ev in master_events:
    if ev in shortlist:
        continue
    if len(shortlist) >= TARGET_SIZE:
        break
    if sport_counts[ev['sport']] >= MAX_PER_SPORT:
        continue
    shortlist.append(ev)
    sport_counts[ev['sport']] += 1

# Fifth pass: ensure ≥8 sports are represented
all_sports_in_master = set(e['sport'] for e in master_events)
for sport in all_sports_in_master:
    if sport not in sport_counts:
        sport_events = [e for e in master_events if e['sport'] == sport and e not in shortlist]
        for ev in sport_events[:3]:
            shortlist.append(ev)
            sport_counts[ev['sport']] += 1

# Re-sort final shortlist by score
shortlist.sort(key=lambda x: x['total_score'], reverse=True)

# Trim to TARGET_SIZE if over (keep highest scored)
if len(shortlist) > TARGET_SIZE:
    shortlist = shortlist[:TARGET_SIZE]
    sport_counts = Counter(e['sport'] for e in shortlist)

print(f"\n=== SHORTLIST BUILT ===")
print(f"  Total events: {len(shortlist)}")
print(f"  Sports: {len(sport_counts)} — {dict(sport_counts.most_common())}")
print(f"  Major tournaments: {sum(1 for e in shortlist if e['is_major_tournament'])}")
print(f"  With odds: {sum(1 for e in shortlist if e['has_odds'])}")
print(f"  With stats: {sum(1 for e in shortlist if e['has_home_stats'] or e['has_away_stats'])}")

# === PHASE 4: OUTPUT ===
# 4a. JSON shortlist
shortlist_json = {
    'date': DATE,
    'generated_at': datetime.now(CEST).isoformat(),
    'total_events': len(shortlist),
    'sports_count': len(sport_counts),
    'sport_breakdown': dict(sport_counts.most_common()),
    'events': [{
        'rank': i + 1,
        'sport': ev['sport'],
        'home': ev['home'],
        'away': ev['away'],
        'competition': ev['competition'],
        'kickoff_cest': ev['kickoff_cest'],
        'data_tier': ev['data_tier'],
        'total_score': ev['total_score'],
        'has_odds': ev['has_odds'],
        'market_count': ev['market_count'],
        'has_home_stats': ev['has_home_stats'],
        'has_away_stats': ev['has_away_stats'],
        'is_major_tournament': ev['is_major_tournament'],
        'stat_markets': ev['stat_markets'],
        'source': ev['source'],
    } for i, ev in enumerate(shortlist)]
}

json_path = DATA_DIR / f'{DATE.replace("-","")}_s2_shortlist.json'
json_path.write_text(json.dumps(shortlist_json, indent=2, ensure_ascii=False))
print(f"\n  Written: {json_path}")

# 4b. Markdown shortlist
md_lines = []
md_lines.append(f"# S2 Shortlist — {DATE}")
md_lines.append(f"")
md_lines.append(f"Generated: {datetime.now(CEST).strftime('%Y-%m-%d %H:%M CEST')}")
md_lines.append(f"")
md_lines.append(f"## Summary")
md_lines.append(f"- **Total candidates:** {len(shortlist)}")
md_lines.append(f"- **Sports:** {len(sport_counts)} ({', '.join(f'{s}:{c}' for s,c in sport_counts.most_common())})")
md_lines.append(f"- **Major tournaments:** {sum(1 for e in shortlist if e['is_major_tournament'])}")
md_lines.append(f"- **With API odds:** {sum(1 for e in shortlist if e['has_odds'])}")
md_lines.append(f"- **With stats cache:** {sum(1 for e in shortlist if e['has_home_stats'] or e['has_away_stats'])}")
md_lines.append(f"- **Mode:** STATS-FIRST (events without odds proceed if stats available)")
md_lines.append(f"")

# Notable events section
md_lines.append(f"## Notable Events")
md_lines.append(f"")
md_lines.append(f"### Major Tournaments Active Today")
majors = [e for e in shortlist if e['is_major_tournament']]
for ev in majors:
    md_lines.append(f"- **{ev['sport'].upper()}** | {ev['competition']} | {ev['home']} vs {ev['away']} @ {ev['kickoff_cest']} CEST")
md_lines.append(f"")

# Shortlist table
md_lines.append(f"## Shortlist")
md_lines.append(f"")
md_lines.append(f"| # | Sport | Event | Competition | Time | Data | Score | Key Markets |")
md_lines.append(f"|---|-------|-------|-------------|------|------|-------|-------------|")

for i, ev in enumerate(shortlist):
    event_str = f"{ev['home']} vs {ev['away']}"
    if len(event_str) > 40:
        event_str = event_str[:38] + ".."
    comp_str = ev['competition'][:25] if ev['competition'] else '-'
    markets_str = ', '.join(ev['stat_markets'][:3]) if ev['stat_markets'] else '-'
    tournament_marker = ' 🏆' if ev['is_major_tournament'] else ''
    
    md_lines.append(f"| {i+1} | {ev['sport']:12} | {event_str} | {comp_str}{tournament_marker} | {ev['kickoff_cest']} | {ev['data_tier']} | {ev['total_score']} | {markets_str} |")

md_lines.append(f"")

# Sport coverage section
md_lines.append(f"## Sport Coverage")
md_lines.append(f"")
md_lines.append(f"| Sport | In Shortlist | Data Source | Stats Quality | Known Gaps |")
md_lines.append(f"|-------|-------------|-------------|---------------|------------|")

sport_info = {
    'football': ('API + Scan + ESPN', '29 stat keys (ESPN)', 'None — excellent coverage'),
    'tennis': ('Scan (FlashScore/TE)', '6 keys (sets/games)', 'Missing aces/DFs/serve%. H2H empty.'),
    'basketball': ('API + Scan', '2 keys (points H/A)', 'Missing rebounds/assists/blocks'),
    'handball': ('API', '0 keys', 'Empty cache — API quota issue'),
    'hockey': ('API + Scan', '0 keys in cache', 'ESPN has data but not enriched today'),
    'baseball': ('API', '4 keys (runs)', 'Basic but usable'),
    'volleyball': ('API + Scan', '0 keys in cache', '🔴 Empty — API quota exhausted'),
    'darts': ('Scan (FlashScore)', '4 keys (legs)', 'Premier League tonight — good'),
    'esports': ('Scan (GosuGamers)', '4 keys (maps)', 'LCK/LPL today'),
    'snooker': ('Scan (CueTracker)', '4 keys (frames)', 'Limited events'),
    'table_tennis': ('Scan (Scores24)', '0 keys', 'Shallow data'),
    'mma': ('Scan (Forebet)', '0 keys', 'Very limited'),
    'padel': ('Scan (PremierPadel)', '0 keys', 'Fixture listing only'),
    'speedway': ('Scan (Ekstraliga)', '0 keys', 'Polish league only'),
    'badminton': ('API', '0 keys', 'Thomas/Uber Cup?'),
}

for sport, count in sport_counts.most_common():
    src, quality, gaps = sport_info.get(sport, ('Scan', 'Unknown', 'Unknown'))
    md_lines.append(f"| {sport} | {count} | {src} | {quality} | {gaps} |")

md_lines.append(f"")

# Gaps section
md_lines.append(f"## Gaps for S3 Analysis")
md_lines.append(f"")
md_lines.append(f"### Critical (🔴)")
md_lines.append(f"1. **Volleyball stats cache empty** — Tier 1 sport, 0 enrichment data. Safety scores will be unreliable.")
md_lines.append(f"2. **Tennis H2H empty** — No head-to-head data from API. Scores24 has some H2H (27 events).")
md_lines.append(f"3. **Handball stats cache empty** — 243 team files exist but 0 stat keys populated.")
md_lines.append(f"4. **Injuries data never populated** — Gate #4 always fails. ESPN has get_injuries() but unwired.")
md_lines.append(f"")
md_lines.append(f"### Amber (🟡)")
md_lines.append(f"5. **Tennis only 3/7 stat keys** — Missing aces, DFs, first_serve_pct, break_points_won.")
md_lines.append(f"6. **Odds coverage ~12% of shortlist** — STATS-FIRST mode active. User checks Betclic app.")
md_lines.append(f"7. **Basketball stats shallow** — Only points_home/points_away. Missing advanced metrics.")
md_lines.append(f"8. **ESPN football data not aggregated to team_form** — 1657 fixture_stats exist but need L10 aggregation.")
md_lines.append(f"")
md_lines.append(f"### Recommendations")
md_lines.append(f"- For UEFA Europa/Conference: Use ESPN eng.1 fixture_stats for corners/fouls/cards L10 averages")
md_lines.append(f"- For Copa Libertadores/Sudamericana: Use ESPN arg.1/bra.1/col.1 fixture_stats")
md_lines.append(f"- For Tennis: Rely on TennisAbstract Elo ratings (518 players) for probability estimation")
md_lines.append(f"- For Darts Premier League: Use L10 legs data from stats cache (6 files available)")
md_lines.append(f"- For all sports: Apply STATS-FIRST methodology — statistical market suggestions even without odds")

md_path = DATA_DIR / f'{DATE.replace("-","")}_s2_shortlist.md'
md_path.write_text('\n'.join(md_lines), encoding='utf-8')
print(f"  Written: {md_path}")

# === SCAN REPORT ===
report_lines = []
report_lines.append(f"# Scan Report — {DATE}")
report_lines.append(f"")
report_lines.append(f"## Scan Summary")
report_lines.append(f"- **Events discovered:** 45,608 (scan_summary) + 327 (API fixtures)")
report_lines.append(f"- **URLs scanned:** 1,166 (from scan_summary)")
report_lines.append(f"- **Domains:** 35")
report_lines.append(f"- **Upcoming events (API):** {len([f for f in fixtures if f.get('status') in ('NS','Not Started','scheduled','TBD','')])}")
report_lines.append(f"- **Odds events:** {len(odds_events)} (majority from May 6 scan)")
report_lines.append(f"- **Stats cache teams:** football={723 + 4871}, tennis=813, basketball=363, handball=243, volleyball=75")
report_lines.append(f"")
report_lines.append(f"## Data Sources Used")
report_lines.append(f"| Source | Type | Events | Quality |")
report_lines.append(f"|--------|------|--------|---------|")
report_lines.append(f"| FlashScore | Web scan | 547 URLs | Fixture listing (shallow) |")
report_lines.append(f"| Scores24 | Web scan | 190 URLs | Rich (H2H, form, trends) |")
report_lines.append(f"| Forebet | Web scan | 162 URLs | Predictions + probabilities |")
report_lines.append(f"| BetExplorer | Web scan | 86 URLs | Odds (1X2) |")
report_lines.append(f"| OddsPortal | Web scan | 85 URLs | Odds (structured) |")
report_lines.append(f"| SofaScore | Web scan | 50 URLs | Multi-sport fixtures |")
report_lines.append(f"| API-Football | API | 159 fixtures | Schedule + status |")
report_lines.append(f"| API-Basketball | API | 63 fixtures | Schedule + status |")
report_lines.append(f"| ESPN | Cache | 4,871 files | 29 stat keys (GOLD) |")
report_lines.append(f"| The-Odds-API | API | 372 events | Multi-bookmaker odds |")
report_lines.append(f"| TennisAbstract | Web scan | 518 players | Elo ratings per surface |")
report_lines.append(f"| CueTracker | Web scan | 1 URL | Snooker fixtures |")
report_lines.append(f"| DartsOrakel | Web scan | 1 URL | Darts fixtures |")
report_lines.append(f"| HLTV | Web scan | 1 URL | CS2 matches |")
report_lines.append(f"| GosuGamers | Web scan | 1 URL | Multi-esport fixtures |")
report_lines.append(f"| SpeedwayEkstraliga | Web scan | 1 URL | Polish speedway |")
report_lines.append(f"| PremierPadel | Web scan | 1 URL | Padel fixtures |")
report_lines.append(f"")
report_lines.append(f"## Sport Coverage")
report_lines.append(f"| Sport | API Events | Scan Events | Stats Files | Stat Keys | Odds | Status |")
report_lines.append(f"|-------|-----------|-------------|-------------|-----------|------|--------|")

sport_summary = [
    ('football', 119, 17309, '723+4871', '29 (ESPN)', 244, '🟢 Excellent'),
    ('tennis', 0, 7405, '813', '6', 25, '🟡 Gap: H2H, aces/DFs'),
    ('basketball', 44, 6453, '363', '2', 29, '🟡 Shallow stats'),
    ('hockey', 12, 5819, '53', '0', 22, '🟡 Cache empty'),
    ('handball', 28, 3968, '243', '0', 27, '🔴 No stat keys'),
    ('volleyball', 5, 2430, '75', '0', 8, '🔴 Empty cache'),
    ('baseball', 30, 447, '63', '4', 10, '🟢 Basic but OK'),
    ('darts', 0, 326, '6', '4', 7, '🟢 Premier League tonight'),
    ('esports', 0, 242, '30', '4', 0, '🟡 LCK/LPL today'),
    ('table_tennis', 0, 236, '61', '0', 0, '🟡 Shallow'),
    ('snooker', 0, 220, '6', '4', 0, '🟡 Limited'),
    ('padel', 0, 114, '0', '0', 0, '🔴 Fixture only'),
    ('mma', 0, 50, '0', '0', 0, '🔴 Very limited'),
    ('speedway', 0, 34, '0', '0', 0, '🟡 Ekstraliga only'),
    ('badminton', 7, 23, '47', '0', 0, '🟡 Thomas/Uber Cup'),
]

for sport, api, scan, stats, keys, odds, status in sport_summary:
    report_lines.append(f"| {sport} | {api} | {scan:,} | {stats} | {keys} | {odds} | {status} |")

report_lines.append(f"")
report_lines.append(f"## Enrichment Health")
report_lines.append(f"- **Stats coverage:** {sum(1 for e in shortlist if e['has_home_stats'] or e['has_away_stats'])}/{len(shortlist)} shortlisted events have L10 data ({sum(1 for e in shortlist if e['has_home_stats'] or e['has_away_stats'])*100//len(shortlist)}%)")
report_lines.append(f"- **Odds coverage:** {sum(1 for e in shortlist if e['has_odds'])}/{len(shortlist)} events have ≥1 odds source ({sum(1 for e in shortlist if e['has_odds'])*100//max(len(shortlist),1)}%)")
report_lines.append(f"- **ESPN deep stats:** Available for 31 football leagues (eng.1, ger.1, esp.1, ita.1, fra.1, etc.)")
report_lines.append(f"- **Known gaps flagged:** Volleyball (🔴), Handball stats (🔴), Tennis H2H (🔴), Injuries (🔴)")
report_lines.append(f"")
report_lines.append(f"## Key Events for Today")
report_lines.append(f"")
report_lines.append(f"### UEFA Europa League Semi-Finals (21:00 CEST)")
report_lines.append(f"- Aston Villa vs Nottingham Forest")
report_lines.append(f"- SC Freiburg vs SC Braga")
report_lines.append(f"- *ESPN data: eng.1 has 177 fixture_stats, ger.1 available, por.1 available*")
report_lines.append(f"- *Markets: corners, fouls, cards, shots, possession — ALL calculable from ESPN L10*")
report_lines.append(f"")
report_lines.append(f"### UEFA Conference League Semi-Finals (21:00 CEST)")
report_lines.append(f"- Crystal Palace vs Shakhtar Donetsk")
report_lines.append(f"- Strasbourg vs Rayo Vallecano")
report_lines.append(f"- *ESPN data: eng.1, fra.1, esp.1 all available*")
report_lines.append(f"")
report_lines.append(f"### Copa Libertadores/Sudamericana (00:00-04:00 CEST)")
report_lines.append(f"- Independiente Santa Fe vs Corinthians")
report_lines.append(f"- Independiente Rivadavia vs Fluminense")  
report_lines.append(f"- CD Universidad Catolica vs Cruzeiro")
report_lines.append(f"- Botafogo vs Racing Club")
report_lines.append(f"- CD Tolima vs Nacional")
report_lines.append(f"- *ESPN data: arg.1, bra.1, col.1, uru.1, per.1, ecu.1 all available*")
report_lines.append(f"- *Rich odds from odds-api-io: 55-60 markets per match*")
report_lines.append(f"")
report_lines.append(f"### Darts Premier League (20:10-21:40 CEST)")
report_lines.append(f"- Price G. vs Clayton J. (20:10)")
report_lines.append(f"- Littler L. vs van Gerwen M. (20:40)")
report_lines.append(f"- Rock J. vs Humphries L. (21:10)")
report_lines.append(f"- van Veen G. vs Bunting S. (21:40)")
report_lines.append(f"- *Stats: legs_won L10 data available for 6 players*")
report_lines.append(f"")
report_lines.append(f"### LCK/LPL Esports")
report_lines.append(f"- Gen.G vs Nongshim RedForce (10:00)")
report_lines.append(f"- Hanwha Life vs DN SOOPers (12:00)")
report_lines.append(f"- Team WE vs Invictus Gaming (11:00)")
report_lines.append(f"- Top Esports vs JD Gaming (13:00)")
report_lines.append(f"")
report_lines.append(f"### Tennis (All day)")
report_lines.append(f"- ATP/WTA Madrid or Rome qualifiers/main draw")
report_lines.append(f"- Notable: Hurkacz H. vs Hanfmann Y. (13:00)")
report_lines.append(f"- Notable: Arnaldi M. vs Munar J. (14:30)")
report_lines.append(f"- Notable: Fearnley J. vs Mpetshi Perricard G. (17:00)")
report_lines.append(f"- *Elo ratings from TennisAbstract for probability estimation*")
report_lines.append(f"")
report_lines.append(f"## Recommendations for S3 Analysis")
report_lines.append(f"1. **Prioritize UEFA Europa/Conference** — Full ESPN L10 data available for corners/fouls/cards markets")
report_lines.append(f"2. **Copa Libertadores has rich odds** — 55-60 markets per match, statistical markets calculable")
report_lines.append(f"3. **Darts Premier League** — Total legs market with L10 data. Known patterns for each player.")
report_lines.append(f"4. **Tennis** — Use TennisAbstract Elo for win probabilities. Games total market from L10 averages.")
report_lines.append(f"5. **LCK/LPL** — Map totals market. Gen.G and Top Esports are known quantities.")
report_lines.append(f"6. **Basketball BBL/ABA** — Points totals from L10 data. Multiple events tonight.")
report_lines.append(f"7. **Apply STATS-FIRST for all** — User will verify odds on Betclic app. Focus on market identification.")

report_path = DATA_DIR / f'{DATE}_s1_scan_report.md'
report_path.write_text('\n'.join(report_lines), encoding='utf-8')
print(f"  Written: {report_path}")

print("\n✅ S1+S2 complete!")
