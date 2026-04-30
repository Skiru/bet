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
    # Minimum match count validation
    if len(team_a_matches) < 5:
        print(f"[normalize] Insufficient data for {team_a}: {len(team_a_matches)} matches (need ≥5)")
        return None
    if len(team_b_matches) < 5:
        print(f"[normalize] Insufficient data for {team_b}: {len(team_b_matches)} matches (need ≥5)")
        return None

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

        # Auto-determine line from L10 average
        if is_combined and team_a_l10 and team_b_l10:
            min_len = min(len(team_a_l10), len(team_b_l10))
            combined_avg = sum(
                team_a_l10[i] + team_b_l10[i] for i in range(min_len)
            ) / min_len
            line = _round_to_half(combined_avg)
        elif team_a_l10:
            line = _round_to_half(sum(team_a_l10) / len(team_a_l10))
        elif team_b_l10:
            line = _round_to_half(sum(team_b_l10) / len(team_b_l10))
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


def build_safety_input_from_cache(
    sport: str,
    team_a: str,
    team_b: str,
    competition: str,
    cache_dir: Path | None = None,
) -> dict | None:
    """Build safety score input from cached team data.

    Reads from betting/data/stats_cache/{sport}/{team_slug}.json.

    Returns:
        Safety score input dict, or None if cache miss or insufficient data.
    """
    cache_dir = cache_dir or CACHE_DIR
    slug_a = _slugify(team_a)
    slug_b = _slugify(team_b)

    cache_file_a = cache_dir / sport / f"{slug_a}.json"
    cache_file_b = cache_dir / sport / f"{slug_b}.json"

    if not cache_file_a.exists():
        print(f"[normalize] Cache miss for {team_a} ({cache_file_a})")
        return None
    if not cache_file_b.exists():
        print(f"[normalize] Cache miss for {team_b} ({cache_file_b})")
        return None

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
