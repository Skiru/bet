"""
Unified fuzzy matching module for team and player names.
"""

from typing import Any
from rapidfuzz import fuzz

from bet.utils import normalize_team_name
from bet.db.connection import get_db
try:
    from bet.discovery.esports_aliases import resolve_alias
except ImportError:
    def resolve_alias(name: str) -> str:
        return name

SPORT_THRESHOLDS: dict[str, float] = {
    "tennis": 80.0,
    "football": 75.0,
    "basketball": 75.0,
    "hockey": 75.0,
    "volleyball": 75.0,
    "cs2": 85.0,
    "valorant": 85.0,
    "dota2": 85.0,
}

ESPORTS_SPORTS = {"cs2", "valorant", "dota2"}

def match_team(db_name: str, source_name: str, sport: str | None = None) -> tuple[float, str]:
    """Match a source team name against a DB team name.
    
    Returns (score 0-100, normalized_matched_name).
    Uses sport-specific thresholds internally but returns raw score for caller to decide.
    """
    normalized_db = normalize_team_name(db_name)
    normalized_source = normalize_team_name(source_name)
    
    if sport and sport.lower() in ESPORTS_SPORTS:
        normalized_db = resolve_alias(normalized_db)
        normalized_source = resolve_alias(normalized_source)
        
    score = fuzz.token_sort_ratio(normalized_db, normalized_source)
    return float(score), normalized_db


def resolve_team_in_db(source_name: str, sport: str, threshold: float | None = None) -> dict[str, Any] | None:
    """Search DB teams table for best match to source_name.
    
    Returns {"team_id": int, "db_name": str, "score": float} or None if below threshold.
    Uses get_db() to query teams table filtered by sport.
    Default thresholds per sport: tennis=80, football=75, esports=85, default=75.
    
    Optimization: checks name_mappings cache first (O(1) lookup) before falling
    back to expensive full-table fuzzy scan.
    """
    if threshold is None:
        threshold = SPORT_THRESHOLDS.get(sport.lower(), 75.0)

    # Fast path: check name_mappings cache first
    with get_db() as conn:
        cached = conn.execute(
            "SELECT db_team_id, db_name, match_score FROM name_mappings "
            "WHERE sport = ? AND source_name = ? LIMIT 1",
            (sport.lower(), source_name),
        ).fetchone()
        if cached and cached["match_score"] and cached["match_score"] >= threshold:
            return {
                "team_id": cached["db_team_id"],
                "db_name": cached["db_name"],
                "score": cached["match_score"],
            }

    # Slow path: full-table fuzzy scan
    best_match = None
    best_score = -1.0

    with get_db() as conn:
        rows = conn.execute(
            """SELECT t.id, t.name FROM teams t
               JOIN sports s ON t.sport_id = s.id
               WHERE LOWER(s.name) = LOWER(?)""",
            (sport,)
        ).fetchall()

        for row in rows:
            team_id = row["id"]
            db_name = row["name"]
            
            score, _ = match_team(db_name, source_name, sport)
            
            if score > best_score and score >= threshold:
                best_score = score
                best_match = {
                    "team_id": team_id,
                    "db_name": db_name,
                    "score": best_score
                }
                
                if score == 100.0:
                    break

    # Cache the result for future lookups
    if best_match:
        try:
            with get_db() as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO name_mappings (sport, source, db_team_id, source_name, db_name, match_score) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (sport.lower(), "fuzzy_match", best_match["team_id"],
                     source_name, best_match["db_name"], best_match["score"]),
                )
                conn.commit()
        except Exception:
            pass  # Cache write failure is non-fatal

    return best_match


def resolve_flashscore_entity(team_name: str, sport: str) -> str | None:
    """Resolve a team name to a Flashscore entity search query.
    
    Applies sport-specific normalization before returning the search-ready name.
    (This is a lightweight helper — actual Flashscore API calls happen in scrapers.)
    """
    if not team_name:
        return None
        
    normalized = normalize_team_name(team_name)
    
    if sport and sport.lower() in ESPORTS_SPORTS:
        normalized = resolve_alias(normalized)
        
    return normalized
