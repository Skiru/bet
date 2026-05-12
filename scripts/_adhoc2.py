import json
import datetime
from datetime import timezone

now = datetime.datetime.now(timezone.utc)

def run():
    try:
        with open('betting/data/2026-05-12_s7_gate_results.json', 'r') as f:
            data = json.load(f)
    except FileNotFoundError:
        print("s7 gate results not found.")
        return
        
    items = data.get('gate_results', {}).get('approved', []) + data.get('gate_results', {}).get('extended_pool', [])
    upcoming = []
    
    for item in items:
        ko = item.get('kickoff') or item.get('time')
        if not ko:
            continue
        try:
            ko_dt = datetime.datetime.fromisoformat(ko.replace('Z', '+00:00'))
            if ko_dt.tzinfo is None:
                ko_dt = ko_dt.replace(tzinfo=timezone.utc)
            if ko_dt > now:
                upcoming.append(item)
        except Exception:
            pass
            
    upcoming = sorted(upcoming, key=lambda x: datetime.datetime.fromisoformat(x.get('kickoff', x.get('time', '')).replace('Z', '+00:00')))
    
    print(f"## Upcoming Events ({len(upcoming)})\n")
    for u in upcoming:
        ko_str = u.get('kickoff', '')
        sport = u.get('sport', 'Unknown')
        home = u.get("home_team", "Unknown")
        away = u.get("away_team", "Unknown")
        market = u.get('best_market', {}).get('name', 'Unknown')
        direction = u.get('best_market', {}).get('direction', '')
        ss = u.get('best_market', {}).get('safety_score', 0)
        
        print(f"- **{ko_str}** | {sport.upper()} | {home} vs {away} | Market: {market} ({direction}) | Safety: {ss}")

if __name__ == '__main__':
    run()
