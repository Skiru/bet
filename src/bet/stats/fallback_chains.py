"""Fallback chains per sport — ordered list of API clients to try for stats.

Used by data_enrichment_agent.py and fetch_api_stats.py to determine which
API sources to query for each sport, in priority order.
"""

FALLBACK_CHAINS: dict[str, list[str]] = {
    "football": ["espn-football", "api-football", "football-data-org", "understat", "google-sports", "serpapi"],
    "basketball": ["espn-basketball", "nba-api", "api-basketball", "google-sports", "serpapi"],
    "hockey": ["espn-hockey", "api-hockey", "google-sports", "serpapi"],
    "tennis": ["espn-tennis", "google-sports", "serpapi"],
    "volleyball": ["espn-volleyball", "api-volleyball", "google-sports", "serpapi"],
}

# Tier 1 sports: all get equal enrichment priority
TIER_1_SPORTS = {"football", "volleyball", "basketball", "tennis", "hockey"}

# Expected stat keys per sport — used to audit extraction completeness
EXPECTED_STATS_PER_SPORT: dict[str, list[str]] = {
    "football": [
        "corners", "fouls", "yellow_cards", "red_cards", "shots",
        "shots_on_target", "possession", "offsides", "saves",
        "total_passes", "pass_accuracy",
    ],
    "basketball": [
        "rebounds", "assists", "steals", "blocks", "turnovers",
        "fouls", "fg_pct", "three_pct", "ft_pct",
        "points_in_paint", "fast_break_points",
    ],
    "hockey": [
        "shots", "hits", "blocks", "penalties", "pim",
        "powerplay_goals", "faceoffs_won", "faceoff_pct",
        "takeaways", "giveaways",
    ],
    "tennis": [
        "aces", "double_faults", "first_serve_pct",
        "break_points_won",
    ],
    "volleyball": [
        "kills", "aces", "blocks", "digs", "assists",
        "hitting_pct", "points",
    ],
}
