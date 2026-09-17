import os
from sofa_test import make_request

def dump_evidence(name, path, method="GET", params=None):
    print(f"Fetching {name} at {path}")
    status, data = make_request(path, method, params, save_as=f"{name}.json")
    print(f"Status: {status}")
    return data

dump_evidence("error_event_not_found", "/event/999999999")
dump_evidence("error_team_not_found", "/team/999999999/events/last/0")
dump_evidence("error_search_empty", "/search/all?q=")
