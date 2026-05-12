import argparse
import concurrent.futures
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) Gecko/20100101 Firefox/115.0",
    "Accept": "application/json",
}

def fetch_top_football_events(date_str: str) -> list:
    url = f"https://api.sofascore.com/api/v1/sport/football/scheduled-events/{date_str}"
    session = requests.Session()
    session.headers.update(HEADERS)
    try:
        resp = session.get(url, timeout=15)
        if resp.status_code == 200:
            events = resp.json().get('events', [])
            # Filter for higher-tier leagues to ensure they are on Betclic
            top_events = [e for e in events if e.get("tournament", {}).get("priority", 0) > 300]
            return top_events
    except Exception as e:
        logger.error(f"Error fetching football: {e}")
    return []

def enrich_event(ev: dict, session: requests.Session) -> Optional[dict]:
    event_id = ev.get('id')
    if not event_id: return None
    
    # 1. Fetch Odds
    odds_url = f"https://api.sofascore.com/api/v1/event/{event_id}/odds/1/all"
    odds = {}
    try:
        r = session.get(odds_url, timeout=5)
        if r.status_code == 200:
            markets = r.json().get("markets", [])
            for m in markets:
                if m.get("marketName") == "Full time":
                    for c in m.get("choices", []):
                        val = float(c.get("fractionalValue").split("/")[0]) / float(c.get("fractionalValue").split("/")[1]) + 1
                        if c.get("name") == "1": odds["home"] = round(val, 2)
                        elif c.get("name") == "X": odds["draw"] = round(val, 2)
                        elif c.get("name") == "2": odds["away"] = round(val, 2)
    except: pass
    
    # Require odds down the line
    if not odds: return None
    
    # 2. Fetch Form
    form_url = f"https://api.sofascore.com/api/v1/event/{event_id}/pregame-form"
    home_form, away_form = [], []
    try:
        r = session.get(form_url, timeout=5)
        if r.status_code == 200:
            data = r.json()
            home_form = data.get("homeTeam", {}).get("form", [])
            away_form = data.get("awayTeam", {}).get("form", [])
    except: pass

    # Evaluation
    # Calculate simple win probability based on form (W=1, D=0.5, L=0)
    def calc_form_score(form: list) -> float:
        if not form: return 0.0
        score = sum(1.0 if x == 'W' else 0.5 if x == 'D' else 0.0 for x in form)
        return score / len(form)
        
    home_score = calc_form_score(home_form)
    away_score = calc_form_score(away_form)
    
    dt_val = ev.get("startTimestamp", 0)
    
    return {
        "event_id": event_id,
        "date": datetime.fromtimestamp(dt_val, tz=timezone.utc).isoformat() if dt_val else "",
        "tournament": ev.get("tournament", {}).get("name", ""),
        "home": ev.get("homeTeam", {}).get("name", ""),
        "away": ev.get("awayTeam", {}).get("name", ""),
        "odds": odds,
        "home_form": home_form,
        "away_form": away_form,
        "home_form_score": round(home_score, 2),
        "away_form_score": round(away_score, 2)
    }

def main():
    date_str = datetime.now(timezone(timedelta(hours=2))).strftime("%Y-%m-%d")
    logger.info("--- BEAST MODE --- Starting completely unified, deep API pipeline...")
    
    events = fetch_top_football_events(date_str)
    logger.info(f"Targeting {len(events)} top-tier football matches...")
    
    session = requests.Session()
    session.headers.update(HEADERS)
    
    enriched = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(enrich_event, ev, session) for ev in events]
        for f in concurrent.futures.as_completed(futures):
            res = f.result()
            if res: enriched.append(res)
            
    logger.info(f"Successfully enriched {len(enriched)} matches with full odds and form.")
    
    # Evaluate for value bets (Very high form score, decent odds)
    value_picks = []
    for match in enriched:
        # Strategy: Home fortress (Home form > 0.8, away form < 0.6) with EV
        if match["home_form_score"] >= 0.8 and match["away_form_score"] <= 0.6:
            if match["odds"].get("home", 0) > 1.4:
                value_picks.append({
                    "match": f"{match['home']} vs {match['away']}",
                    "pick": f"{match['home']} ML (Win)",
                    "odds": match["odds"]["home"],
                    "reasoning": f"Home form [{','.join(match['home_form'])}] ({match['home_form_score']}) vs Away form [{','.join(match['away_form'])}] ({match['away_form_score']})",
                    "tournament": match["tournament"]
                })
        
        # Strategy: Away value
        if match["away_form_score"] >= 0.8 and match["home_form_score"] <= 0.6:
            if match["odds"].get("away", 0) > 1.5:
                value_picks.append({
                    "match": f"{match['home']} vs {match['away']}",
                    "pick": f"{match['away']} ML (Win)",
                    "odds": match["odds"]["away"],
                    "reasoning": f"Away form [{','.join(match['away_form'])}] ({match['away_form_score']}) vs Home form [{','.join(match['home_form'])}] ({match['home_form_score']})",
                    "tournament": match["tournament"]
                })

    # Sort by odds
    value_picks.sort(key=lambda x: x["odds"], reverse=True)
    
    logger.info(f"Identified {len(value_picks)} purely stats-driven value picks.")
    
    coupon = {
        "metadata": {
            "date": date_str,
            "pipeline": "BeastMode-API-V1",
            "matches_analyzed": len(enriched)
        },
        "value_picks": value_picks
    }
    
    with open("betting/coupons/beast_mode_today.json", "w", encoding="utf-8") as f:
        json.dump(coupon, f, ensure_ascii=False, indent=2)
        
    logger.info("Coupon JSON successfully generated at betting/coupons/beast_mode_today.json")

if __name__ == "__main__":
    main()