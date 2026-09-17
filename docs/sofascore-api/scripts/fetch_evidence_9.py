import os
from sofa_test import make_request

def dump_evidence(name, path, method="GET", params=None):
    print(f"Fetching {name} at {path}")
    status, data = make_request(path, method, params, save_as=f"{name}.json")
    print(f"Status: {status}")
    return data

dump_evidence("tournament_17_events_next_0", "/unique-tournament/17/events/next/0")
dump_evidence("tournament_17_events_last_0", "/unique-tournament/17/events/last/0")
dump_evidence("tournament_17_season_96668_events", "/unique-tournament/17/season/96668/events")
