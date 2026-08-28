"""Canonical market definitions per sport, stat key mappings, and translations.

SINGLE SOURCE OF TRUTH for:
- SPORT_MARKETS — dict mapping sport → list of markets
- SPORT_STAT_KEYS — dict mapping sport → list of stat keys
- STANDARD_MARKET_LINES — dict mapping sport → market → standard lines
- MARKET_PL — dict mapping English market names → Polish translations
- DIRECTION_PL — dict mapping direction keywords → Polish translations
"""

# ---------------------------------------------------------------------------
# Per-sport stat key definitions (5 sports)
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
    "tennis": ["sets_won", "total_sets", "games_won", "total_games", "ranking", "aces", "double_faults", "first_serve_pct", "first_serve_win_pct", "second_serve_win_pct", "break_points_saved_pct", "hold_pct", "break_pct"],
    "volleyball": ["points", "aces", "blocks", "hitting_pct", "sets_won", "total_points", "errors"],
    "cs2": [
        "kills", "deaths", "kd_ratio", "rating_2_0",
        "maps_played", "maps_won", "map_win_rate",
        "rounds_won_avg",
    ],
    "dota2": [
        "kills_avg", "deaths_avg", "duration_avg_min",
        "win_rate_l10", "hero_pool_size",
    ],
    "valorant": [
        "maps_played", "maps_won", "map_win_rate",
        "win_rate_l10", "rounds_won_avg",
    ],
}

# ---------------------------------------------------------------------------
# Market definitions per sport (14 sports)
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
    {"name": "Total Shots O/U", "stat_a": "shots", "stat_b": "shots", "is_combined": True},
    {"name": "Total Hits O/U", "stat_a": "hits", "stat_b": "hits", "is_combined": True},
    {"name": "Total Blocks O/U", "stat_a": "blocks", "stat_b": "blocks", "is_combined": True},
    {"name": "Total PIM O/U", "stat_a": "pim", "stat_b": "pim", "is_combined": True},
    {"name": "Powerplay Goals O/U", "stat_a": "powerplay_goals", "stat_b": "powerplay_goals", "is_combined": True},
    {"name": "Team A Shots O/U", "stat_a": "shots", "stat_b": None, "is_combined": False},
    {"name": "Team B Shots O/U", "stat_a": None, "stat_b": "shots", "is_combined": False},
    {"name": "Total Goals O/U", "stat_a": "goals", "stat_b": "goals", "is_combined": True},
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
    {"name": "Break Points Total O/U", "stat_a": "break_pct", "stat_b": "break_pct", "is_combined": True},
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

# ---------------------------------------------------------------------------
# Esports market definitions (CS2, Dota 2, Valorant)
# ---------------------------------------------------------------------------

CS2_MARKETS = [
    {"name": "Total Maps O/U", "stat_a": "maps_played", "stat_b": "maps_played", "is_combined": True},
    {"name": "Total Rounds O/U", "stat_a": "rounds_won_avg", "stat_b": "rounds_won_avg", "is_combined": True},
    {"name": "Map Handicap", "stat_a": "map_win_rate", "stat_b": "map_win_rate", "is_combined": False},
    {"name": "Team A Maps O/U", "stat_a": "maps_won", "stat_b": None, "is_combined": False},
    {"name": "Team B Maps O/U", "stat_a": None, "stat_b": "maps_won", "is_combined": False},
]

DOTA2_MARKETS = [
    {"name": "Total Kills O/U", "stat_a": "kills_avg", "stat_b": "kills_avg", "is_combined": True},
    {"name": "Match Duration O/U", "stat_a": "duration_avg_min", "stat_b": "duration_avg_min", "is_combined": True},
    {"name": "Team A Kills O/U", "stat_a": "kills_avg", "stat_b": None, "is_combined": False},
    {"name": "Team B Kills O/U", "stat_a": None, "stat_b": "kills_avg", "is_combined": False},
    {"name": "Map Handicap", "stat_a": "win_rate_l10", "stat_b": "win_rate_l10", "is_combined": False},
]

VALORANT_MARKETS = [
    {"name": "Total Maps O/U", "stat_a": "maps_played", "stat_b": "maps_played", "is_combined": True},
    {"name": "Total Rounds O/U", "stat_a": "rounds_won_avg", "stat_b": "rounds_won_avg", "is_combined": True},
    {"name": "Map Handicap", "stat_a": "map_win_rate", "stat_b": "map_win_rate", "is_combined": False},
    {"name": "Team A Maps O/U", "stat_a": "maps_won", "stat_b": None, "is_combined": False},
    {"name": "Team B Maps O/U", "stat_a": None, "stat_b": "maps_won", "is_combined": False},
]

SPORT_MARKETS: dict[str, list[dict]] = {
    "football": FOOTBALL_MARKETS,
    "basketball": BASKETBALL_MARKETS,
    "hockey": HOCKEY_MARKETS,
    "tennis": TENNIS_MARKETS,
    "volleyball": VOLLEYBALL_MARKETS,
    "cs2": CS2_MARKETS,
    "dota2": DOTA2_MARKETS,
    "valorant": VALORANT_MARKETS,
}

# ---------------------------------------------------------------------------
# Standard market lines for stats-first mode (5 sports)
# ---------------------------------------------------------------------------

STANDARD_MARKET_LINES: dict[str, list[dict]] = {
    "football": [
        {"market": "Corners Total", "lines": [8.5, 9.5, 10.5, 11.5], "stat": "corners", "is_combined": True},
        {"market": "Cards Total", "lines": [3.5, 4.5, 5.5], "stat": "yellow_cards", "is_combined": True},
        {"market": "Fouls Total", "lines": [20.5, 22.5, 24.5], "stat": "fouls", "is_combined": True},
        {"market": "Shots on Target", "lines": [4.5, 5.5, 6.5, 7.5], "stat": "shots_on_target", "is_combined": True},
        {"market": "Goals Total", "lines": [1.5, 2.5, 3.5], "stat": "goals", "is_combined": True},
        # Per-team totals. "Team Corners" was here alone and unreachable: no
        # provider kept a home/away split past its own client, so ANALYZE
        # skipped every is_combined=False market. Bzzoiro's
        # /events/{id}/stats/ does keep it, which is what makes these four
        # priceable -- and per-team is where the winning coupons actually sat.
        #
        # Lines are roughly half the corresponding match total, which is where
        # a book puts them: a match priced at 9.5 corners is two teams at ~4.5
        # each. The three-line spread per market is the same shape as the
        # combined ones, so a lopsided fixture still has a line near its mean.
        {"market": "Team Corners", "lines": [3.5, 4.5, 5.5], "stat": "corners", "is_combined": False},
        {"market": "Team Fouls", "lines": [8.5, 10.5, 12.5], "stat": "fouls", "is_combined": False},
        {"market": "Team Cards", "lines": [1.5, 2.5, 3.5], "stat": "yellow_cards", "is_combined": False},
        {"market": "Team Shots on Target", "lines": [2.5, 3.5, 4.5, 5.5], "stat": "shots_on_target", "is_combined": False},
        {"market": "Team Shots", "lines": [9.5, 11.5, 13.5], "stat": "shots", "is_combined": False},
    ],
    "basketball": [
        {"market": "Total Points", "lines": [195.5, 205.5, 215.5, 225.5], "stat": "points", "is_combined": True},
        {"market": "Team Points", "lines": [95.5, 100.5, 105.5, 110.5], "stat": "points", "is_combined": False},
        {"market": "Total Rebounds", "lines": [78.5, 82.5, 86.5, 90.5], "stat": "rebounds", "is_combined": True},
        {"market": "Team Rebounds", "lines": [38.5, 40.5, 42.5, 44.5], "stat": "rebounds", "is_combined": False},
        {"market": "Total Assists", "lines": [42.5, 44.5, 46.5, 48.5], "stat": "assists", "is_combined": True},
        {"market": "Team Assists", "lines": [20.5, 22.5, 24.5, 26.5], "stat": "assists", "is_combined": False},
        {"market": "Total Steals", "lines": [12.5, 14.5, 16.5], "stat": "steals", "is_combined": True},
        {"market": "Total Turnovers", "lines": [24.5, 26.5, 28.5, 30.5], "stat": "turnovers", "is_combined": True},
    ],
    "tennis": [
        {"market": "Total Games", "lines": [19.5, 21.5, 22.5, 23.5], "stat": "total_games", "is_combined": True},
        {"market": "Total Aces", "lines": [8.5, 10.5, 12.5], "stat": "aces", "is_combined": True},
        {"market": "Total Sets", "lines": [2.5], "stat": "sets_won", "is_combined": True},
        # double_faults_total and the break markets were canonical names with no
        # line, so ANALYZE emitted no row for them however good the data was.
        # They get lines now because bzzoiro-tennis is the first provider that
        # actually reports them: espn-tennis aliases only games and sets, and
        # tennis-abstract covers a fraction of the tour.
        {"market": "Total Double Faults", "lines": [3.5, 5.5, 7.5], "stat": "double_faults", "is_combined": True},
        # Breaks of serve, not break *points*: the payload gives break-point
        # rates as floats (57.14285714285714) and recovering "4 of 7" from one
        # means guessing a denominator. Service games lost are integers that mean
        # what they say, so that is what this market is priced on.
        {"market": "Total Breaks of Serve", "lines": [3.5, 4.5, 5.5, 6.5], "stat": "breaks", "is_combined": True},
        # Per player, from the same box score. Two rows per fixture, one each
        # side, distinguished by StatsSheetRow.team_name.
        {"market": "Player Aces", "lines": [3.5, 4.5, 5.5, 6.5], "stat": "aces", "is_combined": False},
        {"market": "Player Double Faults", "lines": [1.5, 2.5, 3.5], "stat": "double_faults", "is_combined": False},
        {"market": "Player Games Won", "lines": [8.5, 10.5, 12.5], "stat": "games_won", "is_combined": False},
    ],
    "volleyball": [
        {"market": "Total Sets", "lines": [3.5, 4.5], "stat": "sets_won", "is_combined": True},
        {"market": "Total Points", "lines": [150.5, 160.5, 170.5, 180.5], "stat": "total_points", "is_combined": True},
    ],
    "hockey": [
        {"market": "Total Shots", "lines": [55.5, 58.5, 60.5, 63.5, 65.5], "stat": "shots", "is_combined": True},
        {"market": "Total Hits", "lines": [40.5, 45.5, 50.5, 55.5], "stat": "hits", "is_combined": True},
        {"market": "Total Blocks", "lines": [25.5, 28.5, 30.5, 32.5], "stat": "blocks", "is_combined": True},
        {"market": "Total PIM", "lines": [8.5, 10.5, 12.5, 14.5], "stat": "pim", "is_combined": True},
        {"market": "Powerplay Goals", "lines": [0.5, 1.5, 2.5], "stat": "powerplay_goals", "is_combined": True},
        {"market": "Total Goals", "lines": [4.5, 5.5, 6.5], "stat": "goals", "is_combined": True},
    ],
    "cs2": [
        {"market": "Total Rounds", "lines": [24.5, 25.5, 26.5], "stat": "rounds_won_avg", "is_combined": True},
        {"market": "Total Maps", "lines": [2.5], "stat": "maps_played", "is_combined": True},
        {"market": "Map Handicap", "lines": [-1.5, 1.5], "stat": "map_win_rate", "is_combined": False},
    ],
    "dota2": [
        {"market": "Total Kills", "lines": [44.5, 48.5, 52.5], "stat": "kills_avg", "is_combined": True},
        {"market": "Match Duration", "lines": [32.5, 35.5, 38.5], "stat": "duration_avg_min", "is_combined": True},
        {"market": "Map Handicap", "lines": [-1.5, 1.5], "stat": "win_rate_l10", "is_combined": False},
    ],
    "valorant": [
        {"market": "Total Rounds", "lines": [24.5, 25.5, 26.5], "stat": "rounds_won_avg", "is_combined": True},
        {"market": "Total Maps", "lines": [2.5], "stat": "maps_played", "is_combined": True},
        {"market": "Map Handicap", "lines": [-1.5, 1.5], "stat": "map_win_rate", "is_combined": False},
    ],
}

# ---------------------------------------------------------------------------
# Polish market translations
# ---------------------------------------------------------------------------

MARKET_PL: dict[str, str] = {
    "Corners Total O/U": "Rzuty rożne łącznie",
    "Fouls Total O/U": "Faule łącznie",
    "Cards Total O/U": "Kartki łącznie",
    "Shots Total O/U": "Strzały łącznie",
    "Shots on Target Total O/U": "Strzały celne łącznie",
    "Goals Total O/U": "Bramki łącznie",
    "Total Games O/U": "Gemy łącznie",
    "Total Sets O/U": "Sety łącznie",
    "Total Points O/U": "Punkty łącznie",
    "Total Goals O/U": "Bramki łącznie",
    "Total Rebounds O/U": "Zbiórki łącznie",
    "Total Aces O/U": "Asy łącznie",
    "Total Assists O/U": "Asysty łącznie",
    "Total Steals O/U": "Przechwyty łącznie",
    "Total Turnovers O/U": "Straty łącznie",
    "Total Shots O/U": "Strzały łącznie",
    "Total PIM O/U": "Minuty karne łącznie",
    "Total Hits O/U": "Hity łącznie",
    "Total Blocks O/U": "Bloki łącznie",
    "Powerplay Goals O/U": "Bramki w przewadze łącznie",
    "Total Double Faults O/U": "Podwójne błędy łącznie",
    "Total Errors O/U": "Błędy łącznie",
    "Break Points Total O/U": "Break pointy łącznie",
    "Total Break Points O/U": "Break pointy łącznie",
    "Team A Corners O/U": "Rzuty rożne drużyny",
    "Team B Corners O/U": "Rzuty rożne drużyny",
    "Team A Fouls O/U": "Faule drużyny",
    "Team B Fouls O/U": "Faule drużyny",
    "Team A Cards O/U": "Kartki drużyny",
    "Team B Cards O/U": "Kartki drużyny",
    "Team A Shots O/U": "Strzały drużyny",
    "Team B Shots O/U": "Strzały drużyny",
    "Team A Shots on Target O/U": "Strzały celne drużyny",
    "Team B Shots on Target O/U": "Strzały celne drużyny",
    "Team A Points O/U": "Punkty drużyny",
    "Team B Points O/U": "Punkty drużyny",
    "Team A Rebounds O/U": "Zbiórki drużyny",
    "Team B Rebounds O/U": "Zbiórki drużyny",
    "Team A Assists O/U": "Asysty drużyny",
    "Team B Assists O/U": "Asysty drużyny",
    "Team A Goals O/U": "Bramki drużyny",
    "Team B Goals O/U": "Bramki drużyny",
    "Player A Games O/U": "Gemy zawodnika",
    "Player B Games O/U": "Gemy zawodnika",
    "Player A Aces O/U": "Asy zawodnika",
    "Player B Aces O/U": "Asy zawodnika",
    "Player A Sets O/U": "Sety zawodnika",
    "Player B Sets O/U": "Sety zawodnika",
    "Match Winner": "Zwycięzca meczu",
    "1X2": "1X2",
    "Double Chance": "Podwójna szansa",
    "Draw No Bet": "Remis bez zakładu",
    "BTTS": "Obie strzelą",
    "Handicap": "Handicap",
    "Set Handicap": "Handicap setowy",
    "Game Handicap": "Handicap gemowy",
    # Esports
    "Total Maps O/U": "Mapy łącznie",
    "Total Rounds O/U": "Rundy łącznie",
    "Map Handicap": "Handicap mapowy",
    "Team A Maps O/U": "Mapy drużyny",
    "Team B Maps O/U": "Mapy drużyny",
    "Total Kills O/U": "Zabójstwa łącznie",
    "Match Duration O/U": "Czas gry",
    "Team A Kills O/U": "Zabójstwa drużyny",
    "Team B Kills O/U": "Zabójstwa drużyny",
}

DIRECTION_PL: dict[str, str] = {
    "OVER": "powyżej",
    "UNDER": "poniżej",
}


# ---------------------------------------------------------------------------
# Analysis functions (Task 4.3)
# ---------------------------------------------------------------------------


def rank_candidates(
    candidates: list,
    historical_results: dict[str, float] | None = None,
    config=None,
) -> list:
    """Rank all market candidates across all fixtures.

    Ranking criteria (in order):
    1. Safety score (descending)
    2. Three-way alignment (aligned first)
    3. UNDER direction preference (UNDER before OVER at same safety)
    4. EV if odds available (descending)

    Historical hit rates are advisory data and are never used for rejection.
    """
    if historical_results:
        attach_historical_results(candidates, historical_results)

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


def attach_historical_results(candidates: list, historical_data) -> None:
    """Attach historical hit rates to candidates as non-rejection metadata.

    ``historical_data`` is either a ``sport×market`` mapping or a DB connection.
    """
    if isinstance(historical_data, dict):
        for c in candidates:
            key = f"{c.sport_name}×{c.market_name}"
            c.historical_hit_rate = historical_data.get(key)
    elif historical_data is not None:
        # Assume it's a DB connection — query historical hit rates
        try:
            rows = historical_data.execute(
                "SELECT sport, market, "
                "CAST(SUM(CASE WHEN status = 'won' THEN 1 ELSE 0 END) AS REAL) / "
                "COUNT(*) AS hit_rate "
                "FROM bets WHERE status IN ('won', 'lost') "
                "GROUP BY sport, market"
            ).fetchall()
            history = {f"{r['sport']}×{r['market']}": r["hit_rate"] for r in rows}
            for c in candidates:
                key = f"{c.sport_name}×{c.market_name}"
                c.historical_hit_rate = history.get(key)
        except Exception:
            pass

# ---------------------------------------------------------------------------
# Player prop lines
# ---------------------------------------------------------------------------

# Kept out of STANDARD_MARKET_LINES rather than folded in behind an
# ``is_player`` flag. Four other modules iterate that dict
# (scripts/generate_market_matrix.py, scripts/build_shortlist.py,
# scripts/normalize_stats.py, is_standard_line below) and every one of them
# assumes a row describes a *fixture*. Adding a differently-shaped row there
# would silently produce "Player Shots" candidates with no player attached in
# each of them; the flag they would all need to check is the flag none of them
# has today.
#
# Lines sit low because that is where these markets are actually offered: a
# forward's shots prop is priced around 1.5-2.5, a midfielder's fouls around
# 0.5-1.5, and a card prop is a 0.5 line by construction.
PLAYER_PROP_LINES: dict[str, list[dict]] = {
    "football": [
        {"market": "Player Shots", "lines": [0.5, 1.5, 2.5], "stat": "player_total_shots"},
        {"market": "Player Shots on Target", "lines": [0.5, 1.5], "stat": "player_shots_on_target"},
        {"market": "Player Fouls Committed", "lines": [0.5, 1.5, 2.5], "stat": "player_fouls"},
        {"market": "Player Fouls Won", "lines": [0.5, 1.5, 2.5], "stat": "player_was_fouled"},
        # player_cards, not player_yellow_cards: the market settles on any card.
        {"market": "Player to be Carded", "lines": [0.5], "stat": "player_cards"},
    ],
}


# ---------------------------------------------------------------------------
# Standard line detection helper (ERROR 8 fix — 2026-05-19)
# ---------------------------------------------------------------------------

# Flat set of ALL standard lines for fast lookup
_ALL_STANDARD_LINES: set[float] = set()
for _sport_lines in STANDARD_MARKET_LINES.values():
    for _mkt in _sport_lines:
        for _line in _mkt.get("lines", []):
            _ALL_STANDARD_LINES.add(_line)


def is_standard_line(sport: str, market: str, line: float) -> bool:
    """Check if a line value comes from STANDARD_MARKET_LINES (not a real bookmaker).

    Returns True if the line matches a default standard line for this sport/market.
    Picks using standard lines should be flagged as LINE_UNVERIFIED.
    """
    sport_lines = STANDARD_MARKET_LINES.get(sport, [])
    for mkt in sport_lines:
        mkt_name = mkt.get("market", "").lower()
        if mkt_name in market.lower() or market.lower() in mkt_name:
            if line in mkt.get("lines", []):
                return True
    return False
