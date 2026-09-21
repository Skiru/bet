import os
from sofa_test import make_request

EVIDENCE_DIR = "docs/sofa/evidence"
os.makedirs(EVIDENCE_DIR, exist_ok=True)

def dump_evidence(name, path, method="GET", params=None):
    print(f"Fetching {name} at {path}")
    status, data = make_request(path, method, params, save_as=f"{name}.json")
    print(f"Status: {status}")
    return data

# Current season rounds
dump_evidence("rounds_premier_league_26_27", "/unique-tournament/17/season/96668/rounds")
dump_evidence("events_premier_league_26_27_round_1", "/unique-tournament/17/season/96668/events/round/1")

# Team events
dump_evidence("team_2829_events_next_0", "/team/2829/events/next/0")
dump_evidence("team_2829_events_last_0", "/team/2829/events/last/0")

# Standings
dump_evidence("standings_premier_league_26_27", "/unique-tournament/17/season/96668/standings/total")

# Other discovery candidates
# Maybe /sport/football/events/date/2026-09-17 ?
dump_evidence("discovery_football_events_date", "/sport/football/events/date/2026-09-17")
dump_evidence("discovery_football_schedule", "/sport/football/events/schedule/2026-09-17")
dump_evidence("discovery_football_fixtures", "/sport/football/fixtures/2026-09-17")
dump_evidence("discovery_football_category_1", "/category/1/events")

# Categories search (to see if we can get all tournaments)
dump_evidence("categories_football", "/sport/football/categories")
