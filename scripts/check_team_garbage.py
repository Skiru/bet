"""Check live/upcoming events and team name issues."""
from bet.db.connection import get_db
import unicodedata
import json
import sys

if '--live' in sys.argv:
    with get_db() as db:
        cursor = db.execute('''
            SELECT f.kickoff, h.name, a.name, s.name
            FROM fixtures f
            JOIN teams h ON f.home_team_id = h.id
            JOIN teams a ON f.away_team_id = a.id
            JOIN sports s ON f.sport_id = s.id
            WHERE date(f.kickoff) = '2026-05-24'
            ORDER BY f.kickoff
            LIMIT 30
        ''')
        rows = cursor.fetchall()
        total = db.execute("SELECT COUNT(*) FROM fixtures WHERE date(kickoff) = '2026-05-24'").fetchone()[0]
        print(f"Total fixtures 2026-05-24: {total}")
        print(f"First 30:")
        for r in rows:
            print(f"  {r[0]} | {r[3]:10} | {r[1]} vs {r[2]}")

        # Tennis
        cursor = db.execute('''
            SELECT f.kickoff, h.name, a.name
            FROM fixtures f
            JOIN teams h ON f.home_team_id = h.id
            JOIN teams a ON f.away_team_id = a.id
            WHERE date(f.kickoff) = '2026-05-24' AND f.sport_id = 2
            ORDER BY f.kickoff LIMIT 20
        ''')
        rows = cursor.fetchall()
        print(f"\nTennis today: {len(rows)}")
        for r in rows:
            print(f"  {r[0]} | {r[1]} vs {r[2]}")
    sys.exit(0)

with get_db() as db:
    cursor = db.execute('SELECT COUNT(*) FROM teams')
    total = cursor.fetchone()[0]

    cursor = db.execute("""SELECT COUNT(*) FROM teams WHERE 
        length(name) > 50 
        OR name LIKE '%PLN%' OR name LIKE '%Bonus%' OR name LIKE '%Typy%'
        OR name LIKE '%Picks%' OR name LIKE '%Odds%' OR name LIKE '%VIDEO%'
        OR name LIKE '%http%' OR name LIKE '%połowa%' OR name LIKE '% - -%'
    """)
    garbage = cursor.fetchone()[0]
    print(f"Total teams: {total}, Garbage: {garbage} ({garbage*100//total}%)")

    # Diacritic duplication impact
    print("\n=== DIACRITIC DUPLICATES WITH DATA SPLIT ===")
    cursor = db.execute("SELECT id, name FROM teams WHERE name GLOB '*[^A-Za-z0-9 .()-]*' AND length(name) < 40")
    diacritic_teams = cursor.fetchall()
    data_splits = []
    for tid, name in diacritic_teams:
        ascii_name = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode()
        if ascii_name != name:
            cursor2 = db.execute('SELECT id, name FROM teams WHERE name = ?', (ascii_name,))
            dup = cursor2.fetchone()
            if dup:
                # Check if BOTH have team_form data (= data split)
                c1 = db.execute('SELECT COUNT(*) FROM team_form WHERE team_id = ?', (tid,)).fetchone()[0]
                c2 = db.execute('SELECT COUNT(*) FROM team_form WHERE team_id = ?', (dup[0],)).fetchone()[0]
                if c1 > 0 and c2 > 0:
                    data_splits.append((tid, name, c1, dup[0], dup[1], c2))
    
    print(f"  Total pairs with BOTH having data (split risk): {len(data_splits)}")
    for tid1, n1, c1, tid2, n2, c2 in data_splits[:20]:
        print(f"  SPLIT: [{tid1}]\"{n1}\"({c1}recs) vs [{tid2}]\"{n2}\"({c2}recs)")

    # Polish clubs specifically
    print("\n=== POLISH CLUBS (Ekstraklasa etc.) ===")
    polish = ['Jagiell', 'Legia', 'Lech', 'Raków', 'Rakow', 'Śląsk', 'Slask',
              'Zagłębie', 'Zaglebie', 'Piast', 'Cracovia', 'Wisła', 'Wisla',
              'Górnik', 'Gornik', 'Pogoń', 'Pogon', 'Warta', 'Stal']
    for name_part in polish:
        cursor = db.execute("SELECT id, name FROM teams WHERE name LIKE ?", (f'%{name_part}%',))
        variants = cursor.fetchall()
        if len(variants) > 1:
            # Check for actual name collision (same club, multiple entries)
            with_form = [(v[0], v[1], db.execute('SELECT COUNT(*) FROM team_form WHERE team_id=?', (v[0],)).fetchone()[0]) for v in variants if len(v[1]) < 50]
            with_form = [(i, n, c) for i, n, c in with_form if c > 0]
            if len(with_form) > 1:
                print(f"  {name_part}: {len(with_form)} entries with data")
                for i, n, c in with_form[:5]:
                    print(f"    [{i}] \"{n}\" — {c} form records")

    # Today's fixture ID mapping — check if analysis uses correct team_id
    print("\n=== TODAY'S KEY FIXTURES — TEAM_ID VERIFICATION ===")
    cursor = db.execute("""
        SELECT f.id, h.id, h.name, a.id, a.name, f.sport_id
        FROM fixtures f 
        JOIN teams h ON f.home_team_id = h.id
        JOIN teams a ON f.away_team_id = a.id
        WHERE date(f.kickoff) = '2026-05-24'
        AND (h.name LIKE '%Crystal%' OR h.name LIKE '%Andreeva%' OR h.name LIKE '%Dellien%'
             OR h.name LIKE '%Liberty%' OR h.name LIKE '%Cirstea%' OR h.name LIKE '%Sonego%')
        LIMIT 15
    """)
    for r in cursor.fetchall():
        home_form = db.execute('SELECT COUNT(*) FROM team_form WHERE team_id=?', (r[1],)).fetchone()[0]
        away_form = db.execute('SELECT COUNT(*) FROM team_form WHERE team_id=?', (r[3],)).fetchone()[0]
        print(f"  [{r[0]}] [{r[1]}]{r[2]} (form:{home_form}) vs [{r[3]}]{r[4]} (form:{away_form})")

    # Check if analysis_results correctly reference fixtures with right teams
    print("\n=== ANALYSIS_RESULTS FOR TODAY — TEAM MAPPING ===")
    cursor = db.execute("""
        SELECT ar.fixture_id, ar.best_market_name, ar.best_safety_score,
               h.name, a.name
        FROM analysis_results ar
        JOIN fixtures f ON ar.fixture_id = f.id
        JOIN teams h ON f.home_team_id = h.id
        JOIN teams a ON f.away_team_id = a.id
        WHERE ar.betting_date = '2026-05-24'
        LIMIT 10
    """)
    rows = cursor.fetchall()
    print(f"  Analysis results for today: {len(rows)}")
    for r in rows:
        print(f"  fix={r[0]}: {r[3]} vs {r[4]} — market:{r[1]} safety:{r[2]}")
