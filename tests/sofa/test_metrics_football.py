import json
from bet.sofa.metrics import extract_flat_statistics, check_identities, extract_metric
from bet.sofa.contracts import GapReason

def test_t08a_shots_identity():
    with open("tests/fixtures/sofascore/event_16363633_statistics.json") as f:
        stats = json.load(f)
        
    flat = extract_flat_statistics(stats.get("response", {}).get("body", {}))
    # home = Brighton, away = Arsenal
    assert flat["ALL"]["shotsOnGoal"][0] == 6 # Arsenal shots on target
    assert flat["ALL"]["shotsOffGoal"][0] == 6
    assert flat["ALL"]["blockedScoringAttempt"][0] == 8
    assert flat["ALL"]["totalShotsOnGoal"][0] == 20
    
    res = check_identities(flat, None, {}, "football")
    assert res is None # No inconsistency
    
    val = extract_metric("shots_on_target_for", "football", flat, None, {}, True)
    assert val == 6.0
    
    val_tot = extract_metric("shots_for", "football", flat, None, {}, True)
    assert val_tot == 20.0
    
def test_t08b_flat_search():
    # offsides is in Attack, not Match overview. Should be found.
    with open("tests/fixtures/sofascore/event_16363633_statistics.json") as f:
        stats = json.load(f)
    flat = extract_flat_statistics(stats.get("response", {}).get("body", {}))
    assert "offsides" in flat["ALL"]
    
def test_t08c_goals_from_listing():
    listing_event = {
        "homeScore": {"current": 2, "period1": 1, "period2": 1, "normaltime": 2},
        "awayScore": {"current": 1, "period1": 0, "period2": 1, "normaltime": 1}
    }
    # No statistics provided
    res = extract_metric("goals_total", "football", {}, None, listing_event, True)
    assert res == 3.0
    
    res = extract_metric("goals_1h_for", "football", {}, None, listing_event, True)
    assert res == 1.0

