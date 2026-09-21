import os
from sofa_test import make_request

def dump_evidence(name, path, method="GET", params=None):
    print(f"Fetching {name} at {path}")
    status, data = make_request(path, method, params, save_as=f"{name}.json")
    print(f"Status: {status}")
    return data

dump_evidence("event_15345277_details", "/event/15345277")
dump_evidence("event_15345277_statistics", "/event/15345277/statistics")
dump_evidence("event_15345277_point_by_point", "/event/15345277/point-by-point")
dump_evidence("event_15345277_tennis_power", "/event/15345277/tennis-power")
dump_evidence("event_15345277_incidents", "/event/15345277/incidents")
dump_evidence("event_15345277_odds", "/event/15345277/odds/1/all")
