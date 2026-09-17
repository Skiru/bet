import json
from datetime import datetime, timezone
from bet.sofa.cache import SofaCache
from bet.sofa.config import SofaConfig
from bet.sofa.resolve import SofaResolver
from bet.sofa.contracts import BoardFixture, Fixture, GapReason
from pathlib import Path
import sys

class MockClient:
    def search(self, q: str):
        q = q.lower()
        if "ambig" in q:
            return {"results": [
                {"type": "team", "entity": {"id": 1, "name": "Ambig 1", "sport": {"slug": "football"}}},
                {"type": "team", "entity": {"id": 2, "name": "Ambig 2", "sport": {"slug": "football"}}}
            ]}
        if "dedup" in q:
            return {"results": [
                {"type": "team", "entity": {"id": 3, "name": "Dedup Team", "sport": {"slug": "football"}}}
            ]}
        return {"results": []}

    def entity_events(self, entity_id: int, kind: str, page: int):
        if page > 0:
            return {"events": [], "hasNextPage": False}
        events = []
        if entity_id == 1:
            events.append({"id": 1001, "startTimestamp": int(datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc).timestamp()), "homeTeam": {"name": "Ambig 1"}, "awayTeam": {"name": "Opp"}})
        elif entity_id == 2:
            events.append({"id": 1002, "startTimestamp": int(datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc).timestamp()), "homeTeam": {"name": "Ambig 2"}, "awayTeam": {"name": "Opp"}})
        elif entity_id == 3:
            events.append({"id": 1003, "startTimestamp": int(datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc).timestamp()), "homeTeam": {"name": "Dedup Team"}, "awayTeam": {"name": "Opp"}})
        return {"events": events, "hasNextPage": False}
        
    def event(self, id: int):
        return {"event": {"id": id, "startTimestamp": 0, "tournament": {}, "homeTeam": {}, "awayTeam": {}}}

def test_resolve_ambiguous_and_dedup(tmp_path):
    config = SofaConfig(db_path=str(tmp_path / "test.db"))
    from bet.sofa.db import migrate
    migrate(config.db_path)
    
    cache = SofaCache(config)
    client = MockClient()
    resolver = SofaResolver(config, client, cache)
    
    # 1. Test ambiguous (2 candidates match the opponent in the time window)
    kickoff = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)
    entity_id, event, is_ambig = resolver.resolve_entity("football", "ambig", kickoff, "opp")
    assert event is None
    assert is_ambig is True
    
    # 2. Test dedup: If two BoardFixtures resolve to the same Sofascore ID, 
    # they should be merged into one Fixture with two superbet_event_ids in run_resolve logic.
    # We will simulate the loop from run_resolve
    from scripts.sofa.run_resolve import parse_fixture
    
    resolved_fixtures = {}
    bf1 = BoardFixture(superbet_event_id="sb1", sport="football", match_name="Dedup·Opp", side_a="Dedup", side_b="Opp", kickoff_utc=kickoff)
    bf2 = BoardFixture(superbet_event_id="sb2", sport="football", match_name="Dedup·Opp", side_a="Dedup", side_b="Opp", kickoff_utc=kickoff)
    
    for bf in [bf1, bf2]:
        eid, evt, is_ambig = resolver.resolve_entity(bf.sport, bf.side_a, bf.kickoff_utc, bf.side_b)
        sf_id = evt["id"]
        if sf_id in resolved_fixtures:
            resolved_fixtures[sf_id].superbet_event_ids.append(bf.superbet_event_id)
        else:
            resolved_fixtures[sf_id] = parse_fixture(evt, bf.sport, [bf.superbet_event_id], client)
            
    assert len(resolved_fixtures) == 1
    assert "sb1" in resolved_fixtures[1003].superbet_event_ids
    assert "sb2" in resolved_fixtures[1003].superbet_event_ids
