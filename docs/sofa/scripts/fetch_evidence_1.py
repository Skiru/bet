import os
import json
from sofa_test import make_request

EVIDENCE_DIR = "docs/sofa/evidence"
os.makedirs(EVIDENCE_DIR, exist_ok=True)

def dump_evidence(name, path, method="GET", params=None):
    print(f"Fetching {name} at {path}")
    status, data = make_request(path, method, params, save_as=f"{name}.json")
    print(f"Status: {status}")
    return data

# Discovery checks
dump_evidence("discovery_football_scheduled_events_date", "/sport/football/scheduled-events/2026-09-17")
dump_evidence("discovery_football_events_live", "/sport/football/events/live")
dump_evidence("discovery_tennis_scheduled_tournaments", "/sport/tennis/scheduled-tournaments/2026-09-17/page/0")
dump_evidence("discovery_tennis_events_live", "/sport/tennis/events/live")
dump_evidence("discovery_unique_tournament_17_seasons", "/unique-tournament/17/seasons")
dump_evidence("discovery_unique_tournament_17_season_65275_rounds", "/unique-tournament/17/season/65275/rounds")
dump_evidence("discovery_unique_tournament_17_season_65275_events_round_1", "/unique-tournament/17/season/65275/events/round/1")

# Team discovery pagination
dump_evidence("team_8473_events_next_0", "/team/8473/events/next/0")
dump_evidence("team_8473_events_next_1", "/team/8473/events/next/1")
dump_evidence("team_8473_events_last_0", "/team/8473/events/last/0")
dump_evidence("team_8473_events_last_1", "/team/8473/events/last/1")

# Search
dump_evidence("search_all_real_madrid", "/search/all?q=Real Madrid")
dump_evidence("search_team_real_madrid", "/search/team?q=Real Madrid")

# Let's run this first to get some data and base ids
