import json
from bet.sofa.resolve import resolve_league

class MockClient:
    def __init__(self, data):
        self.data = data
        
    def search(self, q: str):
        q = q.lower()
        if q in self.data:
            # Reconstruct the search/all response format
            results = []
            for item in self.data[q]:
                results.append({
                    "type": "uniqueTournament",
                    "entity": {
                        "id": item["id"],
                        "name": item["name"],
                        "category": {"name": item["category"]}
                    }
                })
            return {"results": results}
        return {"results": []}

def test_resolve_league_disambiguation():
    with open("docs/sofascore-api/evidence/league_search_disambiguation.json") as f:
        data = json.load(f)
        
    client = MockClient(data)
    
    # Check that we pick the correct one by country, NOT results[0]
    
    # "championship" -> England (results[1])
    assert resolve_league("championship", "England", client) == 18
    # "championship" -> World (results[0])
    assert resolve_league("championship", "World", client) == 16
    
    # "brazil serie a" -> Brazil (results[0])
    assert resolve_league("brazil serie a", "Brazil", client) == 325
    
    # "eredivisie" -> Netherlands
    assert resolve_league("eredivisie", "Netherlands", client) == 37
    
    # "superliga" -> Serbia (results[2])
    assert resolve_league("superliga", "Serbia", client) == 210

