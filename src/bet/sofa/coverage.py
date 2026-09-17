import json
import os
import statistics
from datetime import datetime, timedelta

def check_coverage_floor(runs_dir: str, current_date: str) -> dict[str, str]:
    """
    Checks if the number of READY fixtures for the current_date drops by > 40% 
    compared to the median of the last 10 runs for each sport independently.
    
    Returns a dict mapping sport to a warning string if a drop is detected.
    """
    # 1. Read current READY counts
    current_samples_path = os.path.join(runs_dir, current_date, "03_samples.json")
    if not os.path.exists(current_samples_path):
        return {}
        
    with open(current_samples_path) as f:
        current_samples = json.load(f)
        
    # We need sport info! Wait, 03_samples.json doesn't contain sport. 
    # Let's read 02_fixtures.json instead.
    current_fixtures_path = os.path.join(runs_dir, current_date, "02_fixtures.json")
    if not os.path.exists(current_fixtures_path):
        return {}
        
    with open(current_fixtures_path) as f:
        current_fixtures = json.load(f)
        
    sport_map = {f["sofascore_event_id"]: f["sport"] for f in current_fixtures}
    
    current_ready = {"football": 0, "tennis": 0}
    for s in current_samples:
        if s.get("readiness") == "READY":
            sport = sport_map.get(s["sofascore_event_id"])
            if sport:
                current_ready[sport] += 1
                
    # 2. Gather history
    history = {"football": [], "tennis": []}
    
    # Simple sort of date directories
    if not os.path.exists(runs_dir):
        return {}
        
    dates = sorted([d for d in os.listdir(runs_dir) if d < current_date and len(d) == 10])
    last_10 = dates[-10:]
    
    for d in last_10:
        samples_path = os.path.join(runs_dir, d, "03_samples.json")
        fixtures_path = os.path.join(runs_dir, d, "02_fixtures.json")
        
        if not os.path.exists(samples_path) or not os.path.exists(fixtures_path):
            continue
            
        with open(fixtures_path) as f:
            fixes = json.load(f)
        sm = {f["sofascore_event_id"]: f["sport"] for f in fixes}
        
        with open(samples_path) as f:
            samps = json.load(f)
            
        r_counts = {"football": 0, "tennis": 0}
        for s in samps:
            if s.get("readiness") == "READY":
                sp = sm.get(s["sofascore_event_id"])
                if sp:
                    r_counts[sp] += 1
                    
        history["football"].append(r_counts["football"])
        history["tennis"].append(r_counts["tennis"])
        
    # 3. Compare
    warnings = {}
    for sport, counts in history.items():
        if len(counts) >= 3:  # minimum history to compare
            med = statistics.median(counts)
            if med > 0:
                current = current_ready[sport]
                if current < med * 0.6:  # Drop > 40%
                    warnings[sport] = f"{sport} READY count ({current}) dropped by >40% vs median ({med})"
                    
    return warnings
