#!/usr/bin/env python3
"""Quick check: fixture coverage per esports sport."""
import sqlite3

conn = sqlite3.connect("betting/data/betting.db")
for sid, name in [(498, "CS2"), (499, "Dota2"), (500, "Valorant")]:
    fixtures = conn.execute("""
        SELECT t1.name, t2.name,
            (SELECT COUNT(*)>0 FROM team_form WHERE team_id=f.home_team_id AND sport_id=?) as h,
            (SELECT COUNT(*)>0 FROM team_form WHERE team_id=f.away_team_id AND sport_id=?) as a
        FROM fixtures f JOIN teams t1 ON f.home_team_id=t1.id JOIN teams t2 ON f.away_team_id=t2.id
        WHERE f.sport_id=? AND DATE(f.kickoff)='2026-05-25'
    """, (sid, sid, sid)).fetchall()
    both = sum(1 for f in fixtures if f[2] and f[3])
    total = len(fixtures)
    pct = both * 100 // max(total, 1)
    print(f"{name}: {both}/{total} fixtures fully covered ({pct}%)")
    for f in fixtures:
        h_ok = "✓" if f[2] else "✗"
        a_ok = "✓" if f[3] else "✗"
        print(f"  {h_ok} {f[0]:20s} vs {a_ok} {f[1]}")
conn.close()
