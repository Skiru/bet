"""Stat key validation — prevents cross-sport data contamination.

Defines allowed stat_keys per sport. Any enrichment write with an invalid
stat_key for the sport is rejected.
"""

# Extended valid stats per sport (superset of SPORT_STAT_KEYS — includes 
# intermediate/raw keys that may appear in enrichment but aren't market-ranked)
VALID_STATS: dict[str, set[str]] = {
    "football": {
        "corners", "fouls", "yellow_cards", "red_cards",
        "shots", "shots_on_target", "shots_off_target", "possession",
        "ball_possession", "goals", "offsides", "saves",
        "tackles", "passes", "pass_accuracy", "game_total_goals",
        # Home/away variants
        "goals_home", "goals_away", "goals_total", "yellow_cards_home", "yellow_cards_away",
        "shots_home", "shots_away", "shots_on_target_home", "shots_on_target_away",
        "shots_off_target_home", "shots_off_target_away", "red_cards_home", "red_cards_away",
        "possession_home", "possession_away", "offsides_home", "offsides_away",
        "saves_home", "saves_away", "tackles_home", "tackles_away",
        "corners_home", "corners_away", "fouls_home", "fouls_away",
        "interceptions_home", "interceptions_away", "clearances_home", "clearances_away",
        "blocked_shots_home", "blocked_shots_away",
        # Additional variants
        "accurate_passes_home", "accurate_passes_away", "total_passes_home", "total_passes_away",
        "total_clearances_home", "total_clearances_away", "tackles_won_home", "tackles_won_away",
        "tackle_accuracy_home", "tackle_accuracy_away", "shot_accuracy_home", "shot_accuracy_away",
        "penalty_goals_home", "penalty_goals_away", "penalty_attempts_home", "penalty_attempts_away",
        "pass_accuracy_home", "pass_accuracy_away", "long_balls_home", "long_balls_away",
    },
    "hockey": {
        "goals", "shots", "shots_on_goal", "powerplay_goals",
        "power_play_goals", "pim", "penalties_in_minutes",
        "hits", "blocks", "faceoff_pct", "faceoffs_won",
        "game_total_goals", "saves", "save_pct",
        # Home/away variants
        "goals_home", "goals_away", "shots_home", "shots_away",
        "blocks_home", "blocks_away", "hits_home", "hits_away",
        "takeaways_home", "takeaways_away",
        # Period variants
        "goals_p1", "goals_p2", "goals_p3",
        # Special variants
        "shorthanded_goals_home", "shorthanded_goals_away",
        "shootout_goals_home", "shootout_goals_away",
        "powerplay_goals_home", "powerplay_goals_away",
        "power_play_pct_home", "power_play_pct_away",
        "power_play_opportunities_home", "power_play_opportunities_away",
        "pim_home", "pim_away", "penalties_home", "penalties_away",
        # Additional variants
        "giveaways_home", "giveaways_away", "faceoffs_won_home", "faceoffs_won_away",
        "faceoff_pct_home", "faceoff_pct_away", "takeaways", "shorthanded_goals",
        "shootout_goals", "power_play_pct", "power_play_opportunities", "penalties",
        # Team record variants
        "home_wins", "away_wins", "draws",
    },
    "volleyball": {
        "points", "total_points", "aces", "blocks", "hitting_pct",
        "attack_pct", "sets_won", "total_sets", "errors",
        "digs", "assists", "service_errors", "reception_pct",
        "points_per_set",
        # Home/away variants
        "points_home", "points_away", "points_total",
        "total_points_home", "total_points_away",
        "sets_won_home", "sets_won_away", "sets_won_total",
        "total_points_total", "aces_home", "aces_away",
        # Team record variants
        "home_wins", "away_wins", "draws",
    },
    "basketball": {
        "points", "rebounds", "assists", "steals", "blocks",
        "turnovers", "fg_pct", "three_pct", "ft_pct",
        "fouls", "game_total_points", "2_pointers", "3_pointers",
        "free_throws", "points_in_paint", "fast_break_points",
        # Home/away variants
        "points_home", "points_away", "rebounds_home", "rebounds_away",
        "assists_home", "assists_away", "steals_home", "steals_away",
        "blocks_home", "blocks_away", "turnovers_home", "turnovers_away",
        "fouls_home", "fouls_away",
        # Period variants
        "points_p1", "points_p2", "points_p3", "points_p4",
        # Team record variants
        "home_wins", "away_wins", "draws", "turnover_points_home", "turnover_points_away",
        # Additional variants
        "three_pct_home", "three_pct_away", "technical_fouls_home", "technical_fouls_away",
        "points_in_paint_home", "points_in_paint_away", "offensive_rebounds_home", "offensive_rebounds_away",
        "largest_lead_home", "largest_lead_away", "ft_pct_home", "ft_pct_away",
        "flagrant_fouls_home", "flagrant_fouls_away", "fg_pct_home", "fg_pct_away",
        "fast_break_points_home", "fast_break_points_away", "defensive_rebounds_home", "defensive_rebounds_away",
    },
    "tennis": {
        "sets_won", "total_sets", "games_won", "total_games",
        "aces", "double_faults", "first_serve_pct",
        "first_serve_win_pct", "second_serve_win_pct",
        "break_points_saved_pct", "hold_pct", "break_pct",
        "ranking", "win_1st_serve", "break_points_won",
        "break_points_saved", "break_points_faced", "service_games",
        # Home/away variants
        "sets_won_home", "sets_won_away", "games_won_home", "games_won_away",
        "total_sets_home", "total_sets_away", "total_games_home", "total_games_away",
        # Team record variants
        "home_wins", "away_wins", "draws", "return_games", "opponent_rank",
        "home_max_points_streak", "away_max_points_streak",
        # Additional variants
        "home_service_points_won", "away_service_points_won", "home_double_faults", "away_double_faults",
        "home_aces", "away_aces", "home_max_games_streak", "away_max_games_streak",
        "home_hold_pct", "away_hold_pct", "home_break_pct", "away_break_pct",
        "home_return_points_won", "away_return_points_won", "ranking_home", "ranking_away",
        "home_first_serve_pct", "away_first_serve_pct", "home_break_points_saved", "away_break_points_saved",
    },
    "cs2": {
        "kills", "deaths", "kd_ratio", "rating_2_0",
        "maps_played", "maps_won", "map_win_rate",
        "rounds_won_avg", "win_rate_l10", "roster_size",
        "headshot_pct", "adr", "total_score",
    },
    "dota2": {
        "kills_avg", "deaths_avg", "duration_avg_min",
        "win_rate_l10", "hero_pool_size", "first_blood_rate",
        "tower_kills_avg", "roshan_kills_avg", "total_score",
    },
    "valorant": {
        "maps_played", "maps_won", "map_win_rate",
        "win_rate_l10", "rounds_won_avg", "roster_size",
        "acs_avg", "kd_ratio", "total_score", "matches_found", "ranking",
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
