import json
import traceback

def run():
    print("=== INTERNACIONAL IN MARKET MATRIX ===")
    try:
        with open('betting/data/2026-05-12_s7_gate_results.json', 'r') as f:
            data = json.load(f)
            
        found = False
        candidates = data.get('gate_results', {}).get('approved', []) + data.get('gate_results', {}).get('extended_pool', [])

        for c in candidates:
            home = c.get('home_team', '').lower()
            away = c.get('away_team', '').lower()
            event = c.get('event', '').lower()
            
            if 'internacional' in home or 'internacional' in away or 'internacional' in event:
                if 'athletic' in away or 'athletic' in home or 'athletic' in event:
                    found = True
                    print(f"\nMatch Found: {c.get('event') or f'{home} vs {away}'}")
                    print(json.dumps(c.get('best_market', {}), indent=2))
                    
                    # Alternatively read from deep stats again by exact event key from here
                    print("Fixture ID:", c.get('fixture_id'))
                    print("Home:", c.get('home_team'))
                    print("Away:", c.get('away_team'))
                        
        if not found:
            print("Could not find Internacional vs Athletic in market matrix.")
            
    except Exception as e:
        print(f"Error reading stats: {e}")
        traceback.print_exc()

if __name__ == '__main__':
    run()
