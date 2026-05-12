import json
import traceback

def run():
    print("=== INTERNACIONAL S3 DEEP STATS ===")
    try:
        with open('betting/data/2026-05-12_s3_deep_stats.json', 'r') as f:
            data = json.load(f)
            
        if isinstance(data, dict):
            if 'candidates' in data:
                items = data['candidates']
            else:
                items = data.values()
        else:
            items = data
            
        for v in items:
            if isinstance(v, dict) and str(v.get('fixture_id')) == '188430':
                print("Found match!")
                markets = v.get('markets', {})
                for m_key, m_val in markets.items():
                    if 'Corner' in m_key or 'Card' in m_key or 'Foul' in m_key:
                        print(f"\n--- {m_key} ---")
                        print(json.dumps(m_val, indent=2))

        
    except Exception as e:
        print(e)
        traceback.print_exc()

run()
