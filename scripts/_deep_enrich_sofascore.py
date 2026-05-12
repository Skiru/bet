import json
import logging
import argparse
import concurrent.futures
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional
import requests
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# --- PYDANTIC MODELS ---

class Team(BaseModel):
    name: str = Field(..., description="Team name")
    id: int = Field(..., description="Sofascore internal ID")

class Odds(BaseModel):
    home_win: Optional[float] = None
    draw: Optional[float] = None
    away_win: Optional[float] = None
    over_2_5: Optional[float] = None
    under_2_5: Optional[float] = None

class FormStats(BaseModel):
    last_5_matches: List[str] = Field(default_factory=list, description="W, D, L sequence")
    total_goals_scored: Optional[int] = None
    total_goals_conceded: Optional[int] = None

class H2HStats(BaseModel):
    total_matches: int = 0
    home_wins: int = 0
    draws: int = 0
    away_wins: int = 0

class EnrichedMatch(BaseModel):
    event_id: int
    dt_start: str = Field(..., description="Match start time ISO")
    tournament: str
    home_team: Team
    away_team: Team
    odds: Odds
    h2h: H2HStats
    home_form: FormStats
    away_form: FormStats

# --- CLIENT ---

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) Gecko/20100101 Firefox/115.0",
    "Accept": "application/json",
}

def fetch_odds(session: requests.Session, event_id: int) -> Odds:
    url = f"https://api.sofascore.com/api/v1/event/{event_id}/odds/1/all"
    try:
        resp = session.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            markets = data.get("markets", [])
            odds_obj = Odds()
            for market in markets:
                if market.get("marketName") == "Full time":
                    for choice in market.get("choices", []):
                        val = float(choice.get("fractionalValue").split("/")[0]) / float(choice.get("fractionalValue").split("/")[1]) + 1
                        if choice.get("name") == "1": odds_obj.home_win = round(val, 2)
                        elif choice.get("name") == "X": odds_obj.draw = round(val, 2)
                        elif choice.get("name") == "2": odds_obj.away_win = round(val, 2)
                elif market.get("marketName") == "Total goals":
                    for choice in market.get("choices", []):
                        if choice.get("name") == "Over" and choice.get("initialFractionalValue") == "5/2": # Usually 2.5
                           pass # Simplified
            return odds_obj
    except Exception as e:
        logger.warning(f"Failed to fetch odds for {event_id}: {e}")
    return Odds()

def fetch_h2h(session: requests.Session, event_id: int) -> H2HStats:
    url = f"https://api.sofascore.com/api/v1/event/{event_id}/h2h"
    try:
        resp = session.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json().get('teamStats', {})
            return H2HStats(
                total_matches=data.get('H2H', {}).get('totalMatches', 0),
                home_wins=data.get('H2H', {}).get('winsHome', 0),
                draws=data.get('H2H', {}).get('draws', 0),
                away_wins=data.get('H2H', {}).get('winsAway', 0),
            )
    except Exception as e:
        logger.warning(f"Failed to fetch H2H for {event_id}: {e}")
    return H2HStats()

def fetch_form(session: requests.Session, event_id: int) -> (FormStats, FormStats):
    url = f"https://api.sofascore.com/api/v1/event/{event_id}/pregame-form"
    try:
        resp = session.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            hf = data.get('homeTeam', {}).get('form', [])
            af = data.get('awayTeam', {}).get('form', [])
            return FormStats(last_5_matches=hf), FormStats(last_5_matches=af)
    except Exception as e:
        logger.warning(f"Failed to fetch form for {event_id}: {e}")
    return FormStats(), FormStats()

def process_event(ev: dict) -> Optional[EnrichedMatch]:
    event_id = ev.get('id')
    if not event_id: return None
    
    session = requests.Session()
    session.headers.update(HEADERS)
    
    odds = fetch_odds(session, event_id)
    h2h = fetch_h2h(session, event_id)
    home_form, away_form = fetch_form(session, event_id)
    
    dt_val = ev.get("startTimestamp", 0)
    dt = datetime.fromtimestamp(dt_val, tz=timezone.utc).isoformat() if dt_val else ""
    
    return EnrichedMatch(
        event_id=event_id,
        dt_start=dt,
        tournament=ev.get("tournament", {}).get("name", "Unknown"),
        home_team=Team(name=ev.get("homeTeam", {}).get("name", ""), id=ev.get("homeTeam", {}).get("id", 0)),
        away_team=Team(name=ev.get("awayTeam", {}).get("name", ""), id=ev.get("awayTeam", {}).get("id", 0)),
        odds=odds,
        h2h=h2h,
        home_form=home_form,
        away_form=away_form
    )

def main(date_str: str, limit: int = 10, output_file: str = "sofascore_enriched.json"):
    url = f"https://api.sofascore.com/api/v1/sport/football/scheduled-events/{date_str}"
    
    session = requests.Session()
    session.headers.update(HEADERS)
    
    logger.info(f"Fetching raw events for {date_str}...")
    resp = session.get(url, timeout=15)
    if resp.status_code != 200:
        logger.error(f"Failed to get events: {resp.status_code}")
        return
        
    events = resp.json().get('events', [])
    logger.info(f"Found {len(events)} events. Taking first {limit} for deep enrichment...")
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        enriched_matches = list(executor.map(process_event, events[:limit]))
    
    # Filter None
    valid_matches = [m.model_dump() for m in enriched_matches if m is not None]
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(valid_matches, f, ensure_ascii=False, indent=2)
        
    logger.info(f"Successfully processed and saved {len(valid_matches)} enriched matches to {output_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=datetime.now(timezone(timedelta(hours=2))).strftime("%Y-%m-%d"), help="YYYY-MM-DD")
    parser.add_argument("--limit", type=int, default=10, help="Number of events to enrich (diagnostics)")
    parser.add_argument("--output", default="sofascore_enriched.json")
    args = parser.parse_args()
    
    main(args.date, args.limit, args.output)
