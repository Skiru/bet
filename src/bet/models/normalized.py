"""Normalized data structures for multi-source sports stats.

These dataclasses define the canonical format for fixture data, match stats,
odds, player stats, and standings across all API sources in the pipeline.
"""

from dataclasses import dataclass, field


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


@dataclass
class NormalizedOdds:
    """Normalized odds from any source (ESPN, the-odds-api, etc.)."""
    event_id: str
    source: str  # "espn-odds", "the-odds-api", "api-football-odds"
    sport: str
    home_team: str
    away_team: str
    bookmaker: str  # provider name (e.g., "DraftKings", "FanDuel")
    timestamp: str  # ISO datetime of odds snapshot
    markets: dict = field(default_factory=dict)
    # markets structure:
    # {
    #   "moneyline": {"home": decimal_odds, "away": decimal_odds, "draw": decimal_odds | None},
    #   "spread": {"home": decimal_odds, "away": decimal_odds, "line": float},
    #   "totals": {"over": decimal_odds, "under": decimal_odds, "line": float},
    # }
    opening_line: dict = field(default_factory=dict)  # Same structure as markets, for line movement


@dataclass
class NormalizedPlayerStats:
    """Normalized player performance data from gamelogs/splits."""
    athlete_id: str
    athlete_name: str
    source: str  # "espn-stats"
    sport: str
    team: str
    season: str
    games: list = field(default_factory=list)  # gamelog entries [{date, opponent, stats: {}}]
    splits: dict = field(default_factory=dict)  # {"home": {stat: avg}, "away": {stat: avg}}
    averages: dict = field(default_factory=dict)  # season averages {stat: value}


@dataclass
class NormalizedStandings:
    """Normalized league standings with form data."""
    sport: str
    league: str
    season: str
    source: str  # "espn-standings"
    teams: list = field(default_factory=list)
    # Each team entry: {
    #   "name": str, "rank": int,
    #   "wins": int, "draws": int, "losses": int,
    #   "goals_for": int, "goals_against": int, "goal_diff": int, "points": int,
    #   "form": str,  # e.g. "WWDLW"
    #   "home": {"wins": int, "draws": int, "losses": int},
    #   "away": {"wins": int, "draws": int, "losses": int},
    #   "streak": str,  # e.g. "W3"
    # }
