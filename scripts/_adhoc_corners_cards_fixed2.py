import json
import sys
from bet.db.connection import get_db

def main():
    with get_db() as db:
        teams = db.execute("SELECT id, name FROM teams WHERE name LIKE '%Internacional%' OR name LIKE '%Athletic Club%'").fetchall()
        
        for row in teams:
            team_id = dict(row)['id']
            team_name = dict(row)['name']
            print(f"\n--- Stats for {team_name} ({team_id}) ---")
            forms = db.execute("SELECT stat_key, l10_avg, l10_values FROM team_form WHERE team_id = ?", (team_id,)).fetchall()
            for f_row in forms:
                r = dict(f_row)
                key = r.get('stat_key')
                avg = r.get('l10_avg')
                vals = r.get('l10_values')
                if any(x in key.lower() for x in ['corner', 'card', 'foul', 'booking', 'yellow', 'red']):
                    print(f"{key}: L10_Avg={avg}, L10_Values={vals}")

if __name__ == '__main__':
    main()
