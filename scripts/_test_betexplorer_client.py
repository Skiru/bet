import logging
from bet.api_clients.betexplorer import BetExplorerClient
from bet.api_clients.rate_limiter import RateLimiter

logging.basicConfig(level=logging.INFO)

def main():
    rate_limiter = RateLimiter(limits={"betexplorer-scraper": 50})
    client = BetExplorerClient(rate_limiter)
    
    print("Testing get_fixtures...")
    date = "2026-05-13" # Today
    for sport in ["football", "tennis", "basketball", "hockey", "volleyball"]:
        fixtures = client.get_fixtures(date, sport)
        print(f"\nFound {len(fixtures)} fixtures for {sport} on {date}")
        for f in fixtures[:3]:
            print(f"[{f.status}] {f.kickoff} | {f.competition_name} | {f.home_team_name} vs {f.away_team_name} (ID: {f.external_id})")

if __name__ == "__main__":
    main()
