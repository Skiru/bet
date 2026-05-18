"""Live integration test: GoogleSportsClient with DB save.

Tests the full pipeline: query SerpAPI → parse → save to DB.
Uses REAL matches from today/upcoming to validate.
"""

import json
import sys
from pathlib import Path

# Setup paths
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from api_clients import get_client
from api_clients.rate_limiter import RateLimiter


def test_football():
    """Test football H2H enrichment."""
    print(f"\n{'='*60}")
    print("TEST 1: Football H2H — Barcelona vs Real Sociedad")
    print(f"{'='*60}")
    
    rl = RateLimiter()
    client = get_client("google-sports", rl)
    
    enrichment = client.get_h2h_enrichment_and_save("Barcelona", "Real Sociedad", sport="football")
    
    print(f"  Query: {enrichment.query}")
    print(f"  H2H matches found: {len(enrichment.h2h_matches)}")
    for i, match in enumerate(enrichment.h2h_matches):
        print(f"    [{i+1}] {match.home_team} {match.home_score} - {match.away_score} {match.away_team}")
        print(f"        📅 {match.date} | 🏆 {match.tournament} | 🏟️ {match.venue}")
        if match.has_red_card_home or match.has_red_card_away:
            print(f"        🟥 Red cards: home={match.has_red_card_home}, away={match.has_red_card_away}")
    
    print(f"  Team KGMIDs: {enrichment.team_kgmids}")
    print(f"  Budget: {client.get_budget_status()}")
    return enrichment


def test_tennis():
    """Test tennis H2H enrichment."""
    print(f"\n{'='*60}")
    print("TEST 2: Tennis H2H — Djokovic vs Alcaraz")
    print(f"{'='*60}")
    
    rl = RateLimiter()
    client = get_client("google-sports", rl)
    
    enrichment = client.get_h2h_enrichment_and_save("Djokovic", "Alcaraz", sport="tennis")
    
    print(f"  Query: {enrichment.query}")
    print(f"  H2H matches found: {len(enrichment.h2h_matches)}")
    for i, match in enumerate(enrichment.h2h_matches):
        print(f"    [{i+1}] {match.player1} vs {match.player2}")
        print(f"        Sets: {match.sets}")
        print(f"        🏆 {match.tournament} | Stage: {match.stage} | Winner: {match.winner}")
        print(f"        Rankings: {match.player1} #{match.player1_ranking}, {match.player2} #{match.player2_ranking}")
    
    print(f"  Budget: {client.get_budget_status()}")
    return enrichment


def test_hockey():
    """Test hockey H2H enrichment."""
    print(f"\n{'='*60}")
    print("TEST 3: Hockey H2H — Oilers vs Panthers")
    print(f"{'='*60}")
    
    rl = RateLimiter()
    client = get_client("google-sports", rl)
    
    enrichment = client.get_h2h_enrichment_and_save("Oilers", "Panthers", sport="hockey")
    
    print(f"  Query: {enrichment.query}")
    print(f"  H2H matches found: {len(enrichment.h2h_matches)}")
    for i, match in enumerate(enrichment.h2h_matches):
        print(f"    [{i+1}] {match.home_team} {match.home_score} - {match.away_score} {match.away_team}")
        print(f"        📅 {match.date} | 🏆 {match.tournament} | 🏟️ {match.venue}")
    
    print(f"  Budget: {client.get_budget_status()}")
    return enrichment


def test_today_match():
    """Test with a match happening today (should get game_spotlight with goals)."""
    print(f"\n{'='*60}")
    print("TEST 4: Today's match — PSG vs Paris FC (cached from earlier)")
    print(f"{'='*60}")
    
    rl = RateLimiter()
    client = get_client("google-sports", rl)
    
    enrichment = client.get_h2h_enrichment("PSG", "Paris FC", sport="football")
    
    print(f"  Query: {enrichment.query}")
    print(f"  H2H matches: {len(enrichment.h2h_matches)}")
    
    if enrichment.current_match:
        print(f"\n  🔴 LIVE/TODAY MATCH DATA:")
        cm = enrichment.current_match
        print(f"     League: {cm.get('league')}")
        print(f"     Status: {cm.get('status')}")
        print(f"     Stadium: {cm.get('stadium')}")
        teams = cm.get("teams", [])
        for t in teams:
            print(f"     {t.get('name')}: {t.get('score')}")
    
    if enrichment.goal_scorers:
        print(f"\n  ⚽ GOAL SCORERS:")
        for gs in enrichment.goal_scorers:
            print(f"     {gs['time_display']} — {gs['player']} ({gs['team']}) #{gs['jersey_number']}")
    
    print(f"\n  Team KGMIDs: {enrichment.team_kgmids}")
    print(f"  Budget: {client.get_budget_status()}")
    return enrichment


def test_normalized_h2h():
    """Test the BaseAPIClient get_h2h() interface for pipeline compatibility."""
    print(f"\n{'='*60}")
    print("TEST 5: Normalized H2H interface (pipeline compatible)")
    print(f"{'='*60}")
    
    rl = RateLimiter()
    client = get_client("google-sports", rl)
    
    fixtures = client.get_h2h("Manchester City", "Arsenal", last_n=5)
    
    print(f"  NormalizedFixture results: {len(fixtures)}")
    for f in fixtures:
        print(f"    {f.home_team} vs {f.away_team} | {f.competition} | {f.kickoff}")
    
    print(f"  Budget: {client.get_budget_status()}")
    return fixtures


if __name__ == "__main__":
    print("=" * 60)
    print("GOOGLE SPORTS CLIENT — LIVE INTEGRATION TEST")
    print("Uses cached data where available (48h TTL)")
    print("=" * 60)
    
    # Run all tests
    results = {}
    results["football"] = test_football()
    results["tennis"] = test_tennis()
    results["hockey"] = test_hockey()
    results["today"] = test_today_match()
    results["normalized"] = test_normalized_h2h()
    
    print(f"\n\n{'='*60}")
    print("ALL TESTS COMPLETE")
    print(f"{'='*60}")
    print(f"  Football H2H: {len(results['football'].h2h_matches)} matches")
    print(f"  Tennis H2H: {len(results['tennis'].h2h_matches)} matches")
    print(f"  Hockey H2H: {len(results['hockey'].h2h_matches)} matches")
    print(f"  Today's match goals: {len(results['today'].goal_scorers)} scorers")
    print(f"  Normalized fixtures: {len(results['normalized'])} entries")
