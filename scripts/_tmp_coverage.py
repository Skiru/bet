#!/usr/bin/env python3
"""Check team_form DB coverage for night events."""
import sqlite3

db = sqlite3.connect("betting/data/betting.db")
db.row_factory = sqlite3.Row

teams = [
    "LDU Quito", "Always Ready", "Lanus", "Mirassol",
    "Sao Paulo", "Boston River", "Millonarios", "O Higgins",
    "Gremio", "Montevideo City Torque", "Palestino", "Deportivo Riestra",
    "Sesi Franca", "Brasilia", "Pinheiros", "Corinthians",
    "Montreal Alliance", "Niagara River Lions",
    "Fort Wayne Komets", "Kansas City Mavericks",
    "Brown de Adrogue", "Comunicaciones", "UAI Urquiza",
    "Deportivo Merlo", "Liniers", "Ituzaingo", "Laferrere",
    "9z", "KRU", "Chivas", "Contra"
]

print("=== TEAM FORM COVERAGE ===")
covered = 0
for t in teams:
    rows = db.execute(
        "SELECT tf.stat_key, tf.l10_avg, tf.l5_avg, tf.source, te.name "
        "FROM team_form tf JOIN teams te ON tf.team_id = te.id "
        "WHERE LOWER(te.name) LIKE ? LIMIT 8",
        (f"%{t.lower()}%",)
    ).fetchall()
    if rows:
        covered += 1
        keys = [r["stat_key"] for r in rows]
        src = rows[0]["source"]
        print(f"  OK {t}: {len(rows)} stats ({keys[:4]}) [src: {src}]")
    else:
        print(f"  -- {t}: NO DATA")

print(f"\nCoverage: {covered}/{len(teams)} ({100*covered//len(teams)}%)")

# Also check for Libertadores/Sudamericana in analysis_results
print("\n=== EXISTING ANALYSIS FOR TONIGHT ===")
rows = db.execute(
    "SELECT event_name, best_market, safety_score, status "
    "FROM analysis_results WHERE betting_date = '2026-05-26' "
    "AND (event_name LIKE '%LDU%' OR event_name LIKE '%Gremio%' "
    "OR event_name LIKE '%Lanus%' OR event_name LIKE '%Sao Paulo%' "
    "OR event_name LIKE '%Millonarios%' OR event_name LIKE '%Palestino%' "
    "OR event_name LIKE '%Franca%' OR event_name LIKE '%Corinthians%') "
    "LIMIT 20"
).fetchall()
for r in rows:
    print(f"  {r['event_name']}: {r['best_market']} (safety={r['safety_score']}, status={r['status']})")
if not rows:
    print("  None found")

# Check teams table exists
print("\n=== TEAMS TABLE ===")
cnt = db.execute("SELECT COUNT(*) FROM teams").fetchone()[0]
print(f"Total teams in DB: {cnt}")
