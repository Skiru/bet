"""Stat key validation — prevents cross-sport data contamination.

Defines allowed stat_keys per sport. Any enrichment write with an invalid
stat_key for the sport is rejected.
"""

from bet.stats.market_ranking import SPORT_STAT_KEYS

# Extended valid stats per sport (superset of SPORT_STAT_KEYS — includes 
# intermediate/raw keys that may appear in enrichment but aren't market-ranked)
VALID_STATS: dict[str, set[str]] = {
    "football": {
        "corners", "fouls", "yellow_cards", "red_cards",
        "shots", "shots_on_target", "shots_off_target", "possession",
        "ball_possession", "goals", "offsides", "saves",
        "tackles", "passes", "pass_accuracy", "game_total_goals",
    },
    "hockey": {
        "goals", "shots", "shots_on_goal", "powerplay_goals",
        "power_play_goals", "pim", "penalties_in_minutes",
        "hits", "blocks", "faceoff_pct", "faceoffs_won",
        "game_total_goals", "saves", "save_pct",
    },
    "volleyball": {
        "points", "total_points", "aces", "blocks", "hitting_pct",
        "attack_pct", "sets_won", "total_sets", "errors",
        "digs", "assists", "service_errors", "reception_pct",
        "points_per_set",
    },
    "basketball": {
        "points", "rebounds", "assists", "steals", "blocks",
        "turnovers", "fg_pct", "three_pct", "ft_pct",
        "fouls", "game_total_points", "2_pointers", "3_pointers",
        "free_throws", "points_in_paint", "fast_break_points",
    },
    "tennis": {
        "sets_won", "total_sets", "games_won", "total_games",
        "aces", "double_faults", "first_serve_pct",
        "first_serve_win_pct", "second_serve_win_pct",
        "break_points_saved_pct", "hold_pct", "break_pct",
        "ranking", "win_1st_serve", "break_points_won",
        "break_points_saved",
    },
    "cs2": {
        "kills", "deaths", "kd_ratio", "rating_2_0",
        "maps_played", "maps_won", "map_win_rate",
        "rounds_won_avg", "win_rate_l10", "roster_size",
        "headshot_pct", "adr",
    },
    "dota2": {
        "kills_avg", "deaths_avg", "duration_avg_min",
        "win_rate_l10", "hero_pool_size", "first_blood_rate",
        "tower_kills_avg", "roshan_kills_avg",
    },
    "valorant": {
        "maps_played", "maps_won", "map_win_rate",
        "win_rate_l10", "rounds_won_avg", "roster_size",
        "acs_avg", "kd_ratio",
    },
}


def is_valid_stat_key(sport: str, stat_key: str) -> bool:
    """Check if a stat_key is valid for the given sport.
    
    Returns True if the key is allowed, False if it would be contamination.
    """
    sport_lower = sport.lower()
    valid = VALID_STATS.get(sport_lower)
    if valid is None:
        # Unknown sport — allow anything
        return True
    return stat_key.lower() in valid


def get_valid_stats(sport: str) -> set[str]:
    """Get all valid stat keys for a sport."""
    return VALID_STATS.get(sport.lower(), set())


def filter_valid_stats(sport: str, stat_keys: list[str] | set[str]) -> list[str]:
    """Filter a list of stat keys to only those valid for the sport."""
    valid = VALID_STATS.get(sport.lower())
    if valid is None:
        return list(stat_keys)
    return [k for k in stat_keys if k.lower() in valid]


def detect_contamination(sport: str, stat_keys: list[str] | set[str]) -> list[str]:
    """Detect stat keys that don't belong to the given sport (contamination).
    
    Returns list of invalid keys.
    """
    valid = VALID_STATS.get(sport.lower())
    if valid is None:
        return []
    return [k for k in stat_keys if k.lower() not in valid]
