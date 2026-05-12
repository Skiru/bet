import sys
from bet.api_clients.unified import UnifiedAPIClient

def test_unified_client():
    client = UnifiedAPIClient()
    print("Testing UnifiedAPIClient initialization...")
    print("Clients loaded:", [c.api_name for c in client.clients])
    
    print("\nFetching fixtures for today...")
    fixtures = client.get_fixtures("2026-05-12", sport="football")
    print(f"Found {len(fixtures)} fixtures!")
    
    if fixtures:
        first_event = fixtures[0]
        event_id = first_event.get("id")
        print(f"\nFetching stats for event {event_id}...")
        
        # Test Sofascore specific endpoint via unified if needed or direct
        stats = client.sofascore.get_fixture_stats(str(event_id))
        print(f"Stats length: {len(stats)}")

test_unified_client()
