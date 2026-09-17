import os
from sofa_test import make_request

def dump_evidence(name, path, method="GET", params=None):
    print(f"Fetching {name} at {path}")
    status, data = make_request(path, method, params, save_as=f"{name}.json")
    print(f"Status: {status}")
    return data

dump_evidence("team_2829_events_last_10", "/team/2829/events/last/10")
dump_evidence("team_2829_events_last_50", "/team/2829/events/last/50")
