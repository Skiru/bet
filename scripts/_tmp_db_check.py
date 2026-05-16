"""Temporary DB quality check for 2026-05-16 pipeline state."""
import sqlite3

db = sqlite3.connect('betting/data/betting.db')

# Schema: check scan_results columns
cols = db.execute("PRAGMA table_info(scan_results)").fetchall()
print("=== SCAN_RESULTS COLUMNS ===")
for c in cols:
    print(f"  {c[1]} ({c[2]})")

# Check today's scan results sport breakdown  
print("\n=== SCAN RESULTS BY SPORT (today) ===")
rows = db.execute("""SELECT sport, COUNT(*) FROM scan_results 
    WHERE betting_date = '2026-05-16' GROUP BY sport ORDER BY COUNT(*) DESC""").fetchall()
for r in rows:
    print(f"  {r[0]}: {r[1]}")

# Check enrichment quality
print("\n=== TEAM FORM (updated today) ===")
tf_cols = db.execute("PRAGMA table_info(team_form)").fetchall()
print("  Columns:", [c[1] for c in tf_cols])
row = db.execute("SELECT COUNT(*) FROM team_form WHERE updated_at >= '2026-05-16'").fetchone()
print(f"  Updated today: {row[0]}")
row = db.execute("SELECT COUNT(*) FROM team_form").fetchone()
print(f"  Total: {row[0]}")

# Teams schema
t_cols = db.execute("PRAGMA table_info(teams)").fetchall()
print("\n=== TEAMS COLUMNS ===")
print("  ", [c[1] for c in t_cols])

# Check analysis depth
print("\n=== ANALYSIS RESULTS (today) ===")
ar_cols = db.execute("PRAGMA table_info(analysis_results)").fetchall()
print("  Columns:", [c[1] for c in ar_cols])
rows = db.execute("SELECT COUNT(*) FROM analysis_results WHERE betting_date = '2026-05-16'").fetchall()
print(f"  Total: {rows[0][0]}")

# Gate results schema
gr_cols = db.execute("PRAGMA table_info(gate_results)").fetchall()
print("\n=== GATE RESULTS COLUMNS ===")
print("  ", [c[1] for c in gr_cols])

# Check gate results  
print("\n=== GATE RESULTS (today) ===")
rows = db.execute("SELECT status, COUNT(*) FROM gate_results WHERE betting_date = '2026-05-16' GROUP BY status").fetchall()
for r in rows:
    print(f"  {r[0]}: {r[1]}")

# Check coupon builds
print("\n=== COUPONS (today) ===")
cp_cols = db.execute("PRAGMA table_info(coupons)").fetchall()
print("  Columns:", [c[1] for c in cp_cols])
rows = db.execute("SELECT * FROM coupons ORDER BY id DESC LIMIT 5").fetchall()
for r in rows:
    print(f"  {r}")

# Check what sports have data in tipster consensus
print("\n=== TIPSTER DATA ===")
tc_cols = db.execute("PRAGMA table_info(tipster_consensus)").fetchall()
print("  Columns:", [c[1] for c in tc_cols])
rows = db.execute("SELECT sport, COUNT(*) FROM tipster_consensus GROUP BY sport ORDER BY COUNT(*) DESC LIMIT 5").fetchall()
for r in rows:
    print(f"  {r[0]}: {r[1]}")

# Check bets table
print("\n=== RECENT BETS ===")
bt_cols = db.execute("PRAGMA table_info(bets)").fetchall()
print("  Columns:", [c[1] for c in bt_cols])
rows = db.execute("SELECT * FROM bets ORDER BY id DESC LIMIT 3").fetchall()
for r in rows:
    print(f"  {r}")

# 3-way check quality
print("\n=== 3-WAY CHECK QUALITY (today) ===")
rows = db.execute("""SELECT 
    COUNT(*) as total,
    SUM(CASE WHEN three_way_check_json IS NOT NULL AND three_way_check_json != '{}' AND three_way_check_json != 'null' THEN 1 ELSE 0 END) as has_3way
FROM analysis_results WHERE betting_date = '2026-05-16'""").fetchall()
print(f"  Total: {rows[0][0]}, With 3-way data: {rows[0][1]}")

# H2H data 
print("\n=== H2H DATA (today) ===")
rows = db.execute("""SELECT COUNT(*) FROM team_form 
    WHERE h2h_values IS NOT NULL AND h2h_values != '[]' AND h2h_values != '' 
    AND updated_at >= '2026-05-16'""").fetchone()
print(f"  Team form entries with H2H (today): {rows[0]}")
rows = db.execute("""SELECT COUNT(*) FROM team_form 
    WHERE h2h_values IS NOT NULL AND h2h_values != '[]' AND h2h_values != ''""").fetchone()
print(f"  Team form entries with H2H (all time): {rows[0]}")

db.close()
