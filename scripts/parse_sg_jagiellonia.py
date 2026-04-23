import re
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

with open(os.path.join(BASE, 'betting', 'data', 'sportsgambler_tips.html')) as f:
    html = f.read()

# Find Jagiellonia section
idx = html.find('Jagiellonia')
if idx >= 0:
    # Get a large block around Jagiellonia
    block = html[max(0, idx - 2000):idx + 5000]
    text = re.sub(r'<[^>]+>', '|', block)
    text = re.sub(r'\|+', '|', text)
    text = re.sub(r'\s+', ' ', text).strip()
    print('=== SPORTSGAMBLER: Jagiellonia vs Gornik ===')
    # Print in chunks
    for i in range(0, min(len(text), 2000), 200):
        print(text[i:i + 200])
    print()

# Also search for structured prediction data (JSON-LD)
import json
scripts = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL)
for s in scripts:
    try:
        data = json.loads(s)
        if isinstance(data, dict) and 'itemListElement' in data:
            for item in data.get('itemListElement', []):
                if isinstance(item, dict) and 'item' in item:
                    desc = item['item'].get('description', '')
                    name = item['item'].get('name', '')
                    if 'Jagiellonia' in name or 'Jagiellonia' in desc:
                        print('JSON-LD prediction: {} — {}'.format(name, desc))
    except Exception:
        pass

# Find all match predictions
predictions = re.findall(r'"description"\s*:\s*"Expert prediction:\s*([^"]+)"', html[:100000])
print('All expert predictions (first 20):')
for p in predictions[:20]:
    print('  - {}'.format(p))