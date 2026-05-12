import json
import traceback

def run():
    print("=== INTERNACIONAL ALTERNATIVE MARKETS ===")
    try:
        with open('betting/data/2026-05-12_s3_deep_stats.json', 'r') as f:
            data = json.load(f)
            
        found = False
        for k, v in data.items():
            k_lower = k.lower()
            if 'internacional' in k_lower and 'athletic' in k_lower:
                found = True
                print(f"Match: {k}")
                markets = v.get('markets', {})
                
                # Check Corners
                corners = markets.get('Corners Total O/U')
                if corners:
                    print("\n--- Corners Total O/U ---")
                    print(json.dumps(corners, indent=2))
                else:
                    print("\n--- Corners Total O/U --- Not found")
                    
                # Check Cards
                cards = markets.get('Cards Total O/U')
                if cards:
                    print("\n--- Cards Total O/U ---")
                    print(json.dumps(cards, indent=2))
                else:
                    print("\n--- Cards Total O/U --- Not found")
                
                # Check Team specific Corners/Cards
                for m_key, m_val in markets.items():
                    if 'Corners O/U' in m_key and m_key != 'Corners Total O/U':
                        print(f"\n--- {m_key} ---")
                        print(json.dumps(m_val, indent=2))
                    if 'Cards O/U' in m_key and m_key != 'Cards Total O/U':
                        print(f"\n--- {m_key} ---")
                        print(json.dumps(m_val, indent=2))
                        
        if not found:
            print("Could not find Internacional vs Athletic in deep stats.")
            
    except Exception as e:
        print(f"Error reading stats: {e}")
        traceback.print_exc()

if __name__ == '__main__':
    run()
