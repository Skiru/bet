"""Aggressive data mining for coupon expansion — find ALL statistical edges today."""
import json
import re
import sqlite3
from collections import defaultdict
from pathlib import Path

conn = sqlite3.connect('betting/data/betting.db')

# Load excluded competition IDs from config
config_path = Path('config/betting_config.json')
config = json.loads(config_path.read_text())
excluded_ids = config.get('excluded_competition_ids', [])
excluded_kw = config.get('excluded_competition_keywords', [])

# Team name pattern for reserves (e.g. "Columbus Crew II", "Juventus U23")
_RESERVE_TEAM_RE = re.compile(
    r'\bII\b|\bU1[2-9]\b|\bU2[0-3]\b|\bReserves?\b|\bB$|\bNext Pro\b', re.I
)

results = conn.execute(f"""
    SELECT f.id, t1.name, t2.name, c.name, s.name,
           tf.stat_key, tf.l5_avg, tf.team_id, t1.id, t2.id,
           f.kickoff
    FROM fixtures f
    JOIN teams t1 ON f.home_team_id = t1.id
    JOIN teams t2 ON f.away_team_id = t2.id
    JOIN competitions c ON f.competition_id = c.id
    JOIN sports s ON f.sport_id = s.id
    JOIN team_form tf ON (tf.team_id = t1.id OR tf.team_id = t2.id)
    WHERE f.kickoff LIKE '2026-05-24%'
      AND tf.stat_key IN ('goals','corners','fouls','yellow_cards','shots_on_target')
      AND tf.l5_avg > 0
      AND f.competition_id NOT IN ({','.join('?' * len(excluded_ids))})
""", excluded_ids).fetchall()

fixtures = defaultdict(lambda: defaultdict(float))
for fid, home, away, league, sport, stat, l5, tid, hid, aid, ko in results:
    # Skip reserve/youth teams by name
    if _RESERVE_TEAM_RE.search(home) or _RESERVE_TEAM_RE.search(away):
        continue
    # Skip if competition name matches excluded keywords
    league_lower = league.lower()
    if any(kw in league_lower for kw in excluded_kw):
        continue
    side = 'h' if tid == hid else 'a'
    fixtures[(fid, home, away, league, sport)][f'{side}_{stat}'] = l5

print(f"Total fixtures with form stats: {len(fixtures)}")
print()

# GOALS OVER 2.5
print("=== GOALS O2.5 (combined L5 goals > 3.0) ===")
g = []
for (fid, h, a, l, s), stats in fixtures.items():
    comb = stats.get('h_goals', 0) + stats.get('a_goals', 0)
    if comb >= 3.0:
        g.append((comb, h, a, l, s, stats.get('h_goals', 0), stats.get('a_goals', 0)))
for c, h, a, l, s, hg, ag in sorted(g, reverse=True)[:15]:
    print(f"  {c:.1f} | {h[:22]:22}({hg:.1f}) vs {a[:22]:22}({ag:.1f}) | {l[:28]}")

print()
print("=== CORNERS O9.5 (combined L5 corners > 10.0) ===")
co = []
for (fid, h, a, l, s), stats in fixtures.items():
    comb = stats.get('h_corners', 0) + stats.get('a_corners', 0)
    if comb >= 10.0:
        co.append((comb, h, a, l, s, stats.get('h_corners', 0), stats.get('a_corners', 0)))
for c, h, a, l, s, hc, ac in sorted(co, reverse=True)[:15]:
    print(f"  {c:.1f} | {h[:22]:22}({hc:.1f}) vs {a[:22]:22}({ac:.1f}) | {l[:28]}")

print()
print("=== FOULS O25.5 (combined L5 fouls > 26.0) ===")
fo = []
for (fid, h, a, l, s), stats in fixtures.items():
    comb = stats.get('h_fouls', 0) + stats.get('a_fouls', 0)
    if comb >= 26.0:
        fo.append((comb, h, a, l, s, stats.get('h_fouls', 0), stats.get('a_fouls', 0)))
for c, h, a, l, s, hf, af in sorted(fo, reverse=True)[:15]:
    print(f"  {c:.1f} | {h[:22]:22}({hf:.1f}) vs {a[:22]:22}({af:.1f}) | {l[:28]}")

print()
print("=== CARDS O4.5 (combined L5 yellow_cards > 5.0) ===")
ca = []
for (fid, h, a, l, s), stats in fixtures.items():
    comb = stats.get('h_yellow_cards', 0) + stats.get('a_yellow_cards', 0)
    if comb >= 5.0:
        ca.append((comb, h, a, l, s, stats.get('h_yellow_cards', 0), stats.get('a_yellow_cards', 0)))
for c, h, a, l, s, hc, ac in sorted(ca, reverse=True)[:12]:
    print(f"  {c:.1f} | {h[:22]:22}({hc:.1f}) vs {a[:22]:22}({ac:.1f}) | {l[:28]}")

print()
print("=== SHOTS ON TARGET HIGH (combined L5 SoT > 10.0) ===")
sot = []
for (fid, h, a, l, s), stats in fixtures.items():
    comb = stats.get('h_shots_on_target', 0) + stats.get('a_shots_on_target', 0)
    if comb >= 10.0:
        sot.append((comb, h, a, l, s, stats.get('h_shots_on_target', 0), stats.get('a_shots_on_target', 0)))
for c, h, a, l, s, hs, as_ in sorted(sot, reverse=True)[:12]:
    print(f"  {c:.1f} | {h[:22]:22}({hs:.1f}) vs {a[:22]:22}({as_:.1f}) | {l[:28]}")

# Count odds markets for top picks
print()
print("=== ODDS COVERAGE for top events ===")
top_events = set()
for items in [g[:8], co[:8], fo[:8], ca[:6]]:
    for item in items:
        top_events.add(item[1])  # home team
        
for home_name in list(top_events)[:20]:
    cnt = conn.execute("""
        SELECT COUNT(*) FROM odds_history oh
        JOIN fixtures f ON oh.fixture_id = f.id
        JOIN teams t ON f.home_team_id = t.id
        WHERE t.name = ? AND f.kickoff LIKE '2026-05-24%'
    """, (home_name,)).fetchone()[0]
    if cnt > 0:
        print(f"  {home_name[:25]:25} — {cnt} odds markets")
