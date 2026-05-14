import urllib.parse
import re
from typing import Optional, Dict, List
import requests
from bs4 import BeautifulSoup
import sys
import os

# Ensure we can import the api client
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))
from bet.api_clients.sofascore import SofascoreClient

client = SofascoreClient()

SPORT_STAT_MAPPING = {
    "football": {
        "corners": ["Corner kicks"],
        "fouls": ["Fouls"],
        "yellow_cards": ["Yellow cards"],
        "shots_on_target": ["Shots on target"],
        "shots_off_target": ["Shots off target"],
        "ball_possession": ["Ball possession", "Ball possession %"]
    },
    "tennis": {
        "aces": ["Aces"],
        "double_faults": ["Double faults"],
        "break_points_saved": ["Break points saved"],
        "win_1st_serve": ["First serve points", "1st serve won", "First serve won"]
    },
    "basketball": {
        "2_pointers": ["2 pointers", "Two points", "2-pointers"],
        "3_pointers": ["3 pointers", "Three points", "3-pointers"],
        "free_throws": ["Free throws"],
        "rebounds": ["Rebounds"],
        "turnovers": ["Turnovers"],
        "fouls": ["Fouls", "Personal fouls"]
    },
    "volleyball": {
        "aces": ["Aces"],
        "blocks": ["Blocks"],
        "errors": ["Errors", "Service errors"]
    },
    "hockey": {
        "shots": ["Shots on goal"],
        "pim": ["Penalty minutes", "PIM"],
        "power_play_goals": ["Power play goals", "Power play %"]
    }
}

def _find_sofascore_team_id(team_name: str, sport: str) -> Optional[str]:
    """Finds Sofascore unique team ID natively using Sofascore search API."""
    try:
        res = client._request("/search/all", params={"q": team_name})
        if not res or 'results' not in res:
            return None
            
        for r in res['results']:
            if r['type'] == 'team':
                entity = r['entity']
                # Check if sport matches if possible
                if entity.get('sport', {}).get('slug') == sport:
                    return str(entity['id'])
                    
        # Fallback to first team if sport doesn't match perfectly
        for r in res['results']:
            if r['type'] == 'team':
                return str(r['entity']['id'])
                
        return None
    except Exception as e:
        print(f"Error finding team ID for {team_name}: {e}")
        return None

def _try_sofascore(team_name: str, sport: str) -> tuple[Dict[str, List[float]], Optional[str]]:
    """
    Tries to retrieve the last 10 games statistics for a team from Sofascore.
    Returns (stats, errors_if_any).
    """
    stats: Dict[str, List[float]] = {}
    
    team_id = _find_sofascore_team_id(team_name, sport)
    if not team_id:
        return {}, "Team ID not found via search"
    
    try:
        events = client.get_team_last_fixtures(team_id)
        if not events:
            return {}, "No recent fixtures found"
        
        # Sort out stat mapping for this sport
        mapping = SPORT_STAT_MAPPING.get(sport, {})
        if not mapping:
            return {}, f"No stat mapping configured for sport: {sport}"
            
        # Initialize stats dict
        for key in mapping.keys():
            stats[key] = []
            
        # Iterate over the events to get the stats (up to 10)
        fetched = 0
        for ev in events:
            if fetched >= 10:
                break
                
            ev_id = str(ev['id'])
            
            # Determine if we are home or away
            is_home = ev['homeTeam']['id'] == int(team_id)
            
            st = client.get_fixture_stats(ev_id)
            if not st:
                continue
                
            # Sofascore returns a list of periods. [0] is usually 'ALL'
            all_period = st[0]
            
            collected_for_match = {k: None for k in mapping.keys()}
            
            for group in all_period.get('groups', []):
                for item in group.get('statisticsItems', []):
                    name = item['name']
                    # Check if this name maps to any of our target stats
                    for internal_key, possible_names in mapping.items():
                        if name in possible_names:
                            val = item['homeValue'] if is_home else item['awayValue']
                            # values might be strings with '%' or ints
                            if isinstance(val, str) and '%' in val:
                                val = val.replace('%', '').strip()
                            try:
                                collected_for_match[internal_key] = float(val)
                            except (ValueError, TypeError):
                                pass
                                
            # Append collected values if present, else 0.0 or skip
            for k in mapping.keys():
                if collected_for_match[k] is not None:
                    stats[k].append(collected_for_match[k])
                
            fetched += 1
            
        return stats, None
        
    except Exception as e:
        return {}, f"Sofascore API error: {str(e)}"
