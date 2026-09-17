import json
import glob
from bet.sofa.metrics import extract_flat_statistics, extract_metric, GapReason, FOOTBALL_METRICS, TENNIS_METRICS

def test_t11_no_fabrication():
    # Only event_15345277_statistics and event_16363633_statistics and event_16416342_statistics
    files = glob.glob("tests/fixtures/sofascore/event_*_statistics.json")
    assert len(files) > 0
    
    for f in files:
        with open(f) as fh:
            stats = json.load(fh)
            
        flat = extract_flat_statistics(stats.get("response", {}).get("body", {}))
        
        # Decide if tennis or football
        # event_15345277 is tennis
        # 16363633 is football
        sport = "tennis" if "15345277" in f else "football"
        metrics = TENNIS_METRICS if sport == "tennis" else FOOTBALL_METRICS
        
        # Check all metrics
        for metric in metrics:
            val = extract_metric(metric, sport, flat, None, {}, True)
            
            sofascore_key = metrics[metric]["sofascore"]
            
            # if we have no listing event, listing metrics should be STAT_KEY_ABSENT
            if sofascore_key in ["goals_from_listing", "goals_1h_from_listing", "goals_2h_from_listing", "sets_from_listing"]:
                assert val == GapReason.STAT_KEY_ABSENT
                continue
                
            if sofascore_key == "cards_points_from_incidents":
                assert val == GapReason.NO_INCIDENTS
                continue
                
            if sofascore_key == "expectedGoals":
                assert val == GapReason.STAT_KEY_ABSENT
                continue
                
            # For others, if it's missing in flat, it should be GapReason.STAT_KEY_ABSENT
            # If it's present, it should be float. But it shouldn't be 0.0 magically fabricated if key is missing.
            is_present = "ALL" in flat and sofascore_key in flat["ALL"]
            
            if not is_present:
                assert val == GapReason.STAT_KEY_ABSENT
            else:
                assert isinstance(val, float)
