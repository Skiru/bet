#!/usr/bin/env python3
"""Calculate precise hit rates for Copa night picks."""
import sqlite3, json

db = sqlite3.connect("betting/data/betting.db")

def get_all_stats(team_pattern, stat_keys):
    results = {}
    for sk in stat_keys:
        rows = db.execute(
            "SELECT tf.l10_values, tf.l10_avg, tf.l5_avg, tf.source "
            "FROM team_form tf JOIN teams te ON tf.team_id = te.id "
            "WHERE LOWER(te.name) LIKE ? AND tf.stat_key = ? AND tf.l10_avg IS NOT NULL",
            (f"%{team_pattern}%", sk)
        ).fetchall()
        for r in rows:
            vals = json.loads(r[0]) if r[0] and r[0].startswith("[") else []
            if vals:
                results[f"{sk}_{r[3]}"] = {"vals": vals, "avg": r[1], "l5_avg": r[2], "src": r[3]}
    return results

def hit_rate(vals, line, direction="under"):
    if direction == "under":
        hits = sum(1 for v in vals if v < line)
    else:
        hits = sum(1 for v in vals if v > line)
    return hits, len(vals)

print("=" * 80)
print("PRECISE HIT RATE ANALYSIS FOR NIGHT COUPON")
print("=" * 80)

# GREMIO
print("\n1. GREMIO (Copa Sudamericana vs Montevideo City Torque)")
gremio = get_all_stats("gremio", ["game_total_goals", "goals", "fouls", "yellow_cards"])
for k, v in sorted(gremio.items()):
    u25h, u25t = hit_rate(v["vals"], 2.5, "under")
    u35h, u35t = hit_rate(v["vals"], 3.5, "under")
    print(f"  {k}: avg={v['avg']}, l5={v['l5_avg']}")
    print(f"    vals={v['vals']}")
    print(f"    Under 2.5: {u25h}/{u25t} ({100*u25h//max(u25t,1)}%) | Under 3.5: {u35h}/{u35t} ({100*u35h//max(u35t,1)}%)")

# SAO PAULO
print("\n2. SAO PAULO (Copa Sudamericana vs Boston River)")
sp = get_all_stats("sao paulo", ["game_total_goals", "goals", "fouls", "yellow_cards"])
for k, v in sorted(sp.items()):
    if "goals" in k or "fouls" in k:
        print(f"  {k}: avg={v['avg']}, l5={v['l5_avg']}")
        print(f"    vals={v['vals']}")

# MILLONARIOS
print("\n3. MILLONARIOS (Copa Sudamericana vs O'Higgins)")
mill = get_all_stats("millonarios", ["game_total_goals", "goals", "fouls", "yellow_cards"])
for k, v in sorted(mill.items()):
    print(f"  {k}: avg={v['avg']}, l5={v['l5_avg']}")
    print(f"    vals={v['vals']}")

# MONTEVIDEO CITY TORQUE
print("\n4. MONTEVIDEO CITY TORQUE")
torque = get_all_stats("montevideo city", ["game_total_goals", "goals"])
if not torque:
    torque = get_all_stats("torque", ["game_total_goals", "goals"])
for k, v in sorted(torque.items()):
    print(f"  {k}: avg={v['avg']}, l5={v['l5_avg']}")
    print(f"    vals={v['vals']}")

# COMBINED ANALYSIS for Gremio vs Torque Under 2.5
print("\n" + "=" * 80)
print("COMBINED PROJECTIONS")
print("=" * 80)
g_gtg = gremio.get("game_total_goals_flashscore")
if g_gtg:
    g_vals = g_gtg["vals"]
    u25, total = hit_rate(g_vals, 2.5, "under")
    u25_l5, _ = hit_rate(g_vals[:5], 2.5, "under")
    print(f"\nGremio Under 2.5 total goals: L10={u25}/{total}, L5={u25_l5}/5")
    print(f"  Gremio L5 avg = {g_gtg['l5_avg']} (trending {'DOWN' if g_gtg['l5_avg'] < g_gtg['avg'] else 'UP'})")
