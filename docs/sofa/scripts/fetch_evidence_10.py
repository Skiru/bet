import os
from sofa_test import make_request

def dump_evidence(name, path, method="GET", params=None):
    print(f"Fetching {name} at {path}")
    status, data = make_request(path, method, params, save_as=f"{name}.json")
    print(f"Status: {status}")
    return data

dump_evidence("scheduled_events_no_date", "/sport/football/scheduled-events")
dump_evidence("scheduled_events_today", "/sport/football/events/today")
dump_evidence("sport_football_events", "/sport/football/events")
