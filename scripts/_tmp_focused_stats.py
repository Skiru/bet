#!/usr/bin/env python3
"""Focused stats for night coupon key matchups."""
import sqlite3, json

db = sqlite3.connect("betting/data/betting.db")

def get_stat(team, stat_key):
    rows = db.execute(
        "SELECT tf.l10_avg, tf.l5_avg, tf.l10_values, tf.source "
        "FROM team_form tf JOIN teams te ON tf.team_id = te.id "
        "WHERE LOWER(te.name) LIKE ? AND tf.stat_key = ? AND tf.l10_avg IS NOT NULL "
        "ORDER BY tf.updated_at DESC LIMIT 1",
        (f"%{team.lower()}%", stat_key)
    ).fetchone()
    if rows:
        vals = rows[2] or "[]"
        try:
            vals_list = json.loads(vals) if vals.startswith("[") else []
        except:
            vals_list = []
        return {"l10_avg": rows[0], "l5_avg": rows[1], "l10_values": vals_list, "source": rows[3]}
    return None

print("=" * 80)
print("NIGHT COUPON — KEY MATCHUP STATS")
print("=" * 80)

# 1. LANUS vs MIRASSOL (Copa Libertadores)
print("\n--- LANUS vs MIRASSOL (Copa Libertadores, 22:00) ---")
print("TIPSTER: Under 2.5 Goals @1.61")
lanus_gtg = get_stat("Lanus", "game_total_goals")
mirassol_gtg = get_stat("Mirassol", "game_total_goals")
mirassol_fouls = get_stat("Mirassol", "fouls")
mirassol_cards = get_stat("Mirassol", "yellow_cards")
if lanus_gtg:
    vals = lanus_gtg["l10_values"]
    under25 = sum(1 for v in vals if v < 2.5)
    print(f"  Lanus game_total_goals: L10avg={lanus_gtg['l10_avg']}, L5avg={lanus_gtg['l5_avg']}")
    print(f"    L10 raw: {vals}")
    print(f"    Under 2.5 hit rate: {under25}/{len(vals)} ({100*under25//max(len(vals),1)}%)")
if mirassol_gtg:
    vals = mirassol_gtg["l10_values"]
    under25 = sum(1 for v in vals if v < 2.5)
    print(f"  Mirassol game_total_goals: L10avg={mirassol_gtg['l10_avg']}, L5avg={mirassol_gtg['l5_avg']}")
    print(f"    L10 raw: {vals}")
    print(f"    Under 2.5 hit rate: {under25}/{len(vals)} ({100*under25//max(len(vals),1)}%)")
if mirassol_fouls:
    print(f"  Mirassol fouls: L10avg={mirassol_fouls['l10_avg']}, L5avg={mirassol_fouls['l5_avg']}")
    print(f"    L10 raw: {mirassol_fouls['l10_values']}")

# 2. SAO PAULO vs BOSTON RIVER (Copa Sudamericana)
print("\n--- SAO PAULO vs BOSTON RIVER (Copa Sudamericana, 22:00) ---")
sp_fouls = get_stat("Sao Paulo", "fouls")
sp_cards = get_stat("Sao Paulo", "yellow_cards")
sp_goals = get_stat("Sao Paulo", "goals")
br_goals = get_stat("Boston River", "goals")
if sp_fouls:
    print(f"  Sao Paulo fouls: L10avg={sp_fouls['l10_avg']}, L5avg={sp_fouls['l5_avg']}")
    print(f"    L10 raw: {sp_fouls['l10_values']}")
if sp_cards:
    print(f"  Sao Paulo yellow_cards: L10avg={sp_cards['l10_avg']}, L5avg={sp_cards['l5_avg']}")
    print(f"    L10 raw: {sp_cards['l10_values']}")
if sp_goals:
    print(f"  Sao Paulo goals: L10avg={sp_goals['l10_avg']}, L5avg={sp_goals['l5_avg']}")

# 3. GREMIO vs MONTEVIDEO CITY TORQUE
print("\n--- GREMIO vs MONTEVIDEO CITY TORQUE (Copa Sudamericana, 22:00) ---")
gremio_goals = get_stat("Gremio", "goals")
gremio_fouls = get_stat("Gremio", "fouls")
gremio_gtg = get_stat("Gremio", "game_total_goals")
if gremio_goals:
    print(f"  Gremio goals scored: L10avg={gremio_goals['l10_avg']}, L5avg={gremio_goals['l5_avg']}")
    print(f"    L10 raw: {gremio_goals['l10_values']}")
if gremio_fouls:
    print(f"  Gremio fouls: L10avg={gremio_fouls['l10_avg']}, L5avg={gremio_fouls['l5_avg']}")
    print(f"    L10 raw: {gremio_fouls['l10_values']}")
if gremio_gtg:
    print(f"  Gremio game_total_goals: L10avg={gremio_gtg['l10_avg']}, L5avg={gremio_gtg['l5_avg']}")

# 4. MONTREAL ALLIANCE vs NIAGARA RIVER LIONS (CEBL basketball)
print("\n--- MONTREAL ALLIANCE vs NIAGARA RIVER LIONS (CEBL, 23:30) ---")
mont_pts = get_stat("Montreal Alliance", "game_total_points")
niag_pts = get_stat("Niagara River Lions", "game_total_points")
mont_own = get_stat("Montreal Alliance", "points")
niag_own = get_stat("Niagara River Lions", "points")
if mont_pts:
    print(f"  Montreal game_total_points: L10avg={mont_pts['l10_avg']}, L5avg={mont_pts['l5_avg']}")
    print(f"    L10 raw: {mont_pts['l10_values']}")
if niag_pts:
    print(f"  Niagara game_total_points: L10avg={niag_pts['l10_avg']}, L5avg={niag_pts['l5_avg']}")
    print(f"    L10 raw: {niag_pts['l10_values']}")
if mont_own:
    print(f"  Montreal own points: L10avg={mont_own['l10_avg']}, L5avg={mont_own['l5_avg']}")
if niag_own:
    print(f"  Niagara own points: L10avg={niag_own['l10_avg']}, L5avg={niag_own['l5_avg']}")

# 5. EC PINHEIROS vs CORINTHIANS (NBB)
print("\n--- EC PINHEIROS vs SC CORINTHIANS (Brazil NBB, 23:30) ---")
pin_pts = get_stat("Pinheiros", "game_total_points")
pin_own = get_stat("Pinheiros", "points")
bras_pts = get_stat("Brasilia", "points")
if pin_pts:
    print(f"  Pinheiros game_total_points: L10avg={pin_pts['l10_avg']}, L5avg={pin_pts['l5_avg']}")
    print(f"    L10 raw: {pin_pts['l10_values']}")
if pin_own:
    print(f"  Pinheiros own points: L10avg={pin_own['l10_avg']}, L5avg={pin_own['l5_avg']}")

# 6. PALESTINO vs RIESTRA
print("\n--- PALESTINO vs DEPORTIVO RIESTRA (Copa Sudamericana, 22:00) ---")
print("TIPSTER: Palestino Win @2.23 + Over 2.5 Goals")
pal_fouls = get_stat("Palestino", "fouls")
pal_goals = get_stat("Palestino", "goals")
ries_fouls = get_stat("Riestra", "fouls")
ries_goals = get_stat("Riestra", "goals")
if pal_fouls:
    print(f"  Palestino fouls: L10avg={pal_fouls['l10_avg']}, L5avg={pal_fouls['l5_avg']}")
    print(f"    L10 raw: {pal_fouls['l10_values']}")
if pal_goals:
    print(f"  Palestino goals: L10avg={pal_goals['l10_avg']}, L5avg={pal_goals['l5_avg']}")
    print(f"    L10 raw: {pal_goals['l10_values']}")
if ries_fouls:
    print(f"  Riestra fouls: L10avg={ries_fouls['l10_avg']}, L5avg={ries_fouls['l5_avg']}")
    print(f"    L10 raw: {ries_fouls['l10_values']}")
if ries_goals:
    print(f"  Riestra goals: L10avg={ries_goals['l10_avg']}, L5avg={ries_goals['l5_avg']}")
    print(f"    L10 raw: {ries_goals['l10_values']}")

# 7. MILLONARIOS vs O'HIGGINS
print("\n--- MILLONARIOS vs O'HIGGINS (Copa Sudamericana, 22:00) ---")
mill_fouls = get_stat("Millonarios", "fouls")
mill_goals = get_stat("Millonarios", "goals")
if mill_fouls:
    print(f"  Millonarios fouls: L10avg={mill_fouls['l10_avg']}, L5avg={mill_fouls['l5_avg']}")
    print(f"    L10 raw: {mill_fouls['l10_values']}")
if mill_goals:
    print(f"  Millonarios goals: L10avg={mill_goals['l10_avg']}, L5avg={mill_goals['l5_avg']}")
    print(f"    L10 raw: {mill_goals['l10_values']}")
