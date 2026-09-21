import os
from sofa_test import make_request

def dump_evidence(name, path, method="GET", params=None):
    print(f"Fetching {name} at {path}")
    status, data = make_request(path, method, params, save_as=f"{name}.json")
    print(f"Status: {status}")
    return data

dump_evidence("team_17_tournament_17_season_96668_stats", "/team/17/unique-tournament/17/season/96668/statistics/overall")
dump_evidence("player_839956_tournament_17_season_96668_stats", "/player/839956/unique-tournament/17/season/96668/statistics/overall")
# see what other stats there are for players
dump_evidence("player_839956_statistics_seasons", "/player/839956/statistics/seasons")
