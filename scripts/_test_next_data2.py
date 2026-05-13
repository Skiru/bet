"""Explore __NEXT_DATA__ initialState deeply — look for events data."""
import json

d = json.load(open("betting/data/_next_data_dump.json"))

# Check initialState in pageProps
state = d["props"]["pageProps"]["initialState"]
print("pageProps.initialState keys:", list(state.keys()))
for k, v in state.items():
    if isinstance(v, dict):
        print(f"  {k}: dict({len(v)} keys) — {list(v.keys())[:8]}")
    elif isinstance(v, list):
        print(f"  {k}: list({len(v)} items)")
    else:
        print(f"  {k}: {type(v).__name__} = {str(v)[:60]}")

# Check props-level initialState
state2 = d["props"].get("initialState")
if state2:
    print("\nprops.initialState keys:", list(state2.keys()))
    for k, v in state2.items():
        if isinstance(v, dict):
            sub_keys = list(v.keys())[:8]
            print(f"  {k}: dict({len(v)} keys) — {sub_keys}")
            # Go deeper for any dict that looks like it could have events
            for sk in v:
                sv = v[sk]
                if isinstance(sv, dict):
                    deep_keys = list(sv.keys())[:6]
                    print(f"    {sk}: dict({len(sv)} keys) — {deep_keys}")
                    # One more level
                    for dk in sv:
                        dv = sv[dk]
                        if isinstance(dv, dict) and "events" in dv:
                            print(f"      FOUND EVENTS in {k}.{sk}.{dk}!")
                            print(f"      Count: {len(dv['events'])}")
                        elif isinstance(dv, list) and len(dv) > 5:
                            print(f"      {dk}: list({len(dv)} items)")
                            if dv and isinstance(dv[0], dict):
                                print(f"        Sample keys: {list(dv[0].keys())[:8]}")
                elif isinstance(sv, list) and len(sv) > 0:
                    print(f"    {sk}: list({len(sv)} items)")
        elif isinstance(v, list):
            print(f"  {k}: list({len(v)} items)")
        else:
            print(f"  {k}: {type(v).__name__} = {str(v)[:60]}")

# Search recursively for "events" key
def find_events(obj, path=""):
    if isinstance(obj, dict):
        if "events" in obj and isinstance(obj["events"], list) and len(obj["events"]) > 2:
            print(f"\nFOUND events at {path}.events — count: {len(obj['events'])}")
            if obj["events"]:
                print(f"  Sample: {json.dumps(obj['events'][0], indent=2)[:500]}")
            return True
        for k, v in obj.items():
            find_events(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, item in enumerate(obj[:5]):
            find_events(item, f"{path}[{i}]")

print("\n\nDEEP SEARCH for 'events' key:")
find_events(d)

# Also search for team names to find where event data hides
full_text = json.dumps(d)
# Check if any team name appears
for team in ["Barcelona", "Real Madrid", "Liverpool", "Manchester", "Bayern"]:
    if team in full_text:
        # Find context
        idx = full_text.index(team)
        print(f"\nFound '{team}' at position {idx}: ...{full_text[max(0,idx-100):idx+100]}...")
        break
else:
    print("\nNo major team names found in __NEXT_DATA__")
    # Check what's there
    print(f"Total JSON size: {len(full_text)} chars")
    print(f"'event' occurrences: {full_text.lower().count('event')}")
    print(f"'match' occurrences: {full_text.lower().count('match')}")
    print(f"'team' occurrences: {full_text.lower().count('team')}")
