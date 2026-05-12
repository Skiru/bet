import logging
from bet.api_clients.unified import UnifiedAPIClient

logging.basicConfig(level=logging.INFO)

def test_unified_client():
    client = UnifiedAPIClient()
    print("Testing UnifiedAPIClient initialization...")
    print("Clients loaded:", [c.api_name for c in client.clients])
    
    print("\nFetching fixtures for today...")
    fixtures = client.get_fixtures("2026-05-12", sport="football")
    print(f"Found {len(fixtures)} fixtures!")
    
    if fixtures:
        print("\nStructure of first fixture:")
        print(fixtures[0])

if __name__ == "__main__":
    test_unified_client()