import json
import sys
from bet.db.connection import get_db
from bet.db.repositories import TeamRepo

def main():
    db = get_db()
    team_repo = TeamRepo(db)
    
    # Find teams
    teams = team_repo.get_all()
    inter = next((t for t in teams if "Internacional" in t.name), None)
    athletic = next((t for t in teams if "Athletic Club" in t.name), None)
    
    print(f"Internacional: {inter.name if inter else 'Not found'} (ID: {inter.id if inter else 'N/A'})")
    print(f"Athletic Club: {athletic.name if athletic else 'Not found'} (ID: {athletic.id if athletic else 'N/A'})")
    
    for team in [inter, athletic]:
        if not team:
            continue
        print(f"\n--- Stats for {team.name} ({team.id}) ---")
        forms = db.execute("SELECT stat_key, l10_avg, l10_values FROM team_form WHERE team_id = ?", (team.id,)).fetchall()
        for row in forms:
            r = dict(row)
            key = r.get('stat_key')
            avg = r.get('l10_avg')
            vals = r.get('l10_values')
            if any(x in key.lower() for x in ['corner', 'card', 'foul', 'booking', 'yellow', 'red']):
                print(f"{key}: L10_Avg={avg}, L10_Values={vals}")

if __name__ == '__main__':
    main()
