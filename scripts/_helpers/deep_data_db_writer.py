"""Shared helper: convert UnifiedAPIClient deep data → DB records.

Used by data_enrichment_agent.py (Phase 1),
and enrichment.py (Phase 7) to persist API client output to DB.
"""

import logging
from datetime import datetime, timezone

from bet.db.repositories import StatsRepo
from bet.db.models import TeamForm

logger = logging.getLogger(__name__)

def persist_deep_data_to_db(
    conn,
    fixture_id: int,
    home_team_id: int,
    away_team_id: int,
    sport_id: int,
    deep_data: dict,
    source: str = "scan-deep",
) -> dict:
    """Convert deep data dict to DB records and persist.
    
    Args:
        conn: SQLite connection (with row_factory=sqlite3.Row)
        fixture_id: The fixture ID in the DB
        home_team_id: Home team's DB ID
        away_team_id: Away team's DB ID
        sport_id: Sport's DB ID
        deep_data: Dict from UnifiedAPIClient.get_deep_data() with keys:
            - "stats": list of dicts like [{"category": "Corners", "key": "corners", "home": "7", "away": "3"}, ...]
            - "form": {"homeTeam": {"form": ["W","D","L",...]}, "awayTeam": {"form": [...]}}
            - "h2h": {"teamDuel": [...]}
            - "odds": list (not persisted here — handled by OddsRepo)
        source: Source identifier for DB records
        
    Returns:
        {"match_stats_saved": N, "team_form_saved": M, "errors": [...]}
    """
    stats_repo = StatsRepo(conn)
    result = {"match_stats_saved": 0, "team_form_saved": 0, "errors": []}
    
    # 1. Persist match_stats
    stats_list = deep_data.get("stats") or []
    for stat_dict in stats_list:
        try:
            stat_key = stat_dict.get("key", "").lower().replace(" ", "_")
            if not stat_key:
                continue
                
            home_val_raw = stat_dict.get("home")
            away_val_raw = stat_dict.get("away")
            
            home_val = float(str(home_val_raw).replace(",", ".")) if home_val_raw is not None else None
            away_val = float(str(away_val_raw).replace(",", ".")) if away_val_raw is not None else None
            
            if home_val is not None:
                stats_repo.save_match_stats(fixture_id, home_team_id, {stat_key: home_val}, source)
                result["match_stats_saved"] += 1
            if away_val is not None:
                stats_repo.save_match_stats(fixture_id, away_team_id, {stat_key: away_val}, source)
                result["match_stats_saved"] += 1
                
        except (ValueError, TypeError) as e:
            # Skip non-numeric values gracefully
            logger.debug(f"Skipping non-numeric stat: {stat_dict} - {e}")
        except Exception as e:
            err_msg = f"Error saving stat {stat_dict}: {e}"
            logger.error(err_msg)
            result["errors"].append(err_msg)

    # 2. Persist team_form
    form_data = deep_data.get("form") or {}
    for team_key, team_id in [("homeTeam", home_team_id), ("awayTeam", away_team_id)]:
        team_info = form_data.get(team_key) or {}
        form_letters = team_info.get("form") or []
        
        if not form_letters:
            continue
            
        try:
            points_map = {"W": 3, "D": 1, "L": 0, "W (OT)": 2, "L (OT)": 1}
            numeric_form = []
            for letter in form_letters:
                val = points_map.get(str(letter).upper().strip())
                if val is not None:
                    numeric_form.append(float(val))
                else:
                    # Treat unknown as draw/1pt or just skip? Let's treat unknown as None and skip
                    pass
            
            if numeric_form:
                l10_values = numeric_form[:10]
                l5_values = numeric_form[:5]
                
                l10_avg = sum(l10_values) / len(l10_values) if l10_values else None
                l5_avg = sum(l5_values) / len(l5_values) if l5_values else None
                
                team_form = TeamForm(
                    id=None,
                    team_id=team_id,
                    sport_id=sport_id,
                    stat_key="form_points",
                    l10_values=l10_values,
                    l5_values=l5_values,
                    l10_avg=l10_avg,
                    l5_avg=l5_avg,
                    trend="".join(str(f) for f in form_letters[:5]),
                    updated_at=datetime.now(timezone.utc).isoformat(),
                    source=source
                )
                stats_repo.save_team_form(team_form)
                result["team_form_saved"] += 1
        except Exception as e:
            err_msg = f"Error saving form for {team_key}: {e}"
            logger.error(err_msg)
            result["errors"].append(err_msg)

    return result
