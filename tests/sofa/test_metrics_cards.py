from bet.sofa.metrics import calculate_cards_points, GapReason

def test_t10_cards_points():
    # Brak payloadu
    assert calculate_cards_points(None) == GapReason.NO_INCIDENTS
    
    # rescinded
    incidents_rescinded = {
        "incidents": [
            {"incidentType": "card", "incidentClass": "yellow", "rescinded": True, "isHome": True}
        ]
    }
    assert calculate_cards_points(incidents_rescinded) == (0.0, 0.0)
    
    # second yellow points (+1 for first, +2 for second) -> Total 3
    import json
    with open("tests/fixtures/sofascore/incidents_second_yellow.json") as f:
        inc = json.load(f)
        
    pts = calculate_cards_points(inc)
    # home should be 3
    assert pts == (3.0, 0.0)
    
    # normal test
    incidents_mixed = {
        "incidents": [
            {"incidentType": "card", "incidentClass": "yellow", "isHome": True},
            {"incidentType": "card", "incidentClass": "red", "isHome": False},
            {"incidentType": "card", "incidentClass": "yellow", "isHome": False},
        ]
    }
    pts_mixed = calculate_cards_points(incidents_mixed)
    assert pts_mixed == (1.0, 3.0)

