"""Stats normalizer framework — unified data structures for multi-source sports stats.

Converts API-specific response formats into normalized dataclasses, then builds
input for compute_safety_scores.py (§3.0 market ranking protocol).
"""

import json
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

CACHE_DIR = Path(__file__).parent.parent / "betting" / "data" / "stats_cache"

PERCENTAGE_STATS = {
    "possession", "fg_pct", "three_pct", "ft_pct",
    "first_serve_pct", "faceoff_pct", "attack_pct", "checkout_pct",
}

# Standard market lines per sport/stat — used instead of auto-computed lines
# to avoid circular reasoning (computing line from same data used for hit rate)
try:
    from scripts.generate_market_matrix import STANDARD_MARKET_LINES as _SML
except ImportError:
    try:
        from generate_market_matrix import STANDARD_MARKET_LINES as _SML
    except ImportError:
        _SML = {}

# Build SEPARATE lookups for combined and team lines to prevent collision.
# Sports like basketball have "Total Points" (combined, lines=[195.5-225.5]) and
# "Team Points" (per-team, lines=[95.5-110.5]) sharing the same stat key "points".
# A single dict would overwrite one with the other.
_STANDARD_LINES_COMBINED: dict[tuple[str, str], list[float]] = {}
_STANDARD_LINES_TEAM: dict[tuple[str, str], list[float]] = {}
for _sport_key, _markets_list in _SML.items():
    for _mkt in _markets_list:
        _stat = _mkt.get("stat", "")
        _lines = _mkt.get("lines", [])
        if _stat and _lines:
            if _mkt.get("is_combined", True):
                _STANDARD_LINES_COMBINED[(_sport_key, _stat)] = _lines
            else:
                _STANDARD_LINES_TEAM[(_sport_key, _stat)] = _lines


def _find_closest_standard_line(sport: str, stat_key: str, avg: float, is_combined: bool = True) -> float | None:
    """Find the closest standard line for a given sport/stat/average.

    Returns the standard line closest to the data average, or None if no
    standard lines exist for this sport/stat combination or if the closest
    line is too far from the average (>40% away).

    Uses separate lookups for combined (total) vs per-team markets to avoid
    the collision where team lines [95.5-110.5] overwrite total lines [195.5-225.5].
    """
    lookup = _STANDARD_LINES_COMBINED if is_combined else _STANDARD_LINES_TEAM
    lines = lookup.get((sport, stat_key))
    if not lines:
        return None
    closest = min(lines, key=lambda x: abs(x - avg))
    # Sanity check: don't use a standard line that's wildly different from the average
    if avg > 0 and abs(closest - avg) / avg > 0.40:
        return None
    return closest


# ---------------------------------------------------------------------------
# Normalized data structures
# ---------------------------------------------------------------------------

@dataclass
class NormalizedFixture:
    """Normalized fixture/game metadata."""
    fixture_id: str
    source: str
    sport: str
    competition: str
    home_team: str
    away_team: str
    home_team_id: str = ""
    away_team_id: str = ""
    kickoff: str = ""
    status: str = "scheduled"


@dataclass
class NormalizedMatchStats:
    """Normalized per-match statistics from any source."""
    fixture_id: str
    source: str
    sport: str
    home_team: str
    away_team: str
    date: str
    stats: dict = field(default_factory=dict)
    # stats keys are sport-specific, values are dicts with "home" and "away" sub-keys
    # e.g. {"corners": {"home": 5, "away": 3}, "fouls": {"home": 12, "away": 9}}


# ---------------------------------------------------------------------------
# Per-sport stat key definitions
# ---------------------------------------------------------------------------

SPORT_STAT_KEYS = {
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
    "tennis": ["aces", "double_faults", "first_serve_pct", "break_points_won", "games_won", "sets_won", "total_games"],
    "volleyball": ["points", "aces", "blocks", "attack_pct", "sets_won", "total_points", "errors"],
    "handball": ["goals", "saves", "turnovers", "penalties", "suspensions", "total_goals"],
    "snooker": ["frames_won", "centuries", "highest_break", "total_frames", "fifty_plus_breaks"],
    "darts": ["legs_won", "checkout_pct", "one_eighties", "avg_score", "total_legs"],
    "table_tennis": ["sets_won", "points_per_set", "total_sets", "total_points"],
    "esports": ["maps_won", "rounds_won", "kills", "total_maps", "total_rounds"],
    "baseball": ["runs", "hits", "errors", "strikeouts", "walks", "total_runs", "home_runs"],
    "mma": ["takedowns", "sig_strikes", "submission_attempts", "rounds", "control_time"],
    "padel": ["games_won", "break_points", "sets_won", "total_games"],
    "speedway": ["heat_points", "total_points", "heat_wins"],
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

HANDBALL_MARKETS = [
    {"name": "Total Goals O/U", "stat_a": "goals", "stat_b": "goals", "is_combined": True},
    {"name": "Team A Goals O/U", "stat_a": "goals", "stat_b": None, "is_combined": False},
    {"name": "Team B Goals O/U", "stat_a": None, "stat_b": "goals", "is_combined": False},
    {"name": "Total Saves O/U", "stat_a": "saves", "stat_b": "saves", "is_combined": True},
    {"name": "Total Suspensions O/U", "stat_a": "suspensions", "stat_b": "suspensions", "is_combined": True},
    {"name": "Total Turnovers O/U", "stat_a": "turnovers", "stat_b": "turnovers", "is_combined": True},
    {"name": "Total Penalties O/U", "stat_a": "penalties", "stat_b": "penalties", "is_combined": True},
]

SNOOKER_MARKETS = [
    {"name": "Total Frames O/U", "stat_a": "total_frames", "stat_b": "total_frames", "is_combined": True},
    {"name": "Total Centuries O/U", "stat_a": "centuries", "stat_b": "centuries", "is_combined": True},
    {"name": "Total 50+ Breaks O/U", "stat_a": "fifty_plus_breaks", "stat_b": "fifty_plus_breaks", "is_combined": True},
    {"name": "Player A Frames O/U", "stat_a": "frames_won", "stat_b": None, "is_combined": False},
    {"name": "Player B Frames O/U", "stat_a": None, "stat_b": "frames_won", "is_combined": False},
]

DARTS_MARKETS = [
    {"name": "Total 180s O/U", "stat_a": "one_eighties", "stat_b": "one_eighties", "is_combined": True},
    {"name": "Total Legs O/U", "stat_a": "total_legs", "stat_b": "total_legs", "is_combined": True},
    {"name": "Player A Legs O/U", "stat_a": "legs_won", "stat_b": None, "is_combined": False},
    {"name": "Player B Legs O/U", "stat_a": None, "stat_b": "legs_won", "is_combined": False},
    {"name": "Player A 180s O/U", "stat_a": "one_eighties", "stat_b": None, "is_combined": False},
    {"name": "Player B 180s O/U", "stat_a": None, "stat_b": "one_eighties", "is_combined": False},
]

TABLE_TENNIS_MARKETS = [
    {"name": "Total Sets O/U", "stat_a": "total_sets", "stat_b": "total_sets", "is_combined": True},
    {"name": "Total Points O/U", "stat_a": "total_points", "stat_b": "total_points", "is_combined": True},
    {"name": "Player A Sets O/U", "stat_a": "sets_won", "stat_b": None, "is_combined": False},
    {"name": "Player B Sets O/U", "stat_a": None, "stat_b": "sets_won", "is_combined": False},
]

ESPORTS_MARKETS = [
    {"name": "Total Maps O/U", "stat_a": "total_maps", "stat_b": "total_maps", "is_combined": True},
    {"name": "Total Rounds O/U", "stat_a": "total_rounds", "stat_b": "total_rounds", "is_combined": True},
    {"name": "Total Kills O/U", "stat_a": "kills", "stat_b": "kills", "is_combined": True},
    {"name": "Team A Maps O/U", "stat_a": "maps_won", "stat_b": None, "is_combined": False},
    {"name": "Team B Maps O/U", "stat_a": None, "stat_b": "maps_won", "is_combined": False},
    {"name": "Team A Rounds O/U", "stat_a": "rounds_won", "stat_b": None, "is_combined": False},
    {"name": "Team B Rounds O/U", "stat_a": None, "stat_b": "rounds_won", "is_combined": False},
]

BASEBALL_MARKETS = [
    {"name": "Total Runs O/U", "stat_a": "total_runs", "stat_b": "total_runs", "is_combined": True},
    {"name": "Total Hits O/U", "stat_a": "hits", "stat_b": "hits", "is_combined": True},
    {"name": "Total Strikeouts O/U", "stat_a": "strikeouts", "stat_b": "strikeouts", "is_combined": True},
    {"name": "Team A Runs O/U", "stat_a": "runs", "stat_b": None, "is_combined": False},
    {"name": "Team B Runs O/U", "stat_a": None, "stat_b": "runs", "is_combined": False},
    {"name": "Total Errors O/U", "stat_a": "errors", "stat_b": "errors", "is_combined": True},
    {"name": "Total Home Runs O/U", "stat_a": "home_runs", "stat_b": "home_runs", "is_combined": True},
    {"name": "Total Walks O/U", "stat_a": "walks", "stat_b": "walks", "is_combined": True},
]

MMA_MARKETS = [
    {"name": "Total Rounds O/U", "stat_a": "rounds", "stat_b": "rounds", "is_combined": True},
    {"name": "Total Significant Strikes O/U", "stat_a": "sig_strikes", "stat_b": "sig_strikes", "is_combined": True},
    {"name": "Total Takedowns O/U", "stat_a": "takedowns", "stat_b": "takedowns", "is_combined": True},
    {"name": "Fighter A Sig Strikes O/U", "stat_a": "sig_strikes", "stat_b": None, "is_combined": False},
    {"name": "Fighter B Sig Strikes O/U", "stat_a": None, "stat_b": "sig_strikes", "is_combined": False},
]

PADEL_MARKETS = [
    {"name": "Total Games O/U", "stat_a": "total_games", "stat_b": "total_games", "is_combined": True},
    {"name": "Total Sets O/U", "stat_a": "sets_won", "stat_b": "sets_won", "is_combined": True},
    {"name": "Total Break Points O/U", "stat_a": "break_points", "stat_b": "break_points", "is_combined": True},
    {"name": "Pair A Games O/U", "stat_a": "games_won", "stat_b": None, "is_combined": False},
    {"name": "Pair B Games O/U", "stat_a": None, "stat_b": "games_won", "is_combined": False},
]

SPEEDWAY_MARKETS = [
    {"name": "Total Points O/U", "stat_a": "total_points", "stat_b": "total_points", "is_combined": True},
    {"name": "Team A Points O/U", "stat_a": "heat_points", "stat_b": None, "is_combined": False},
    {"name": "Team B Points O/U", "stat_a": None, "stat_b": "heat_points", "is_combined": False},
    {"name": "Total Heat Wins O/U", "stat_a": "heat_wins", "stat_b": "heat_wins", "is_combined": True},
]

SPORT_MARKETS = {
    "football": FOOTBALL_MARKETS,
    "basketball": BASKETBALL_MARKETS,
    "hockey": HOCKEY_MARKETS,
    "tennis": TENNIS_MARKETS,
    "volleyball": VOLLEYBALL_MARKETS,
    "handball": HANDBALL_MARKETS,
    "snooker": SNOOKER_MARKETS,
    "darts": DARTS_MARKETS,
    "table_tennis": TABLE_TENNIS_MARKETS,
    "esports": ESPORTS_MARKETS,
    "baseball": BASEBALL_MARKETS,
    "mma": MMA_MARKETS,
    "padel": PADEL_MARKETS,
    "speedway": SPEEDWAY_MARKETS,
}


# ---------------------------------------------------------------------------
# Helper: extract stat values from match list
# ---------------------------------------------------------------------------

def _extract_stat_values(
    matches: list[NormalizedMatchStats],
    stat_key: str,
    team_name: str,
    last_n: int = 10,
) -> list[float]:
    """Extract a stat's values from a list of matches.

    Args:
        matches: List of NormalizedMatchStats (most recent first)
        stat_key: The stat to extract (e.g., "corners")
        team_name: Team name — we determine home/away side per match
        last_n: Max number of values to return

    Returns:
        List of numeric stat values (up to last_n)
    """
    values = []
    for match in matches[:last_n]:
        stat = match.stats.get(stat_key, {})
        if isinstance(stat, dict):
            # Determine which side this team was on
            if team_name.lower() == match.home_team.lower():
                val = stat.get("home")
            elif team_name.lower() == match.away_team.lower():
                val = stat.get("away")
            else:
                # Team name doesn't match either side — skip this match
                continue
        else:
            val = stat
        if val is not None and isinstance(val, (int, float)):
            values.append(float(val))
    return values


def _extract_h2h_combined(
    h2h_matches: list[NormalizedMatchStats],
    stat_key: str,
) -> list[float]:
    """Extract combined (home + away) stat values from H2H matches."""
    values = []
    for match in h2h_matches:
        stat = match.stats.get(stat_key, {})
        if isinstance(stat, dict):
            home_val = stat.get("home", 0)
            away_val = stat.get("away", 0)
            if isinstance(home_val, (int, float)) and isinstance(away_val, (int, float)):
                values.append(float(home_val) + float(away_val))
        elif isinstance(stat, (int, float)):
            values.append(float(stat))
    return values


def _round_to_half(value: float) -> float:
    """Round a value to the nearest 0.5."""
    return round(value * 2) / 2


# ---------------------------------------------------------------------------
# Main builder: match data → safety score input
# ---------------------------------------------------------------------------

def build_safety_score_input(
    sport: str,
    team_a: str,
    team_b: str,
    competition: str,
    team_a_matches: list[NormalizedMatchStats],
    team_b_matches: list[NormalizedMatchStats],
    h2h_matches: list[NormalizedMatchStats],
    market_definitions: list[dict] | None = None,
    source: str = "api",
) -> dict | None:
    """Build compute_safety_scores.py input from normalized match data.

    Args:
        sport: Sport name (football, basketball, hockey)
        team_a: Home team name
        team_b: Away team name
        competition: League/competition name
        team_a_matches: Team A's recent matches (most recent first)
        team_b_matches: Team B's recent matches (most recent first)
        h2h_matches: Head-to-head matches between the two teams
        market_definitions: Custom market defs; defaults to SPORT_MARKETS[sport]
        source: Data source identifier

    Returns:
        Dict matching compute_safety_scores.py input format, or None if insufficient data.
    """
    # Minimum match count validation — need ≥5 for at least ONE team
    # (allows team-specific markets like team corners when only one team has data)
    if len(team_a_matches) < 5 and len(team_b_matches) < 5:
        print(f"[normalize] Insufficient data for both teams: {team_a}={len(team_a_matches)}, {team_b}={len(team_b_matches)} (need ≥5 for at least one)")
        return None
    if len(team_a_matches) < 3:
        print(f"[normalize] Very thin data for {team_a}: {len(team_a_matches)} matches — using available data")
    if len(team_b_matches) < 3:
        print(f"[normalize] Very thin data for {team_b}: {len(team_b_matches)} matches — using available data")

    markets = market_definitions or SPORT_MARKETS.get(sport, [])
    if not markets:
        print(f"[normalize] No market definitions for sport: {sport}")
        return None

    built_markets = []

    for market_def in markets:
        stat_a_key = market_def.get("stat_a")
        stat_b_key = market_def.get("stat_b")
        is_combined = market_def.get("is_combined", True)

        # Extract L10 values
        team_a_l10 = []
        team_b_l10 = []

        if stat_a_key:
            team_a_l10 = _extract_stat_values(team_a_matches, stat_a_key, team_a, last_n=10)
        if stat_b_key:
            team_b_l10 = _extract_stat_values(team_b_matches, stat_b_key, team_b, last_n=10)

        # For non-combined Team B-only markets, swap into team_a_l10
        # because compute_safety_scores uses team_a_l10 for non-combined
        if not is_combined:
            if stat_b_key and not stat_a_key:
                team_a_l10 = team_b_l10
                team_b_l10 = []

        # Skip market if insufficient stat data
        if stat_a_key and len(team_a_l10) < 5:
            continue
        if stat_b_key and not stat_a_key and len(team_a_l10) < 5:
            continue
        if stat_b_key and stat_a_key and len(team_b_l10) < 5:
            continue

        # H2H values
        h2h_values = []
        if is_combined and (stat_a_key or stat_b_key):
            h2h_values = _extract_h2h_combined(h2h_matches, stat_a_key or stat_b_key)
        elif stat_a_key:
            h2h_values = _extract_stat_values(h2h_matches, stat_a_key, team_a)
        elif stat_b_key:
            h2h_values = _extract_stat_values(h2h_matches, stat_b_key, team_b)

        # L5 = last 5 entries of L10
        team_a_l5 = team_a_l10[:5] if team_a_l10 else []
        team_b_l5 = team_b_l10[:5] if team_b_l10 else []

        # Auto-determine line from L10 average — use standard lines when available
        # to avoid circular reasoning (line = avg → ~50% hit rate by construction)
        stat_key_for_line = stat_a_key or stat_b_key or ""
        if is_combined and team_a_l10 and team_b_l10:
            min_len = min(len(team_a_l10), len(team_b_l10))
            combined_avg = sum(
                team_a_l10[i] + team_b_l10[i] for i in range(min_len)
            ) / min_len
            std_line = _find_closest_standard_line(sport, stat_key_for_line, combined_avg, is_combined=True)
            line = std_line if std_line is not None else _round_to_half(combined_avg)
        elif team_a_l10:
            avg = sum(team_a_l10) / len(team_a_l10)
            std_line = _find_closest_standard_line(sport, stat_key_for_line, avg, is_combined=False)
            line = std_line if std_line is not None else _round_to_half(avg)
        elif team_b_l10:
            avg = sum(team_b_l10) / len(team_b_l10)
            std_line = _find_closest_standard_line(sport, stat_key_for_line, avg, is_combined=False)
            line = std_line if std_line is not None else _round_to_half(avg)
        else:
            continue

        # Replace Team A/B placeholders with actual team names
        market_name = market_def["name"]
        market_name = market_name.replace("Team A", team_a).replace("Team B", team_b)

        built_markets.append({
            "name": market_name,
            "line": line,
            "team_a_l10": team_a_l10,
            "team_b_l10": team_b_l10,
            "h2h_values": h2h_values,
            "team_a_l5": team_a_l5,
            "team_b_l5": team_b_l5,
            "is_combined": is_combined,
            "source": source,
            "team_swapped": bool(stat_b_key and not stat_a_key),
        })

    if not built_markets:
        print(f"[normalize] No markets could be built for {team_a} vs {team_b}")
        return None

    return {
        "sport": sport,
        "team_a": team_a,
        "team_b": team_b,
        "competition": competition,
        "markets": built_markets,
    }


# ---------------------------------------------------------------------------
# Cache-based builder
# ---------------------------------------------------------------------------

def _slugify(name: str) -> str:
    """Convert team name to filesystem-safe slug (mirrors build_stats_cache.py)."""
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")


# ---------------------------------------------------------------------------
# DB-first safety input helpers
# ---------------------------------------------------------------------------

def _strip_ha_suffix(stat_key: str) -> tuple[str, str | None]:
    """Strip _home/_away suffix from a DB stat_key.

    Returns (bare_key, side) where side is "home", "away", or None.
    """
    if stat_key.endswith("_home"):
        return stat_key[:-5], "home"
    if stat_key.endswith("_away"):
        return stat_key[:-5], "away"
    return stat_key, None


def _synthesize_l10(
    l10_avg: float, l5_avg: float | None, count: int = 10,
    seed_key: str = "",
) -> list[float]:
    """Generate synthetic per-match values from aggregates.

    Creates `count` values centered on l10_avg with deterministic spread
    derived from the L10/L5 delta. Uses seed_key (team name) to produce
    team-specific noise so different teams don't get identical values.
    """
    if l10_avg == 0:
        return [0.0] * count

    if l5_avg is not None and l10_avg > 0:
        delta = abs(l5_avg - l10_avg)
        spread = max(delta, l10_avg * 0.1)
    else:
        spread = max(l10_avg * 0.15, 0.5)

    # Team-specific noise from hash of seed_key
    import hashlib
    seed = int(hashlib.md5(seed_key.encode()).hexdigest()[:8], 16) if seed_key else 0
    noise_bits = [(seed >> i) & 1 for i in range(count)]

    values = []
    for i in range(count):
        base_offset = spread * (1 - 2 * (i % 2)) * ((i // 2 + 1) / (count // 2))
        # Add small team-specific perturbation (±5% of spread)
        team_nudge = spread * 0.05 * (1 if noise_bits[i] else -1)
        values.append(round(l10_avg + base_offset + team_nudge, 1))

    if l5_avg is not None:
        l5_subset = values[:5]
        current_avg = sum(l5_subset) / 5
        if current_avg > 0:
            adjustment = l5_avg - current_avg
            # Shift each L5 value by the full adjustment to achieve target L5 average
            values[:5] = [round(v + adjustment, 1) for v in l5_subset]

    return values


def _build_markets_from_db_form(
    sport: str,
    team_a: str,
    team_b: str,
    team_a_form: list,
    team_b_form: list,
    h2h_form: list,
    market_definitions: list[dict],
) -> tuple[list[dict], int]:
    """Convert DB TeamForm rows into market dicts matching build_safety_score_input() output."""
    # Group form rows by bare stat_key and side
    def _group_form(form_rows):
        grouped = {}
        for row in form_rows:
            bare, side = _strip_ha_suffix(row.stat_key)
            grouped.setdefault(bare, {})[side] = row
        return grouped

    a_grouped = _group_form(team_a_form)
    b_grouped = _group_form(team_b_form)

    # Group H2H rows by bare stat_key (H2H rows typically don't have _home/_away)
    h2h_by_stat = {}
    for row in h2h_form:
        bare, _ = _strip_ha_suffix(row.stat_key)
        h2h_by_stat.setdefault(bare, []).append(row)

    built_markets = []
    synthetic_count = 0

    for market_def in market_definitions:
        stat_a_key = market_def.get("stat_a")
        stat_b_key = market_def.get("stat_b")
        is_combined = market_def.get("is_combined", True)

        team_a_l10 = []
        team_b_l10 = []
        source = "db"

        # Extract team_a values (home side)
        if stat_a_key:
            a_forms = a_grouped.get(stat_a_key, {})
            # Prefer _home row; fall back to bare key
            row_a = a_forms.get("home") or a_forms.get(None)
            if row_a:
                if row_a.l10_values and len(row_a.l10_values) >= 3:
                    team_a_l10 = row_a.l10_values[:10]
                elif row_a.l10_avg is not None:
                    team_a_l10 = _synthesize_l10(row_a.l10_avg, row_a.l5_avg, seed_key=team_a)
                    source = "db-synthetic"
                    synthetic_count += 1

        # Extract team_b values (away side)
        if stat_b_key:
            b_forms = b_grouped.get(stat_b_key, {})
            # Prefer _away row; fall back to bare key
            row_b = b_forms.get("away") or b_forms.get(None)
            if row_b:
                if row_b.l10_values and len(row_b.l10_values) >= 3:
                    team_b_l10 = row_b.l10_values[:10]
                elif row_b.l10_avg is not None:
                    team_b_l10 = _synthesize_l10(row_b.l10_avg, row_b.l5_avg, seed_key=team_b)
                    source = "db-synthetic"
                    synthetic_count += 1

        # For non-combined Team B-only markets, swap into team_a_l10
        team_swapped = False
        if not is_combined and stat_b_key and not stat_a_key:
            team_a_l10 = team_b_l10
            team_b_l10 = []
            team_swapped = True

        # Skip market if insufficient stat data
        if stat_a_key and len(team_a_l10) < 5:
            continue
        if stat_b_key and not stat_a_key and len(team_a_l10) < 5:
            continue
        if stat_b_key and stat_a_key and len(team_b_l10) < 5:
            continue

        # H2H values
        h2h_values = []
        h2h_stat = stat_a_key or stat_b_key
        if h2h_stat and h2h_stat in h2h_by_stat:
            for h_row in h2h_by_stat[h2h_stat]:
                if h_row.h2h_values:
                    h2h_values.extend(h_row.h2h_values)
                elif h_row.l10_avg is not None:
                    h2h_values.append(h_row.l10_avg)

        # L5 subsets
        team_a_l5 = team_a_l10[:5] if team_a_l10 else []
        team_b_l5 = team_b_l10[:5] if team_b_l10 else []

        # Auto-determine line — prefer standard market lines to avoid circular reasoning
        stat_key_for_line = stat_a_key or stat_b_key
        if is_combined and team_a_l10 and team_b_l10:
            min_len = min(len(team_a_l10), len(team_b_l10))
            combined_avg = sum(
                team_a_l10[i] + team_b_l10[i] for i in range(min_len)
            ) / min_len
            # Use standard line if available (prevents circular reasoning)
            std_line = _find_closest_standard_line(sport, stat_key_for_line, combined_avg, is_combined=True)
            line = std_line if std_line is not None else _round_to_half(combined_avg)
        elif team_a_l10:
            avg = sum(team_a_l10) / len(team_a_l10)
            std_line = _find_closest_standard_line(sport, stat_key_for_line, avg, is_combined=False)
            line = std_line if std_line is not None else _round_to_half(avg)
        elif team_b_l10:
            avg = sum(team_b_l10) / len(team_b_l10)
            std_line = _find_closest_standard_line(sport, stat_key_for_line, avg, is_combined=False)
            line = std_line if std_line is not None else _round_to_half(avg)
        else:
            continue

        # Replace placeholders in market name
        market_name = market_def["name"]
        market_name = market_name.replace("Team A", team_a).replace("Team B", team_b)
        market_name = market_name.replace("Player A", team_a).replace("Player B", team_b)
        market_name = market_name.replace("Fighter A", team_a).replace("Fighter B", team_b)
        market_name = market_name.replace("Pair A", team_a).replace("Pair B", team_b)

        # Detect one-sided data: combined market where one team has no data
        one_sided = False
        if is_combined and stat_a_key and stat_b_key:
            if not team_b_l10 or all(v == 0.0 for v in team_b_l10):
                one_sided = True
            elif not team_a_l10 or all(v == 0.0 for v in team_a_l10):
                one_sided = True

        built_markets.append({
            "name": market_name,
            "line": line,
            "team_a_l10": team_a_l10,
            "team_b_l10": team_b_l10,
            "h2h_values": h2h_values,
            "team_a_l5": team_a_l5,
            "team_b_l5": team_b_l5,
            "is_combined": is_combined,
            "source": source,
            "team_swapped": team_swapped,
            "one_sided": one_sided,
        })

    return built_markets, synthetic_count


def build_safety_input_from_db(
    sport: str,
    team_a: str,
    team_b: str,
    competition: str,
) -> dict | None:
    """Build safety score input from the SQLite DB (team_form rows).

    Returns dict matching build_safety_score_input() output format, or None
    on any DB error or missing data.
    """
    try:
        from bet.db.connection import get_db
        from bet.db.repositories import SportRepo, TeamRepo, StatsRepo
    except ImportError:
        return None

    try:
        with get_db() as conn:
            sport_repo = SportRepo(conn)
            team_repo = TeamRepo(conn)
            stats_repo = StatsRepo(conn)

            # Resolve sport
            sport_obj = sport_repo.get_by_name(sport)
            if not sport_obj or sport_obj.id is None:
                return None

            # Resolve teams
            team_a_obj = team_repo.resolve(team_a, sport_obj.id)
            team_b_obj = team_repo.resolve(team_b, sport_obj.id)
            if not team_a_obj or not team_b_obj:
                return None

            # Fetch team_form rows (non-H2H)
            team_a_form = stats_repo.get_all_form_for_team(team_a_obj.id, sport_obj.id)
            team_b_form = stats_repo.get_all_form_for_team(team_b_obj.id, sport_obj.id)

            if not team_a_form and not team_b_form:
                return None

            # Fetch H2H form rows
            h2h_form = []
            h2h_rows = conn.execute(
                "SELECT * FROM team_form "
                "WHERE team_id = ? AND sport_id = ? AND h2h_opponent_id = ?",
                (team_a_obj.id, sport_obj.id, team_b_obj.id),
            ).fetchall()
            for row in h2h_rows:
                h2h_form.append(StatsRepo._row_to_team_form(row))

            # Build markets
            market_definitions = SPORT_MARKETS.get(sport, [])
            if not market_definitions:
                return None

            built_markets, synthetic_count = _build_markets_from_db_form(
                sport, team_a, team_b,
                team_a_form, team_b_form, h2h_form,
                market_definitions,
            )

            if not built_markets:
                return None

            print(f"[normalize] DB-first: {len(built_markets)} markets for {team_a} vs {team_b} ({synthetic_count} synthetic)")

            return {
                "sport": sport,
                "team_a": team_a,
                "team_b": team_b,
                "competition": competition,
                "markets": built_markets,
            }
    except Exception as e:
        print(f"[normalize] DB-first error for {team_a} vs {team_b}: {e}")
        return None


def build_safety_input(
    sport: str,
    team_a: str,
    team_b: str,
    competition: str,
    cache_dir: Path | None = None,
) -> dict | None:
    """DB-first wrapper with JSON cache fallback."""
    result = build_safety_input_from_db(sport, team_a, team_b, competition)
    if result and result.get("markets"):
        return result
    return build_safety_input_from_cache(sport, team_a, team_b, competition, cache_dir)


def _cache_to_normalized_matches(
    cache_data: dict, team_name: str, sport: str
) -> list[NormalizedMatchStats]:
    """Convert stats cache format to list of NormalizedMatchStats.

    Supports both old format (form.recent_matches) and new extended format
    (form.l10_matches) from update_from_api().
    """
    matches = []
    form = cache_data.get("form", {})
    # New format takes precedence
    recent = form.get("l10_matches", form.get("recent_matches", []))

    for i, match in enumerate(recent):
        stats = {}
        # Support both flat stats at match level and nested under "stats" key
        match_stats = match.get("stats", match)
        for key in SPORT_STAT_KEYS.get(sport, []):
            if key in match_stats:
                val = match_stats[key]
                if isinstance(val, dict):
                    stats[key] = val
                else:
                    stats[key] = {"home": val, "away": 0}
        if stats:
            matches.append(NormalizedMatchStats(
                fixture_id=match.get("fixture_id", f"cache-{i}"),
                source="cache",
                sport=sport,
                home_team=team_name,
                away_team=match.get("opponent", "Unknown"),
                date=match.get("date", ""),
                stats=stats,
            ))

    return matches


def _load_team_id_lookup(cache_dir: Path, sport: str) -> dict[str, int]:
    """Load team-name → API-team-id mapping from _team_ids/*.json.

    Returns dict mapping lowercased team name to integer team ID.
    """
    ids_dir = cache_dir / "_team_ids"
    if not ids_dir.is_dir():
        return {}
    lookup: dict[str, int] = {}
    for id_file in ids_dir.glob("*.json"):
        # Only load files matching the sport (api-football.json → football)
        stem = id_file.stem  # e.g. "api-football"
        file_sport = stem.replace("api-", "") if stem.startswith("api-") else stem
        if file_sport != sport:
            continue
        try:
            data = json.loads(id_file.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for name, tid in data.items():
                    lookup[name.lower()] = int(tid)
        except (json.JSONDecodeError, OSError, ValueError):
            pass
    return lookup


def build_safety_from_api_cache(
    sport: str,
    team_a: str,
    team_b: str,
    competition: str,
    cache_dir: Path | None = None,
) -> dict | None:
    """Fallback: build safety score input from raw API cache files.

    Reads team IDs from _team_ids/, fixture lists from team_fixtures/,
    per-fixture stats from stats/, and H2H from h2h/.

    Returns:
        Safety score input dict, or None if insufficient data.
    """
    cache_dir = cache_dir or CACHE_DIR
    id_lookup = _load_team_id_lookup(cache_dir, sport)
    if not id_lookup:
        return None

    # Resolve team IDs (try exact, then slug match)
    team_a_id = id_lookup.get(team_a.lower()) or id_lookup.get(_slugify(team_a))
    team_b_id = id_lookup.get(team_b.lower()) or id_lookup.get(_slugify(team_b))
    if not team_a_id and not team_b_id:
        return None  # Need at least one team ID

    def _read_fixture_stats(sport_name: str, fixture_ids: list[str]) -> list[NormalizedMatchStats]:
        """Read per-fixture NormalizedMatchStats from stats cache."""
        matches = []
        stats_dir = cache_dir / sport_name / "stats"
        if not stats_dir.is_dir():
            return matches
        for fid in fixture_ids:
            stats_file = stats_dir / f"{fid}.json"
            if not stats_file.exists():
                continue
            try:
                data = json.loads(stats_file.read_text(encoding="utf-8"))
                ms = data.get("match_stats")
                if ms and isinstance(ms, dict):
                    matches.append(NormalizedMatchStats(**ms))
            except (json.JSONDecodeError, OSError, TypeError):
                pass
        return matches

    def _read_team_fixtures(sport_name: str, team_id: int) -> list[str]:
        """Read fixture IDs from team_fixtures cache."""
        tf_file = cache_dir / sport_name / "team_fixtures" / f"{team_id}_last10.json"
        if not tf_file.exists():
            return []
        try:
            data = json.loads(tf_file.read_text(encoding="utf-8"))
            return [
                f.get("fixture_id", "")
                for f in data.get("fixtures", [])
                if f.get("fixture_id")
            ]
        except (json.JSONDecodeError, OSError):
            return []

    # Collect fixture stats for each team
    team_a_matches: list[NormalizedMatchStats] = []
    team_b_matches: list[NormalizedMatchStats] = []

    if team_a_id:
        fids = _read_team_fixtures(sport, team_a_id)
        team_a_matches = _read_fixture_stats(sport, fids)
    if team_b_id:
        fids = _read_team_fixtures(sport, team_b_id)
        team_b_matches = _read_fixture_stats(sport, fids)

    # H2H data
    h2h_matches: list[NormalizedMatchStats] = []
    if team_a_id and team_b_id:
        # Try both orderings of ID pair
        for id_pair in [f"{team_a_id}-{team_b_id}", f"{team_b_id}-{team_a_id}"]:
            h2h_file = cache_dir / sport / "h2h" / f"{id_pair}.json"
            if h2h_file.exists():
                try:
                    data = json.loads(h2h_file.read_text(encoding="utf-8"))
                    h2h_fids = [
                        f.get("fixture_id", "")
                        for f in data.get("fixtures", [])
                        if f.get("fixture_id")
                    ]
                    h2h_matches = _read_fixture_stats(sport, h2h_fids)
                except (json.JSONDecodeError, OSError):
                    pass
                break

    # Only proceed if we have enough data
    if len(team_a_matches) < 5 and len(team_b_matches) < 5:
        return None

    return build_safety_score_input(
        sport=sport,
        team_a=team_a,
        team_b=team_b,
        competition=competition,
        team_a_matches=team_a_matches,
        team_b_matches=team_b_matches,
        h2h_matches=h2h_matches,
        source="api_cache",
    )


def _find_cache_file(sport_dir: Path, slug: str) -> Path | None:
    """Find cache file for a team slug, with fuzzy matching fallback.

    Tries exact match first, then checks if slug is a substring of any
    cache filename (or vice versa) to handle naming differences
    (e.g., 'sk-rapid-wien' → 'rapid-vienna.json').
    """
    exact = sport_dir / f"{slug}.json"
    if exact.exists():
        return exact

    if not sport_dir.is_dir():
        return None

    # Extract core name tokens (skip common prefixes like fc, sc, sk, etc.)
    skip_prefixes = {"fc", "sc", "sk", "fk", "ac", "as", "us", "ss", "cd", "cf", "rc", "rb"}
    slug_parts = [p for p in slug.split("-") if p not in skip_prefixes and len(p) > 1]

    best_match = None
    best_score = 0
    for f in sport_dir.glob("*.json"):
        stem = f.stem
        # Skip date-prefixed files (e.g. may-04-2030-lask-linz.json)
        # Pattern: 3-letter month + dash + 2-digit day (jan-01, feb-14, etc.)
        if re.match(r'^[a-z]{3}-\d{2}', stem):
            continue
        stem_parts = [p for p in stem.split("-") if p not in skip_prefixes and len(p) > 1]
        # Score = number of matching parts
        common = sum(1 for p in slug_parts if p in stem_parts)
        min_required = max(2, (len(slug_parts) * 2 + 2) // 3)  # ≥2/3 of tokens, minimum 2
        if common > best_score and common >= min_required:
            best_score = common
            best_match = f

    return best_match


def build_safety_input_from_cache(
    sport: str,
    team_a: str,
    team_b: str,
    competition: str,
    cache_dir: Path | None = None,
) -> dict | None:
    """Build safety score input from cached team data.

    Reads from betting/data/stats_cache/{sport}/{team_slug}.json.
    Falls back to raw API cache files if slug-based cache is missing.

    Returns:
        Safety score input dict, or None if cache miss or insufficient data.
    """
    cache_dir = cache_dir or CACHE_DIR
    slug_a = _slugify(team_a)
    slug_b = _slugify(team_b)

    cache_file_a = _find_cache_file(cache_dir / sport, slug_a)
    cache_file_b = _find_cache_file(cache_dir / sport, slug_b)

    if not cache_file_a or not cache_file_b:
        # Fallback: try raw API cache files
        return build_safety_from_api_cache(sport, team_a, team_b, competition, cache_dir)

    try:
        cache_a = json.loads(cache_file_a.read_text(encoding="utf-8"))
        cache_b = json.loads(cache_file_b.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"[normalize] Cache read error: {e}")
        return None

    team_a_matches = _cache_to_normalized_matches(cache_a, team_a, sport)
    team_b_matches = _cache_to_normalized_matches(cache_b, team_b, sport)

    # Extract H2H from cache (supports both old and new formats)
    h2h_matches = []
    h2h_data = cache_a.get("h2h", {}).get(_slugify(team_b), {})
    h2h_recent = h2h_data.get("matches", [])
    for i, match in enumerate(h2h_recent):
        stats = {}
        # Support both flat stats at match level and nested under "stats" key
        h2h_match_stats = match.get("stats", match)
        for key in SPORT_STAT_KEYS.get(sport, []):
            if key in h2h_match_stats:
                val = h2h_match_stats[key]
                if isinstance(val, dict):
                    stats[key] = val
                else:
                    stats[key] = {"home": val, "away": 0}
        if stats:
            h2h_matches.append(NormalizedMatchStats(
                fixture_id=match.get("fixture_id", f"h2h-{i}"),
                source="cache",
                sport=sport,
                home_team=team_a,
                away_team=team_b,
                date=match.get("date", ""),
                stats=stats,
            ))

    return build_safety_score_input(
        sport=sport,
        team_a=team_a,
        team_b=team_b,
        competition=competition,
        team_a_matches=team_a_matches,
        team_b_matches=team_b_matches,
        h2h_matches=h2h_matches,
        source="cache",
    )
