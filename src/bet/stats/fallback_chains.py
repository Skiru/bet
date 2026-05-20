"""Canonical provider policy for match stats and derived team form.

This module is the single source of truth for per-sport match-stat fallback
chains used by enrichment and cache-building flows.

Policy:
- Flashscore is not a canonical per-match stats provider.
- Flashscore remains allowed only for lightweight search/results-page use cases
    handled outside these chains.
- Settlement may keep a temporary Flashscore HTML exception, but that exception
    is isolated outside this module.
"""

FALLBACK_CHAINS: dict[str, list[str]] = {
    "football": ["espn-football", "api-football", "football-data-org", "understat", "google-sports", "serpapi"],
    "basketball": ["espn-basketball", "nba-api", "api-basketball", "sofascore", "google-sports", "serpapi"],
    "hockey": ["espn-hockey", "api-hockey", "scrapernhl", "moneypuck", "sofascore", "google-sports", "serpapi"],
    "tennis": ["tennis-abstract", "sackmann", "espn-tennis", "google-sports", "serpapi"],
    "volleyball": ["espn-volleyball", "api-volleyball", "google-sports", "serpapi"],
}

RICH_COMPLETION_POLICY: dict[str, dict[str, list[str] | str]] = {
    "basketball": {
        "required_rich_keys": [
            "rebounds",
            "assists",
            "steals",
            "blocks",
            "turnovers",
            "fouls",
            "fg_pct",
            "three_pct",
            "ft_pct",
            "points_in_paint",
            "fast_break_points",
        ],
        "canonical_source": "api-basketball",
        "supporting_sources": ["nba-api", "espn-basketball"],
        "aggregate_only_sources": [],
    },
    "hockey": {
        "required_rich_keys": [
            "shots",
            "hits",
            "blocks",
            "pim",
            "powerplay_goals",
            "faceoff_pct",
        ],
        "canonical_source": "api-hockey",
        "supporting_sources": ["espn-hockey"],
        "aggregate_only_sources": ["moneypuck", "scrapernhl"],
    },
    "tennis": {
        "baseline_keys": [
            "sets_won",
            "total_sets",
            "games_won",
            "total_games",
        ],
        "required_rich_keys": [
            "aces",
            "double_faults",
            "first_serve_pct",
            "first_serve_win_pct",
            "second_serve_win_pct",
            "break_points_saved_pct",
            "hold_pct",
            "break_pct",
        ],
        "baseline_sources": ["espn-tennis-enriched"],
        "canonical_source": "tennis-abstract",
        "supporting_sources": ["sackmann"],
        "aggregate_only_sources": ["sackmann-season-aggregate"],
    },
    "volleyball": {
        "required_rich_keys": [
            "aces",
            "blocks",
            "hitting_pct",
            "points",
        ],
        "canonical_source": "api-volleyball",
        "supporting_sources": ["espn-volleyball"],
        "aggregate_only_sources": ["volleybox"],
    },
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
           "shots", "hits", "blocks", "pim",
        "powerplay_goals", "faceoffs_won", "faceoff_pct",
        "takeaways", "giveaways",
    ],
    "tennis": [
        "aces", "double_faults", "first_serve_pct",
        "first_serve_win_pct", "second_serve_win_pct",
        "break_points_saved_pct", "hold_pct", "break_pct",
        "sets_won", "total_sets", "games_won", "total_games",
    ],
    "volleyball": [
        "kills", "aces", "blocks", "digs", "assists",
        "hitting_pct", "points",
    ],
}
