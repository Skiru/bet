import json
from datetime import datetime
from pathlib import Path

from bet.sofa.cache import SofaCache
from bet.sofa.config import SofaConfig
from bet.sofa.resolve import SofaResolver

class MockClient:
    def __init__(self, data):
        self.data = data
        
    def search(self, q: str):
        q = q.lower()
        if "inter miami" in q:
            return {"results": [{"type": "team", "entity": {"id": 101, "name": "Inter Miami CF", "sport": {"slug": "football"}}}]}
        elif "china w" in q or "chiny" in q:
            return {"results": [{"type": "team", "entity": {"id": 102, "name": "China W", "sport": {"slug": "football"}}}]}
        elif "france u20" in q or "francja" in q:
            return {"results": [{"type": "team", "entity": {"id": 103, "name": "France U20", "sport": {"slug": "football"}}}]}
        elif "real madrid" in q and "castilla" in q or "real madrid (r)" in q:
            return {"results": [{"type": "team", "entity": {"id": 104, "name": "Real Madrid Castilla", "sport": {"slug": "football"}}}]}
        elif "real madrid" in q:
            return {"results": [{"type": "team", "entity": {"id": 105, "name": "Real Madrid", "sport": {"slug": "football"}}}]}
        return {"results": []}

    def entity_events(self, entity_id: int, kind: str, page: int):
        if page > 0:
            return {"events": [], "hasNextPage": False}
        events = []
        if entity_id == 101:
            events.append({"id": 16640655, "startTimestamp": int(datetime(2026, 9, 17, 0, 0, 0).timestamp()), "homeTeam": {"name": "Inter Miami CF", "id": 101}, "awayTeam": {"name": "Cruz Azul", "id": 201}, "tournament": {"name": "Campeones Cup"}})
        elif entity_id == 102:
            events.append({"id": 999999, "startTimestamp": int(datetime(2026, 9, 17, 12, 0, 0).timestamp()), "homeTeam": {"name": "China W", "id": 102}, "awayTeam": {"name": "Vietnam W", "id": 202}, "tournament": {"name": "Friendly"}})
        elif entity_id == 103:
            events.append({"id": 888888, "startTimestamp": int(datetime(2026, 9, 17, 15, 0, 0).timestamp()), "homeTeam": {"name": "France U20", "id": 103}, "awayTeam": {"name": "Brazil U20", "id": 203}, "tournament": {"name": "World Cup U20"}})
        elif entity_id == 104:
            events.append({"id": 777777, "startTimestamp": int(datetime(2026, 9, 17, 18, 0, 0).timestamp()), "homeTeam": {"name": "Real Madrid Castilla", "id": 104}, "awayTeam": {"name": "Barcelona Atlètic", "id": 204}, "tournament": {"name": "Primera RFEF"}})
        elif entity_id == 105:
            events.append({"id": 15345277, "startTimestamp": int(datetime(2026, 9, 17, 20, 0, 0).timestamp()), "homeTeam": {"name": "Real Madrid", "id": 105}, "awayTeam": {"name": "Barcelona", "id": 205}, "tournament": {"name": "LaLiga"}})
            
        return {"events": events, "hasNextPage": False}
        
    def event(self, id: int):
        return {"event": {"id": id, "startTimestamp": 0, "tournament": {}, "homeTeam": {}, "awayTeam": {}}}

def test_resolve_golden(tmp_path):
    config = SofaConfig(db_path=str(tmp_path / "test.db"))
    from bet.sofa.db import migrate
    migrate(config.db_path)
    
    cache = SofaCache(config)
    
    with open("tests/fixtures/sofascore/golden_matches.json") as f:
        golden = json.load(f)
        
    client = MockClient(golden)
    resolver = SofaResolver(config, client, cache)
    
    correct = 0
    false_matches = 0
    total_matches_expected = 0
    
    for g in golden:
        parts = g["superbet_match_name"].split("·")
        side_a, side_b = parts[0], parts[1]
        kickoff = datetime.fromisoformat(g["kickoff_utc"].replace("Z", "+00:00"))
        
        entity_id, event, is_ambig = resolver.resolve_entity(g["sport"], side_a, kickoff, side_b)
        if not event:
            entity_id, event, is_ambig = resolver.resolve_entity(g["sport"], side_b, kickoff, side_a)
            
        if g["expected"] == "match":
            total_matches_expected += 1
            if event and event["id"] == g["expected_sofascore_id"]:
                correct += 1
            elif event:
                false_matches += 1
        else:
            if event:
                false_matches += 1
                
    precision = correct / (correct + false_matches) if correct + false_matches > 0 else 0.0
    assert precision >= 0.98, f"Precision {precision} < 0.98"
    assert false_matches <= 1, "More than 1 false match"
