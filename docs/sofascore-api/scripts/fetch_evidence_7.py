import os
from sofa_test import make_request

def dump_evidence(name, path, method="GET", params=None):
    print(f"Fetching {name} at {path}")
    status, data = make_request(path, method, params, save_as=f"{name}.json")
    print(f"Status: {status}")
    return data

dump_evidence("search_league_liga_profesional", "/search/all?q=liga profesional")
dump_evidence("search_league_brazil_serie_b2", "/search/all?q=brasileirao serie b")
# find team for player
dump_evidence("search_player_haaland", "/search/all?q=haaland")
