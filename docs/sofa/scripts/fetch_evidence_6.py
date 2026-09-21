import os
from sofa_test import make_request

def dump_evidence(name, path, method="GET", params=None):
    print(f"Fetching {name} at {path}")
    status, data = make_request(path, method, params, save_as=f"{name}.json")
    print(f"Status: {status}")
    return data

leagues = [
    "premier league",
    "ekstraklasa",
    "super lig",
    "liga mx",
    "k league 1",
    "superettan",
    "champions league",
    "fa cup",
    "j1 league",
    "saudi pro league",
    "brazil serie b",
    "superliga argentina" # to be precise
]

for league in leagues:
    safe_name = league.replace(" ", "_")
    dump_evidence(f"search_league_{safe_name}", f"/search/all?q={league}")
