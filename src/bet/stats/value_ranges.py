"""Canonical SPORT_VALUE_RANGES — single source of truth for stat validation.

Used by: data_enrichment_agent.py, flashscore_enricher.py, src/bet/scrapers/flashscore.py,
clean_garbage_team_form.py. Import from here — do NOT define locally.
"""

SPORT_VALUE_RANGES: dict[str, dict[str, tuple[float, float]]] = {
    "football": {
        "corners": (0, 20), "fouls": (0, 35), "yellow_cards": (0, 12),
        "red_cards": (0, 4), "shots": (0, 40), "shots_on_target": (0, 20),
        "shots_off_target": (0, 30), "possession": (20, 80),
        "ball_possession": (20, 80), "goals": (0, 12), "offsides": (0, 15),
        "saves": (0, 15), "game_total_goals": (0, 15),
    },
    "basketball": {
        "points": (50, 160), "rebounds": (15, 70), "assists": (10, 45),
        "steals": (0, 20), "blocks": (0, 15), "turnovers": (0, 30),
        "fg_pct": (25, 65), "three_pct": (15, 55), "ft_pct": (50, 100),
        "2_pointers": (0, 60), "3_pointers": (0, 30), "free_throws": (0, 40),
        "game_total_points": (100, 350),
    },
    "hockey": {
        "goals": (0, 12), "shots": (10, 60), "powerplay_goals": (0, 5),
        "power_play_goals": (0, 5), "pim": (0, 50), "hits": (10, 70),
        "blocks": (5, 35), "faceoff_pct": (30, 70), "shots_on_goal": (0, 60),
        "penalties_in_minutes": (0, 50), "game_total_goals": (0, 20),
    },
    "tennis": {
        "aces": (0, 40), "double_faults": (0, 15), "first_serve_pct": (40, 95),
        "break_points_won": (0, 15), "games_won": (0, 25), "sets_won": (0, 5),
        "total_games": (10, 80), "win_1st_serve": (0, 100),
        "break_points_saved": (0, 100),
    },
    "volleyball": {
        "points": (0, 160), "aces": (0, 15), "blocks": (0, 20),
        "hitting_pct": (20, 70), "sets_won": (0, 5), "total_points": (60, 250),
        "errors": (0, 30),
    },
}
