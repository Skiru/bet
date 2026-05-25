#!/usr/bin/env python3
"""Check esports DB state."""
import sqlite3
conn = sqlite3.connect("betting/data/betting.db")

# Esports fixtures
rows = conn.execute("""
SELECT f.id, f.sport_id, t1.name, t2.name, f.kickoff, f.source
FROM fixtures f
JOIN teams t1 ON f.home_team_id = t1.id
JOIN teams t2 ON f.away_team_id = t2.id
WHERE f.sport_id IN (498, 499, 500)
AND f.kickoff LIKE '2026-05-25%'
ORDER BY f.sport_id
""").fetchall()
print(f"Esports fixtures ({len(rows)}):")
for r in rows:
    sport = {498: "cs2", 499: "dota2", 500: "val"}[r[1]]
    print(f"  id={r[0]} [{sport}] {r[2]} vs {r[3]}")

# Check odds
print()
odds_count = conn.execute("""
SELECT COUNT(*) FROM odds_history oh
JOIN fixtures f ON f.id = oh.fixture_id
WHERE f.sport_id IN (498, 499, 500)
AND f.kickoff LIKE '2026-05-25%'
""").fetchone()[0]
print(f"Odds entries for esports today: {odds_count}")

# Team form
print()
tf = conn.execute("""
SELECT team_name, sport, data_source, wins_l10, losses_l10
FROM team_form WHERE sport IN ('cs2', 'valorant', 'dota2')
""").fetchall()
print(f"Team form entries: {len(tf)}")
for t in tf[:15]:
    print(f"  {t}")

conn.close()
