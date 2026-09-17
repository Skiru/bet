import json
from bet.sofa.metrics import extract_flat_statistics, extract_metric

def test_t09_tennis_metrics():
    with open("tests/fixtures/sofascore/event_15345277_statistics.json") as f:
        stats = json.load(f)
        
    flat = extract_flat_statistics(stats.get("response", {}).get("body", {}))
    
    # 5.7 details:
    # serviceGamesTotal 17 + 17 = 34
    # gamesWon 20 + 15 = 35
    
    games_home = flat["ALL"]["gamesWon"][0]
    games_away = flat["ALL"]["gamesWon"][1]
    assert games_home == 20
    assert games_away == 15
    
    games_total = extract_metric("games_total", "tennis", flat, None, {}, True)
    assert games_total == 35.0
    
    # aces
    # T09: "aces_total = suma obu stron (2+7=9), nie 2"
    aces_home = flat["ALL"]["aces"][0]
    aces_away = flat["ALL"]["aces"][1]
    # Check if they are 2 and 7
    assert aces_home + aces_away == 9.0
    
    aces_total = extract_metric("aces_total", "tennis", flat, None, {}, True)
    assert aces_total == 9.0
    
    # sets_total
    listing_event = {
        "homeScore": {"period1": 7, "period2": 6, "period3": 7},
        "awayScore": {"period1": 6, "period2": 4, "period3": 5}
    }
    sets_total = extract_metric("sets_total", "tennis", flat, None, listing_event, True)
    assert sets_total == 3.0
    
