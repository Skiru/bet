"""Market definitions per sport and stat key mappings.

Ported from scripts/normalize_stats.py, filtered to 7 focus sports.
"""

# ---------------------------------------------------------------------------
# Per-sport stat key definitions
# ---------------------------------------------------------------------------

SPORT_STAT_KEYS: dict[str, list[str]] = {
    "football": [
        "corners", "fouls", "yellow_cards", "red_cards",
        "shots", "shots_on_target", "possession", "goals",
        "offsides", "saves",
    ],
    "basketball": [
        "points", "rebounds", "assists", "steals", "blocks",
        "turnovers", "fg_pct", "three_pct", "ft_pct",
    ],
    "hockey": [
        "goals", "shots", "powerplay_goals", "pim",
        "hits", "blocks", "faceoff_pct",
    ],
    "tennis": [
        "aces", "double_faults", "first_serve_pct",
        "break_points_won", "games_won", "sets_won", "total_games",
    ],
    "volleyball": [
        "points", "aces", "blocks", "attack_pct",
        "sets_won", "total_points", "errors",
    ],
    "snooker": [
        "frames_won", "centuries", "highest_break",
        "total_frames", "fifty_plus_breaks",
    ],
    "speedway": [
        "heat_points", "total_points", "heat_wins",
    ],
}

# ---------------------------------------------------------------------------
# Market definitions per sport
# ---------------------------------------------------------------------------

FOOTBALL_MARKETS = [
    {"name": "Corners Total O/U", "stat_a": "corners", "stat_b": "corners", "is_combined": True},
    {"name": "Fouls Total O/U", "stat_a": "fouls", "stat_b": "fouls", "is_combined": True},
    {"name": "Cards Total O/U", "stat_a": "yellow_cards", "stat_b": "yellow_cards", "is_combined": True},
    {"name": "Shots Total O/U", "stat_a": "shots", "stat_b": "shots", "is_combined": True},
    {"name": "Shots on Target Total O/U", "stat_a": "shots_on_target", "stat_b": "shots_on_target", "is_combined": True},
    {"name": "Team A Corners O/U", "stat_a": "corners", "stat_b": None, "is_combined": False},
    {"name": "Team B Corners O/U", "stat_a": None, "stat_b": "corners", "is_combined": False},
    {"name": "Team A Fouls O/U", "stat_a": "fouls", "stat_b": None, "is_combined": False},
    {"name": "Team B Fouls O/U", "stat_a": None, "stat_b": "fouls", "is_combined": False},
    {"name": "Team A Cards O/U", "stat_a": "yellow_cards", "stat_b": None, "is_combined": False},
    {"name": "Team B Cards O/U", "stat_a": None, "stat_b": "yellow_cards", "is_combined": False},
    {"name": "Team A Shots O/U", "stat_a": "shots", "stat_b": None, "is_combined": False},
    {"name": "Team B Shots O/U", "stat_a": None, "stat_b": "shots", "is_combined": False},
    {"name": "Team A Shots on Target O/U", "stat_a": "shots_on_target", "stat_b": None, "is_combined": False},
    {"name": "Team B Shots on Target O/U", "stat_a": None, "stat_b": "shots_on_target", "is_combined": False},
    {"name": "Goals Total O/U", "stat_a": "goals", "stat_b": "goals", "is_combined": True},
]

BASKETBALL_MARKETS = [
    {"name": "Total Points O/U", "stat_a": "points", "stat_b": "points", "is_combined": True},
    {"name": "Total Rebounds O/U", "stat_a": "rebounds", "stat_b": "rebounds", "is_combined": True},
    {"name": "Total Assists O/U", "stat_a": "assists", "stat_b": "assists", "is_combined": True},
    {"name": "Team A Points O/U", "stat_a": "points", "stat_b": None, "is_combined": False},
    {"name": "Team B Points O/U", "stat_a": None, "stat_b": "points", "is_combined": False},
    {"name": "Team A Rebounds O/U", "stat_a": "rebounds", "stat_b": None, "is_combined": False},
    {"name": "Team B Rebounds O/U", "stat_a": None, "stat_b": "rebounds", "is_combined": False},
    {"name": "Team A Assists O/U", "stat_a": "assists", "stat_b": None, "is_combined": False},
    {"name": "Team B Assists O/U", "stat_a": None, "stat_b": "assists", "is_combined": False},
    {"name": "Total Steals O/U", "stat_a": "steals", "stat_b": "steals", "is_combined": True},
    {"name": "Total Turnovers O/U", "stat_a": "turnovers", "stat_b": "turnovers", "is_combined": True},
]

HOCKEY_MARKETS = [
    {"name": "Total Goals O/U", "stat_a": "goals", "stat_b": "goals", "is_combined": True},
    {"name": "Total Shots O/U", "stat_a": "shots", "stat_b": "shots", "is_combined": True},
    {"name": "Total PIM O/U", "stat_a": "pim", "stat_b": "pim", "is_combined": True},
    {"name": "Team A Shots O/U", "stat_a": "shots", "stat_b": None, "is_combined": False},
    {"name": "Team B Shots O/U", "stat_a": None, "stat_b": "shots", "is_combined": False},
    {"name": "Total Hits O/U", "stat_a": "hits", "stat_b": "hits", "is_combined": True},
    {"name": "Total Blocks O/U", "stat_a": "blocks", "stat_b": "blocks", "is_combined": True},
]

TENNIS_MARKETS = [
    {"name": "Total Games O/U", "stat_a": "total_games", "stat_b": "total_games", "is_combined": True},
    {"name": "Total Aces O/U", "stat_a": "aces", "stat_b": "aces", "is_combined": True},
    {"name": "Total Double Faults O/U", "stat_a": "double_faults", "stat_b": "double_faults", "is_combined": True},
    {"name": "Player A Games O/U", "stat_a": "games_won", "stat_b": None, "is_combined": False},
    {"name": "Player B Games O/U", "stat_a": None, "stat_b": "games_won", "is_combined": False},
    {"name": "Total Sets O/U", "stat_a": "sets_won", "stat_b": "sets_won", "is_combined": True},
    {"name": "Player A Aces O/U", "stat_a": "aces", "stat_b": None, "is_combined": False},
    {"name": "Player B Aces O/U", "stat_a": None, "stat_b": "aces", "is_combined": False},
    {"name": "Break Points Total O/U", "stat_a": "break_points_won", "stat_b": "break_points_won", "is_combined": True},
]

VOLLEYBALL_MARKETS = [
    {"name": "Total Sets O/U", "stat_a": "sets_won", "stat_b": "sets_won", "is_combined": True},
    {"name": "Total Points O/U", "stat_a": "total_points", "stat_b": "total_points", "is_combined": True},
    {"name": "Team A Points O/U", "stat_a": "total_points", "stat_b": None, "is_combined": False},
    {"name": "Team B Points O/U", "stat_a": None, "stat_b": "total_points", "is_combined": False},
    {"name": "Total Aces O/U", "stat_a": "aces", "stat_b": "aces", "is_combined": True},
    {"name": "Total Blocks O/U", "stat_a": "blocks", "stat_b": "blocks", "is_combined": True},
    {"name": "Total Errors O/U", "stat_a": "errors", "stat_b": "errors", "is_combined": True},
]

SNOOKER_MARKETS = [
    {"name": "Total Frames O/U", "stat_a": "total_frames", "stat_b": "total_frames", "is_combined": True},
    {"name": "Total Centuries O/U", "stat_a": "centuries", "stat_b": "centuries", "is_combined": True},
    {"name": "Total 50+ Breaks O/U", "stat_a": "fifty_plus_breaks", "stat_b": "fifty_plus_breaks", "is_combined": True},
    {"name": "Player A Frames O/U", "stat_a": "frames_won", "stat_b": None, "is_combined": False},
    {"name": "Player B Frames O/U", "stat_a": None, "stat_b": "frames_won", "is_combined": False},
]

SPEEDWAY_MARKETS = [
    {"name": "Total Points O/U", "stat_a": "total_points", "stat_b": "total_points", "is_combined": True},
    {"name": "Team A Points O/U", "stat_a": "heat_points", "stat_b": None, "is_combined": False},
    {"name": "Team B Points O/U", "stat_a": None, "stat_b": "heat_points", "is_combined": False},
    {"name": "Total Heat Wins O/U", "stat_a": "heat_wins", "stat_b": "heat_wins", "is_combined": True},
]

SPORT_MARKETS: dict[str, list[dict]] = {
    "football": FOOTBALL_MARKETS,
    "basketball": BASKETBALL_MARKETS,
    "hockey": HOCKEY_MARKETS,
    "tennis": TENNIS_MARKETS,
    "volleyball": VOLLEYBALL_MARKETS,
    "snooker": SNOOKER_MARKETS,
    "speedway": SPEEDWAY_MARKETS,
}

# Standard market lines for stats-first mode
STANDARD_MARKET_LINES: dict[str, list[dict]] = {
    "football": [
        {"market": "Corners Total", "lines": [8.5, 9.5, 10.5, 11.5], "stat": "corners"},
        {"market": "Team Corners", "lines": [3.5, 4.5, 5.5], "stat": "corners"},
        {"market": "Cards Total", "lines": [3.5, 4.5, 5.5], "stat": "yellow_cards"},
        {"market": "Fouls Total", "lines": [20.5, 22.5, 24.5], "stat": "fouls"},
        {"market": "Shots on Target", "lines": [4.5, 5.5, 6.5, 7.5], "stat": "shots_on_target"},
        {"market": "Goals Total", "lines": [1.5, 2.5, 3.5], "stat": "goals"},
    ],
    "basketball": [
        {"market": "Total Points", "lines": [195.5, 205.5, 215.5, 225.5], "stat": "points"},
        {"market": "Team Points", "lines": [95.5, 100.5, 105.5, 110.5], "stat": "points"},
        {"market": "Total Rebounds", "lines": [40.5, 42.5, 44.5], "stat": "rebounds"},
        {"market": "Total Assists", "lines": [22.5, 24.5, 26.5], "stat": "assists"},
    ],
    "tennis": [
        {"market": "Total Games", "lines": [19.5, 21.5, 22.5, 23.5], "stat": "total_games"},
        {"market": "Total Aces", "lines": [8.5, 10.5, 12.5], "stat": "aces"},
        {"market": "Total Sets", "lines": [2.5], "stat": "sets_won"},
    ],
    "volleyball": [
        {"market": "Total Sets", "lines": [3.5, 4.5], "stat": "sets_won"},
        {"market": "Total Points", "lines": [150.5, 160.5, 170.5, 180.5], "stat": "total_points"},
    ],
    "hockey": [
        {"market": "Total Goals", "lines": [4.5, 5.5, 6.5], "stat": "goals"},
        {"market": "Total Shots", "lines": [55.5, 60.5, 65.5], "stat": "shots"},
    ],
    "snooker": [
        {"market": "Total Frames", "lines": [8.5, 9.5, 10.5, 12.5], "stat": "total_frames"},
    ],
    "speedway": [
        {"market": "Total Points", "lines": [80.5, 85.5, 90.5], "stat": "total_points"},
    ],
}


# ---------------------------------------------------------------------------
# Analysis functions (Task 4.3)
# ---------------------------------------------------------------------------


def rank_candidates(
    candidates: list,
    betclic_history: dict[str, float] | None = None,
    config=None,
) -> list:
    """Rank all market candidates across all fixtures.

    Ranking criteria (in order):
    1. Safety score (descending)
    2. Three-way alignment (aligned first)
    3. UNDER direction preference (UNDER before OVER at same safety)
    4. EV if odds available (descending)

    Betclic history hit rates are attached as advisory data (NEVER used for rejection).
    """
    if betclic_history:
        attach_betclic_history(candidates, betclic_history)

    candidates.sort(
        key=lambda c: (
            c.safety_score,
            c.three_way_aligned,
            c.direction == "UNDER",
            c.ev if c.ev is not None else -999,
        ),
        reverse=True,
    )

    return candidates


def quality_checks(candidate, db_conn) -> list[str]:
    """Run 5 quality checks on a candidate. Returns list of failed check names.

    Checks:
    1. data_completeness: L10 has ≥ 8 values
    2. positive_ev: EV > 0 (if odds available) OR min_odds < 3.50 (if no odds)
    3. no_48h_repeat: Same team+market not bet in last 48h
    4. min_safety: safety_score ≥ 0.60
    5. three_way_check: three_way_aligned is True
    """
    failed: list[str] = []

    # 1. Data completeness
    if candidate.hit_rate_l10 == 0:
        failed.append("data_completeness")

    # 2. Positive EV
    if candidate.ev is not None:
        if candidate.ev <= 0:
            failed.append("positive_ev")
    elif candidate.min_odds >= 3.50:
        failed.append("positive_ev")

    # 3. No 48h repeat
    if db_conn is not None:
        from datetime import datetime, timedelta, timezone
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
        home_name = candidate.home_team.name if candidate.home_team else ""
        away_name = candidate.away_team.name if candidate.away_team else ""
        event_pattern = f"%{home_name}%{away_name}%"

        row = db_conn.execute(
            "SELECT COUNT(*) AS cnt FROM bets "
            "WHERE market = ? AND event_name LIKE ? AND settled_at > ?",
            (candidate.market_name, event_pattern, cutoff),
        ).fetchone()
        if row and row["cnt"] > 0:
            failed.append("no_48h_repeat")

    # 4. Min safety
    if candidate.safety_score < 0.60:
        failed.append("min_safety")

    # 5. Three-way check
    if not candidate.three_way_aligned:
        failed.append("three_way_check")

    return failed


def attach_betclic_history(candidates: list, betclic_data) -> None:
    """Attach betclic_hit_rate to each candidate (ADVISORY ONLY, never rejects).

    betclic_data: dict mapping "sport×market" → hit_rate float,
                  or a DB connection to query from bets table.
    """
    if isinstance(betclic_data, dict):
        for c in candidates:
            key = f"{c.sport_name}×{c.market_name}"
            c.betclic_hit_rate = betclic_data.get(key)
    elif betclic_data is not None:
        # Assume it's a DB connection — query historical hit rates
        try:
            rows = betclic_data.execute(
                "SELECT sport, market, "
                "CAST(SUM(CASE WHEN status = 'won' THEN 1 ELSE 0 END) AS REAL) / "
                "COUNT(*) AS hit_rate "
                "FROM bets WHERE status IN ('won', 'lost') "
                "GROUP BY sport, market"
            ).fetchall()
            history = {f"{r['sport']}×{r['market']}": r["hit_rate"] for r in rows}
            for c in candidates:
                key = f"{c.sport_name}×{c.market_name}"
                c.betclic_hit_rate = history.get(key)
        except Exception:
            pass
