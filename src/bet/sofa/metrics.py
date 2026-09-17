from typing import Any
from bet.sofa.contracts import GapReason

FOOTBALL_METRICS = {
    "goals_total": {"sofascore": "goals_from_listing", "is_total": True},
    "goals_for": {"sofascore": "goals_from_listing", "is_total": False},
    "goals_1h_total": {"sofascore": "goals_1h_from_listing", "is_total": True},
    "goals_1h_for": {"sofascore": "goals_1h_from_listing", "is_total": False},
    "goals_2h_total": {"sofascore": "goals_2h_from_listing", "is_total": True},
    "goals_2h_for": {"sofascore": "goals_2h_from_listing", "is_total": False},
    "corners_total": {"sofascore": "cornerKicks", "is_total": True},
    "corners_for": {"sofascore": "cornerKicks", "is_total": False},
    "cards_total": {"sofascore": "yellowCards", "is_total": True},
    "cards_for": {"sofascore": "yellowCards", "is_total": False},
    "cards_points_total": {"sofascore": "cards_points_from_incidents", "is_total": True},
    "cards_points_for": {"sofascore": "cards_points_from_incidents", "is_total": False},
    "fouls_total": {"sofascore": "fouls", "is_total": True},
    "fouls_for": {"sofascore": "fouls", "is_total": False},
    "offsides_total": {"sofascore": "offsides", "is_total": True},
    "offsides_for": {"sofascore": "offsides", "is_total": False},
    "shots_total": {"sofascore": "totalShotsOnGoal", "is_total": True},
    "shots_for": {"sofascore": "totalShotsOnGoal", "is_total": False},
    "shots_on_target_total": {"sofascore": "shotsOnGoal", "is_total": True},
    "shots_on_target_for": {"sofascore": "shotsOnGoal", "is_total": False},
    "xg_total": {"sofascore": "expectedGoals", "is_total": True},
    "xg_for": {"sofascore": "expectedGoals", "is_total": False}
}

TENNIS_METRICS = {
    "games_total": {"sofascore": "gamesWon", "is_total": True},
    "games_won_for": {"sofascore": "gamesWon", "is_total": False},
    "sets_total": {"sofascore": "sets_from_listing", "is_total": True},
    "aces_total": {"sofascore": "aces", "is_total": True},
    "aces_for": {"sofascore": "aces", "is_total": False},
    "double_faults_total": {"sofascore": "doubleFaults", "is_total": True},
    "double_faults_for": {"sofascore": "doubleFaults", "is_total": False},
    "tiebreaks_total": {"sofascore": "tiebreaks", "is_total": True}
}

def extract_flat_statistics(statistics: dict[str, Any] | None) -> dict[str, dict[str, tuple[float, float]]]:
    flat = {}
    if not statistics:
        return flat
    for period in statistics.get("statistics", []):
        period_name = period.get("period", "ALL")
        flat[period_name] = {}
        for group in period.get("groups", []):
            for item in group.get("statisticsItems", []):
                key = item.get("key")
                if key:
                    try:
                        home = float(item.get("homeValue", 0))
                        away = float(item.get("awayValue", 0))
                        flat[period_name][key] = (home, away)
                    except ValueError:
                        pass
    return flat

def calculate_cards_points(incidents: dict[str, Any] | None) -> tuple[float, float] | GapReason:
    if incidents is None:
        return GapReason.NO_INCIDENTS
        
    home = 0.0
    away = 0.0
    
    for inc in incidents.get("incidents", []):
        if inc.get("incidentType") != "card":
            continue
        if inc.get("rescinded", False):
            continue
            
        pts = 0
        cls = inc.get("incidentClass")
        if cls == "yellow":
            pts = 1
        elif cls == "red":
            pts = 2
        elif cls == "yellowRed":
            pts = 2
            
        if inc.get("isHome", False):
            home += pts
        else:
            away += pts
            
    return home, away

def check_identities(
    flat_stats: dict[str, dict[str, tuple[float, float]]], 
    incidents: dict[str, Any] | None, 
    listing_event: dict[str, Any],
    sport: str
) -> GapReason | None:
    if "ALL" in flat_stats:
        stats = flat_stats["ALL"]
        if "totalShotsOnGoal" in stats and "shotsOnGoal" in stats and "shotsOffGoal" in stats and "blockedScoringAttempt" in stats:
            for side in (0, 1):
                s_on = stats["shotsOnGoal"][side]
                s_off = stats["shotsOffGoal"][side]
                s_blk = stats["blockedScoringAttempt"][side]
                s_tot = stats["totalShotsOnGoal"][side]
                if s_on + s_off + s_blk != s_tot:
                    return GapReason.INTERNAL_INCONSISTENT
                    
    if sport == "football" and incidents is not None:
        goal_incs = sum(1 for i in incidents.get("incidents", []) if i.get("incidentType") == "goal" and not i.get("rescinded", False))
        hs = listing_event.get("homeScore", {})
        as_ = listing_event.get("awayScore", {})
        
        c_h = hs.get("current")
        c_a = as_.get("current")
        
        if c_h is not None and c_a is not None:
            # Extra time / penalties goals might be excluded or included. 
            # In regular matches without ET, current = normaltime.
            if hs.get("normaltime") is not None and hs.get("normaltime") == c_h:
                if goal_incs != c_h + c_a:
                    return GapReason.INTERNAL_INCONSISTENT

    if sport == "football":
        hs = listing_event.get("homeScore", {})
        if "period1" in hs and "period2" in hs and "normaltime" in hs:
            if hs["period1"] + hs["period2"] != hs["normaltime"]:
                return GapReason.INTERNAL_INCONSISTENT
                
    if sport == "tennis":
        if "ALL" in flat_stats and "gamesWon" in flat_stats["ALL"]:
            hs = listing_event.get("homeScore", {})
            as_ = listing_event.get("awayScore", {})
            set_keys = [f"period{i}" for i in range(1, 6)]
            home_sets = sum(hs.get(k, 0) for k in set_keys if k in hs)
            away_sets = sum(as_.get(k, 0) for k in set_keys if k in as_)
            
            # tiebreak games might need to be included? 
            # The rule says: "suma gamesWon obu stron == suma gemów z wyniku setowego"
            # periodNTieBreak contains points, not games. The set score (e.g. 7-6) already includes the tiebreak game.
            
            home_stat = flat_stats["ALL"]["gamesWon"][0]
            away_stat = flat_stats["ALL"]["gamesWon"][1]
            if home_sets != home_stat or away_sets != away_stat:
                return GapReason.INTERNAL_INCONSISTENT

    return None

def extract_metric(
    metric_name: str,
    sport: str,
    flat_stats: dict[str, dict[str, tuple[float, float]]],
    incidents: dict[str, Any] | None,
    listing_event: dict[str, Any],
    is_home: bool
) -> float | GapReason:
    metrics_map = FOOTBALL_METRICS if sport == "football" else TENNIS_METRICS
    if metric_name not in metrics_map:
        return GapReason.STAT_KEY_ABSENT
        
    config = metrics_map[metric_name]
    sofascore_key = config["sofascore"]
    is_total = config["is_total"]
    
    if sofascore_key == "goals_from_listing":
        h = listing_event.get("homeScore", {}).get("current")
        a = listing_event.get("awayScore", {}).get("current")
        if h is None or a is None:
            return GapReason.STAT_KEY_ABSENT
        return float(h + a) if is_total else float(h if is_home else a)
        
    if sofascore_key == "goals_1h_from_listing":
        h = listing_event.get("homeScore", {}).get("period1")
        a = listing_event.get("awayScore", {}).get("period1")
        if h is None or a is None:
            return GapReason.STAT_KEY_ABSENT
        return float(h + a) if is_total else float(h if is_home else a)
        
    if sofascore_key == "goals_2h_from_listing":
        h = listing_event.get("homeScore", {}).get("period2")
        a = listing_event.get("awayScore", {}).get("period2")
        if h is None or a is None:
            return GapReason.STAT_KEY_ABSENT
        return float(h + a) if is_total else float(h if is_home else a)
        
        
    if sofascore_key == "cards_points_from_incidents":
        pts = calculate_cards_points(incidents)
        if isinstance(pts, GapReason):
            return pts
        h, a = pts
        return float(h + a) if is_total else float(h if is_home else a)
        
    if sofascore_key == "sets_from_listing":
        hs = listing_event.get("homeScore", {})
        as_ = listing_event.get("awayScore", {})
        set_keys = [f"period{i}" for i in range(1, 6)]
        home_sets = sum(1 for k in set_keys if k in hs)
        away_sets = sum(1 for k in set_keys if k in as_)
        # We need the number of sets played.
        # Since it's a total, it's just home_sets or wait. 
        # Both players play the same number of sets. The number of sets is the number of period keys present in either score.
        played_sets = len([k for k in set_keys if k in hs or k in as_])
        if played_sets == 0:
            return GapReason.STAT_KEY_ABSENT
        return float(played_sets)

    if sofascore_key == "expectedGoals" and not listing_event.get("hasXg", False):
        return GapReason.STAT_KEY_ABSENT
        
    # Default stats lookup
    if "ALL" not in flat_stats:
        return GapReason.NO_STATISTICS
        
    stats = flat_stats["ALL"]
    if sofascore_key not in stats:
        return GapReason.STAT_KEY_ABSENT
        
    h, a = stats[sofascore_key]
    return float(h + a) if is_total else float(h if is_home else a)

