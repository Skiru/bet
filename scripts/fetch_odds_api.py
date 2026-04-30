#!/usr/bin/env python3
"""
Fetch odds from The Odds API for all configured sports.

Usage:
    python3 scripts/fetch_odds_api.py                     # fetch all sports
    python3 scripts/fetch_odds_api.py --sports mlb,nba    # fetch specific sports
    python3 scripts/fetch_odds_api.py --list-sports       # list available sports (FREE, 0 credits)
    python3 scripts/fetch_odds_api.py --scores mlb        # fetch scores for settlement

Requires ODDS_API_KEY env var or config/odds_api_key.txt file.
Free tier: 500 credits/month. Each sport+market+region = 1 credit.
"""

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    import requests
except ImportError:
    print("ERROR: requests not installed. Run: pip3 install requests")
    sys.exit(1)

BASE_URL = "https://api.the-odds-api.com/v4"
DATA_DIR = Path(__file__).parent.parent / "betting" / "data"
CONFIG_DIR = Path(__file__).parent.parent / "config"

# Map our config sports to Odds API sport keys
# Some sports have multiple keys (e.g., soccer has many leagues)
SPORT_KEY_MAP = {
    "football": [
        "soccer_epl", "soccer_germany_bundesliga", "soccer_spain_la_liga",
        "soccer_italy_serie_a", "soccer_france_ligue_one",
        "soccer_netherlands_eredivisie", "soccer_portugal_primeira_liga",
        "soccer_turkey_super_league", "soccer_poland_ekstraklasa",
        "soccer_usa_mls", "soccer_brazil_campeonato",
        "soccer_uefa_champs_league", "soccer_uefa_europa_league",
        "soccer_efl_champ", "soccer_spain_segunda_division",
    ],
    "tennis": [
        "tennis_atp_french_open", "tennis_wta_french_open",
        "tennis_atp_aus_open", "tennis_wta_aus_open",
        "tennis_atp_us_open", "tennis_wta_us_open",
        "tennis_atp_wimbledon", "tennis_wta_wimbledon",
        # API auto-discovers in-season ATP/WTA events;
        # Grand Slam keys are fallbacks. Use --list-sports to see active keys.
    ],
    "basketball": ["basketball_nba", "basketball_euroleague", "basketball_ncaab"],
    "hockey": ["icehockey_nhl", "icehockey_shl"],
    "baseball": ["baseball_mlb"],
    "mma": ["mma_mixed_martial_arts"],
    # These sports are NOT covered by the API — skip silently
    "volleyball": [],
    "esports": [],
    "snooker": [],
    "table_tennis": [],
    "darts": [],
    "handball": [],
    "padel": [],
    "speedway": [],
}


def get_api_key():
    """Get API key from env var, api_keys.json, or config file."""
    key = os.environ.get("ODDS_API_KEY")
    if key and key.strip():
        return key.strip()

    # Check api_keys.json (shared key store)
    keys_json = CONFIG_DIR / "api_keys.json"
    if keys_json.exists():
        try:
            import json
            keys = json.loads(keys_json.read_text())
            key = keys.get("odds-api", "").strip()
            if key:
                return key
        except (json.JSONDecodeError, AttributeError):
            pass

    key_file = CONFIG_DIR / "odds_api_key.txt"
    if key_file.exists():
        for line in key_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                return line

    print("ERROR: No API key found.")
    print("  Set ODDS_API_KEY env var, or create config/odds_api_key.txt")
    print("  Get free key at: https://the-odds-api.com/#get-started")
    sys.exit(1)


def list_sports(api_key):
    """List all available in-season sports (FREE — 0 credits)."""
    resp = requests.get(f"{BASE_URL}/sports", params={"apiKey": api_key}, timeout=15)
    resp.raise_for_status()

    sports = resp.json()
    remaining = resp.headers.get("x-requests-remaining", "?")
    used = resp.headers.get("x-requests-used", "?")

    print(f"\n{'Key':<45} {'Group':<25} {'Title':<30} {'Active'}")
    print("-" * 110)
    for s in sorted(sports, key=lambda x: (x["group"], x["key"])):
        print(f"{s['key']:<45} {s['group']:<25} {s['title']:<30} {s['active']}")

    print(f"\nTotal: {len(sports)} sports | Credits used: {used} | Remaining: {remaining}")
    return sports


def fetch_odds(api_key, sport_key, markets="h2h,totals", regions="eu",
               commence_from=None, commence_to=None):
    """Fetch odds for a specific sport key. Returns list of events with odds."""
    params = {
        "apiKey": api_key,
        "regions": regions,
        "markets": markets,
        "oddsFormat": "decimal",
    }
    if commence_from:
        params["commenceTimeFrom"] = commence_from
    if commence_to:
        params["commenceTimeTo"] = commence_to

    resp = requests.get(f"{BASE_URL}/sports/{sport_key}/odds", params=params, timeout=15)

    if resp.status_code == 422:
        # Sport not in season or invalid key
        return [], resp.headers
    resp.raise_for_status()

    return resp.json(), resp.headers


def fetch_scores(api_key, sport_key, days_from=1):
    """Fetch scores for settlement (cost: 2 credits with daysFrom, 1 without)."""
    params = {
        "apiKey": api_key,
        "daysFrom": days_from,
    }
    resp = requests.get(f"{BASE_URL}/sports/{sport_key}/scores", params=params, timeout=15)
    if resp.status_code == 422:
        return [], resp.headers
    resp.raise_for_status()
    return resp.json(), resp.headers


def extract_best_odds(event):
    """Extract market-best odds from an event's bookmakers."""
    result = {
        "id": event["id"],
        "home_team": event["home_team"],
        "away_team": event["away_team"],
        "commence_time": event["commence_time"],
        "markets": {},
    }

    for market_type in ["h2h", "totals", "spreads"]:
        best = {}
        for bm in event.get("bookmakers", []):
            for market in bm.get("markets", []):
                if market["key"] != market_type:
                    continue
                for outcome in market.get("outcomes", []):
                    key = outcome["name"]
                    if "point" in outcome:
                        key = f"{outcome['name']}_{outcome['point']}"
                    price = outcome["price"]
                    if key not in best or price > best[key]["price"]:
                        best[key] = {
                            "price": price,
                            "bookmaker": bm["title"],
                            "point": outcome.get("point"),
                        }
        if best:
            result["markets"][market_type] = best

    return result


def format_event_summary(event, sport_key):
    """Format a single event as a readable line."""
    home = event["home_team"]
    away = event["away_team"]
    time_str = event["commence_time"][:16].replace("T", " ")

    parts = [f"  {away} @ {home} | {time_str} UTC"]

    best = extract_best_odds(event)

    # Show totals if available
    totals = best["markets"].get("totals", {})
    over_keys = [k for k in totals if k.startswith("Over")]
    under_keys = [k for k in totals if k.startswith("Under")]
    if over_keys and under_keys:
        over_key = sorted(over_keys)[0]
        under_key = sorted(under_keys)[0]
        o = totals[over_key]
        u = totals[under_key]
        parts.append(f"O/U {o.get('point', '?')}: O {o['price']:.2f} ({o['bookmaker']}) / U {u['price']:.2f} ({u['bookmaker']})")

    # Show h2h if available
    h2h = best["markets"].get("h2h", {})
    if home in h2h and away in h2h:
        parts.append(f"ML: {home} {h2h[home]['price']:.2f} / {away} {h2h[away]['price']:.2f}")

    return " | ".join(parts)


def run_full_scan(api_key, sport_filter=None, betting_day_window=True):
    """Run a full odds scan across all configured sports."""
    now = datetime.now(timezone.utc)

    # Betting day window: 04:00 UTC today to 03:59 UTC tomorrow (= 06:00-05:59 CEST)
    commence_from = None
    commence_to = None
    if betting_day_window:
        commence_from = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        commence_to = (now + timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")

    all_events = []
    total_credits_used = 0
    credits_remaining = "?"

    # Determine which sports to scan
    sports_to_scan = {}
    for our_sport, api_keys in SPORT_KEY_MAP.items():
        if not api_keys:
            continue
        if sport_filter and our_sport not in sport_filter:
            continue
        sports_to_scan[our_sport] = api_keys

    print(f"\n{'='*80}")
    print(f"THE ODDS API — Full Scan @ {now.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*80}")

    for our_sport, api_keys in sports_to_scan.items():
        print(f"\n--- {our_sport.upper()} ---")
        sport_events = []

        for sport_key in api_keys:
            try:
                events, headers = fetch_odds(
                    api_key, sport_key,
                    markets="h2h,totals",
                    regions="eu",
                    commence_from=commence_from,
                    commence_to=commence_to,
                )
                credits_remaining = headers.get("x-requests-remaining", credits_remaining)
                last_cost = headers.get("x-requests-last", "0")
                total_credits_used += int(last_cost) if last_cost else 0

                if events:
                    for e in events:
                        e["_sport_key"] = sport_key
                        e["_our_sport"] = our_sport
                    sport_events.extend(events)
                    print(f"  {sport_key}: {len(events)} events (cost: {last_cost})")
                else:
                    print(f"  {sport_key}: no events")

            except requests.exceptions.HTTPError as exc:
                print(f"  {sport_key}: ERROR {exc}")
            except Exception as exc:
                print(f"  {sport_key}: ERROR {exc}")

        # Print event summaries
        for ev in sport_events:
            print(format_event_summary(ev, ev["_sport_key"]))

        all_events.extend(sport_events)

    # Save raw data
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    output_file = DATA_DIR / "odds_api_snapshot.json"
    snapshot = {
        "timestamp": now.isoformat(),
        "credits_used_this_scan": total_credits_used,
        "credits_remaining": credits_remaining,
        "total_events": len(all_events),
        "events": all_events,
    }
    output_file.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False))

    # Save summary CSV for easy parsing (proper quoting for team names with commas)
    summary_file = DATA_DIR / "odds_api_summary.csv"
    with open(summary_file, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["sport", "sport_key", "home", "away", "commence_time",
                         "h2h_home", "h2h_away", "total_line", "over_price",
                         "over_book", "under_price", "under_book"])
        for ev in all_events:
            best = extract_best_odds(ev)
            h2h = best["markets"].get("h2h", {})
            totals = best["markets"].get("totals", {})

            h2h_home = h2h.get(ev["home_team"], {}).get("price", "")
            h2h_away = h2h.get(ev["away_team"], {}).get("price", "")

            over_keys = [k for k in totals if k.startswith("Over")]
            under_keys = [k for k in totals if k.startswith("Under")]

            total_line = ""
            over_price = ""
            over_book = ""
            under_price = ""
            under_book = ""

            if over_keys:
                ok = sorted(over_keys)[0]
                over_price = totals[ok]["price"]
                over_book = totals[ok]["bookmaker"]
                total_line = totals[ok].get("point", "")
            if under_keys:
                uk = sorted(under_keys)[0]
                under_price = totals[uk]["price"]
                under_book = totals[uk]["bookmaker"]

            writer.writerow([ev.get("_our_sport", ""), ev["_sport_key"],
                             ev["home_team"], ev["away_team"],
                             ev["commence_time"], h2h_home, h2h_away,
                             total_line, over_price, over_book,
                             under_price, under_book])

    print(f"\n{'='*80}")
    print(f"SUMMARY: {len(all_events)} events across {len(sports_to_scan)} sports")
    print(f"Credits used: {total_credits_used} | Remaining: {credits_remaining}")
    print(f"Data saved: {output_file}")
    print(f"CSV saved:  {summary_file}")
    print(f"{'='*80}\n")

    return all_events


def run_scores(api_key, sport_filter, days_from=2):
    """Fetch scores for settlement and save to odds_api_scores.json."""
    print(f"\nFetching scores for: {sport_filter} (daysFrom={days_from})")
    all_scores = []
    now = datetime.now(timezone.utc)
    for sport_name in sport_filter:
        api_keys = SPORT_KEY_MAP.get(sport_name, [])
        for sport_key in api_keys:
            try:
                scores, headers = fetch_scores(api_key, sport_key, days_from=days_from)
                remaining = headers.get("x-requests-remaining", "?")
                print(f"\n--- {sport_key} ({len(scores)} games) | Credits remaining: {remaining} ---")
                for game in scores:
                    game["_sport_key"] = sport_key
                    game["_our_sport"] = sport_name
                    status = "FINAL" if game.get("completed") else "LIVE" if game.get("scores") else "UPCOMING"
                    scores_str = ""
                    if game.get("scores"):
                        scores_str = " | ".join(
                            f"{s['name']}: {s['score']}" for s in game["scores"]
                        )
                    print(f"  {game['away_team']} @ {game['home_team']} [{status}] {scores_str}")
                all_scores.extend(scores)
            except Exception as exc:
                print(f"  {sport_key}: ERROR {exc}")

    # Save to JSON for settle_on_finish.py
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    scores_file = DATA_DIR / "odds_api_scores.json"
    scores_data = {
        "timestamp": now.isoformat(),
        "days_from": days_from,
        "total_games": len(all_scores),
        "events": all_scores,
    }
    scores_file.write_text(json.dumps(scores_data, indent=2, ensure_ascii=False))
    completed = sum(1 for g in all_scores if g.get("completed"))
    print(f"\nScores saved: {scores_file} ({len(all_scores)} games, {completed} completed)")


def main():
    parser = argparse.ArgumentParser(description="Fetch odds from The Odds API")
    parser.add_argument("--list-sports", action="store_true", help="List available sports (FREE)")
    parser.add_argument("--sports", type=str, help="Comma-separated sports to fetch (e.g., baseball,hockey)")
    parser.add_argument("--scores", type=str, help="Fetch scores for settlement (e.g., baseball,hockey)")
    parser.add_argument("--no-window", action="store_true", help="Don't filter by betting day window")
    args = parser.parse_args()

    api_key = get_api_key()

    if args.list_sports:
        list_sports(api_key)
        return

    if args.scores:
        sport_filter = [s.strip() for s in args.scores.split(",")]
        run_scores(api_key, sport_filter)
        return

    sport_filter = None
    if args.sports:
        sport_filter = [s.strip() for s in args.sports.split(",")]

    run_full_scan(api_key, sport_filter=sport_filter, betting_day_window=not args.no_window)


if __name__ == "__main__":
    main()
