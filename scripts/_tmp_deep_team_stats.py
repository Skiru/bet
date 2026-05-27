#!/usr/bin/env python3
"""Deep stat inspection for night coupon candidates."""
import sqlite3
import json

db = sqlite3.connect("betting/data/betting.db")
db.row_factory = sqlite3.Row

key_teams = [
    "Lanus", "Mirassol", "Sao Paulo", "Boston River",
    "Gremio", "Montevideo City", "Palestino", "Riestra",
    "Millonarios", "Montreal Alliance", "Niagara River Lions",
    "Pinheiros", "Brasilia", "Franca"
]

for team in key_teams:
    rows = db.execute('''
        SELECT tf.stat_key, tf.l10_avg, tf.l5_avg, tf.l10_values, tf.source, tf.trend
        FROM team_form tf JOIN teams te ON tf.team_id = te.id
        WHERE LOWER(te.name) LIKE ?
        ORDER BY tf.stat_key
    ''', (f'%{team.lower()}%',)).fetchall()
    if rows:
        print(f"\n=== {team} ({len(rows)} stats) ===")
        for r in rows:
            l10_avg = r['l10_avg'] if r['l10_avg'] is not None else "N/A"
            l5_avg = r['l5_avg'] if r['l5_avg'] is not None else "N/A"
            trend = r['trend'] or "?"
            src = r['source'] or "?"
            l10v = r['l10_values'] or ""
            print(f"  {r['stat_key']:<30} l10_avg={str(l10_avg):<8} l5_avg={str(l5_avg):<8} trend={trend:<8} [{src}]")
            # Show raw values for key stats
            if r['stat_key'] in ('goals', 'game_total_goals', 'points', 'game_total_points',
                                 'goals_total', 'fouls', 'corners', 'yellow_cards'):
                if l10v:
                    try:
                        vals = json.loads(l10v) if l10v.startswith('[') else l10v
                        print(f"    RAW L10: {str(vals)[:80]}")
                    except:
                        print(f"    RAW L10: {l10v[:80]}")
    else:
        print(f"\n=== {team}: NO DATA ===")
