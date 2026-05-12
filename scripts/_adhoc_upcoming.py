import json
import datetime
from datetime import timezone
import os
import re

now = datetime.datetime.now(timezone.utc)

def run():
    print("=== UPCOMING EVENTS FROM S7 GATE RESULTS ===")
    try:
        with open('betting/data/2026-05-12_s7_gate_results.json', 'r') as f:
            data = json.load(f)
    except FileNotFoundError:
        print("s7 gate results not found.")
        return
        
    upcoming = []
    
    if isinstance(data, dict):
        if 'gate_results' in data:
            items = data['gate_results'].get('approved', []) + data['gate_results'].get('extended_pool', [])
        elif 'candidates' in data:
            items = data['candidates']
        else:
            items = list(data.values())
    elif isinstance(data, list):
        items = data
    else:
        items = []
        
    for item in items:
        ko = item.get('kickoff') or item.get('time')
        if not ko:
            continue
        try:
            # Replace Z with +00:00 for isoformat
            ko_str = ko.replace('Z', '+00:00')
            ko_dt = datetime.datetime.fromisoformat(ko_str)
            if ko_dt.tzinfo is None:
                ko_dt = ko_dt.replace(tzinfo=timezone.utc)
            if ko_dt > now:
                upcoming.append(item)
        except Exception as e:
            pass
            
    upcoming = sorted(upcoming, key=lambda x: datetime.datetime.fromisoformat(x.get('kickoff', x.get('time', '')).replace('Z', '+00:00')))
    
    print(f"Total matched up: {len(upcoming)}")
    for u in upcoming:
        print(f"[{u.get('kickoff')}] {u.get('sport')} - {u.get('event')} - EV: {u.get('expected_value')}")

if __name__ == '__main__':
    run()
