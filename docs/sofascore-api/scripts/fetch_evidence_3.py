import os
from sofa_test import make_request

EVIDENCE_DIR = "docs/sofascore-api/evidence"

def dump_evidence(name, path, method="GET", params=None):
    print(f"Fetching {name} at {path}")
    status, data = make_request(path, method, params, save_as=f"{name}.json")
    print(f"Status: {status}")
    return data

# Event details
dump_evidence("event_16363633_details", "/event/16363633")
dump_evidence("event_16363633_statistics", "/event/16363633/statistics")
dump_evidence("event_16363633_lineups", "/event/16363633/lineups")
dump_evidence("event_16363633_incidents", "/event/16363633/incidents")
dump_evidence("event_16363633_graph", "/event/16363633/graph")
dump_evidence("event_16363633_managers", "/event/16363633/managers")
dump_evidence("event_16363633_odds", "/event/16363633/odds/1/all")
dump_evidence("event_16363633_odds_providers", "/event/16363633/providers/odds")

# Category tournaments
dump_evidence("category_1_tournaments", "/category/1/unique-tournaments")
