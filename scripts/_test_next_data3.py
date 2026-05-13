"""Extract events from __NEXT_DATA__ seoContent + check RSC chunks."""
import json, re

d = json.load(open("betting/data/_next_data_dump.json"))

# 1. Check seoContent for event data
seo = d["props"]["pageProps"]["initialProps"].get("seoContent", {})
print("seoContent keys:", list(seo.keys()))
for k, v in seo.items():
    if isinstance(v, str):
        print(f"  {k}: string ({len(v)} chars)")
    elif isinstance(v, list):
        print(f"  {k}: list ({len(v)} items)")
        if v and isinstance(v[0], dict):
            print(f"    Sample: {json.dumps(v[0], indent=2)[:300]}")
    elif isinstance(v, dict):
        print(f"  {k}: dict ({len(v)} keys) — {list(v.keys())[:8]}")

# 2. Extract all match URLs and event IDs from the full JSON
full_text = json.dumps(d)

# Find all Sofascore event IDs
event_ids = re.findall(r'#id:(\d+)', full_text)
print(f"\nFound {len(event_ids)} event IDs in __NEXT_DATA__")
print(f"  Sample: {event_ids[:10]}")

# Find all match URLs
match_urls = re.findall(r'/(?:football|basketball|tennis|ice-hockey|volleyball)/match/[^"]+', full_text)
print(f"\nFound {len(match_urls)} match URLs")

# Group by sport
sports = {}
for url in match_urls:
    sport = url.split("/")[1]
    if sport not in sports:
        sports[sport] = []
    sports[sport].append(url)

for sport, urls in sports.items():
    print(f"\n  {sport}: {len(urls)} matches")
    for u in urls[:3]:
        # Extract team names from URL
        match_part = u.split("/match/")[1].split("#")[0] if "/match/" in u else u
        eid = re.search(r'#id:(\d+)', u)
        eid_str = eid.group(1) if eid else "no-id"
        print(f"    {match_part} (ID: {eid_str})")

# 3. Check footerEntities (another source of links)
footer = d["props"].get("footerEntities", {})
if footer:
    print(f"\nfooterEntities keys: {list(footer.keys())}")
    for k, v in footer.items():
        if isinstance(v, list):
            print(f"  {k}: {len(v)} items")
            if v and isinstance(v[0], dict):
                print(f"    Sample: {json.dumps(v[0])[:200]}")

# 4. Quick search for scheduled-events or event array patterns
for pattern in ['"events":', '"scheduledEvents":', '"fixtures":', '"matches":']:
    count = full_text.count(pattern)
    if count > 0:
        idx = full_text.index(pattern)
        print(f"\n'{pattern}' found {count}x, first at pos {idx}: ...{full_text[idx:idx+200]}...")
