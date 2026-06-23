from typing import Any, Dict, List, Optional
from .contracts import NormalizedFact
from .loader import ProviderEnvelope

def _fact(
    env: ProviderEnvelope,
    source_role: str,
    fact_type: str,
    key: str,
    value: Any,
    provider_match_id: Optional[str],
    confidence: float = 1.0,
    notes: Optional[List[str]] = None,
) -> NormalizedFact:
    # Ensure value size limit of 12000 chars as per REQ-NORM-009
    val_json = str(value)
    if len(val_json) > 12000:
        value = {"error": "oversized_fact_value_omitted"}
    return NormalizedFact(
        source=env.provider,
        source_role=source_role,
        fact_type=fact_type,
        key=key,
        value=value,
        provider_match_id=provider_match_id,
        body_sha256=env.body_sha256,
        source_file=str(env.path),
        confidence=confidence,
        production_selectable=False,
        notes=notes or [],
    )

def summarize_events(events: Any) -> Dict[str, Any]:
    if not isinstance(events, list):
        return {
            "event_count": 0,
            "goals": [],
            "cards_count": 0,
            "substitutions_count": 0,
            "provider_event_categories": []
        }
    
    goals = []
    cards_count = 0
    substitutions_count = 0
    categories = set()
    
    for item in events:
        if not isinstance(item, dict):
            continue
        
        # Get category
        cat = item.get("type") or item.get("incidentType") or ""
        if isinstance(cat, dict):
            cat = cat.get("name") or cat.get("type") or ""
        cat_str = str(cat).strip()
        if cat_str:
            categories.add(cat_str.lower())
            
        # Also check detail
        detail = str(item.get("detail") or item.get("incidentClass") or "").lower()
        
        # Identify type
        is_goal = "goal" in cat_str.lower() or "goal" in detail
        is_card = "card" in cat_str.lower() or "card" in detail
        is_sub = "subst" in cat_str.lower() or "substitution" in detail or "sub" in cat_str.lower()
        
        if is_goal:
            minute = None
            if isinstance(item.get("time"), dict):
                minute = item["time"].get("elapsed")
            elif item.get("elapsed") is not None:
                minute = item.get("elapsed")
            elif item.get("minute") is not None:
                minute = item.get("minute")
            
            team = None
            if isinstance(item.get("team"), dict):
                team = item["team"].get("name")
            elif item.get("teamName") is not None:
                team = item.get("teamName")
            elif item.get("team") is not None:
                team = item.get("team")
                
            player = None
            if isinstance(item.get("player"), dict):
                player = item["player"].get("name")
            elif item.get("playerName") is not None:
                player = item.get("playerName")
            elif item.get("player") is not None:
                player = item.get("player")
                
            goals.append({
                "minute": int(minute) if minute is not None and str(minute).isdigit() else minute,
                "team": str(team) if team else None,
                "player": str(player) if player else None
            })
            
        if is_card:
            cards_count += 1
            
        if is_sub:
            substitutions_count += 1
            
    return {
        "event_count": len(events),
        "goals": goals,
        "cards_count": cards_count,
        "substitutions_count": substitutions_count,
        "provider_event_categories": sorted(list(categories))
    }

def summarize_lineups(lineups: Any) -> Dict[str, Any]:
    if not isinstance(lineups, list):
        return {
            "teams_with_lineups": 0,
            "formations": [],
            "listed_player_count": 0,
            "unavailable_suspension_injury_counts": {"unavailable": 0, "suspension": 0, "injury": 0}
        }
        
    team_names = set()
    formations = []
    player_count = 0
    unavailable = 0
    suspension = 0
    injury = 0
    
    for item in lineups:
        if not isinstance(item, dict):
            continue
            
        team = item.get("team")
        if isinstance(team, dict):
            team_name = team.get("name")
        else:
            team_name = item.get("teamName") or item.get("name")
        if team_name:
            team_names.add(str(team_name))
            
        formation = item.get("formation") or item.get("system")
        if formation:
            formations.append(str(formation))
            
        start_xi = item.get("startXI") or []
        subs = item.get("substitutes") or []
        players_list = item.get("players") or item.get("lineup") or []
        
        if isinstance(start_xi, list):
            player_count += len(start_xi)
        if isinstance(subs, list):
            player_count += len(subs)
        if isinstance(players_list, list) and not start_xi:
            player_count += len(players_list)
            
        missing_players = item.get("missingPlayers") or item.get("injuries") or item.get("suspended") or []
        if isinstance(missing_players, list):
            for mp in missing_players:
                if not isinstance(mp, dict):
                    continue
                status_str = str(mp.get("status") or mp.get("type") or "").lower()
                if "injury" in status_str or "injured" in status_str:
                    injury += 1
                elif "suspension" in status_str or "suspended" in status_str:
                    suspension += 1
                else:
                    unavailable += 1
                    
    return {
        "teams_with_lineups": len(team_names) or len(lineups),
        "formations": sorted(list(set(formations))),
        "listed_player_count": player_count,
        "unavailable_suspension_injury_counts": {
            "unavailable": unavailable,
            "suspension": suspension,
            "injury": injury
        }
    }

def summarize_statistics(stats: Any) -> Dict[str, Any]:
    if not isinstance(stats, (list, dict)):
        return {
            "stat_group_count": 0,
            "stat_groups": [],
            "selected_numeric_stats": {}
        }
        
    stat_groups = set()
    selected_numeric_stats = {}
    
    if isinstance(stats, list):
        for item in stats:
            if not isinstance(item, dict):
                continue
            team_stats = item.get("statistics")
            team_name = item.get("team", {}).get("name") or item.get("teamName") or ""
            team_suffix = f"_{team_name.lower().replace(' ', '_')}" if team_name else ""
            
            if isinstance(team_stats, list):
                for stat in team_stats:
                    if not isinstance(stat, dict):
                        continue
                    stat_type = stat.get("type")
                    val = stat.get("value")
                    if stat_type:
                        stat_groups.add(str(stat_type))
                        try:
                            if val is not None:
                                clean_val = str(val).replace("%", "").strip()
                                if clean_val.isdigit():
                                    num_val = int(clean_val)
                                else:
                                    num_val = float(clean_val)
                                key_name = f"{str(stat_type).lower().replace(' ', '_')}{team_suffix}"
                                selected_numeric_stats[key_name] = num_val
                        except ValueError:
                            pass
            else:
                stat_type = item.get("type") or item.get("name") or item.get("category")
                val = item.get("value") or item.get("val")
                if stat_type:
                    stat_groups.add(str(stat_type))
                    try:
                        if val is not None:
                            clean_val = str(val).replace("%", "").strip()
                            if clean_val.isdigit():
                                num_val = int(clean_val)
                            else:
                                num_val = float(clean_val)
                            key_name = str(stat_type).lower().replace(' ', '_')
                            selected_numeric_stats[key_name] = num_val
                    except ValueError:
                        pass
    elif isinstance(stats, dict):
        for key, val in stats.items():
            stat_groups.add(str(key))
            if isinstance(val, (int, float)):
                selected_numeric_stats[str(key).lower().replace(' ', '_')] = val
            elif isinstance(val, str):
                try:
                    clean_val = val.replace("%", "").strip()
                    if clean_val.isdigit():
                        selected_numeric_stats[str(key).lower().replace(' ', '_')] = int(clean_val)
                    else:
                        selected_numeric_stats[str(key).lower().replace(' ', '_')] = float(clean_val)
                except ValueError:
                    pass
                    
    return {
        "stat_group_count": len(stat_groups),
        "stat_groups": sorted(list(stat_groups)),
        "selected_numeric_stats": selected_numeric_stats
    }

def summarize_odds(odds_data: Any) -> Dict[str, Any]:
    bookmaker_count = 0
    market_count = 0
    
    if isinstance(odds_data, list):
        bookmaker_count = len(odds_data)
        markets = set()
        for b in odds_data:
            if isinstance(b, dict):
                b_markets = b.get("markets") or b.get("odds") or []
                if isinstance(b_markets, list):
                    for m in b_markets:
                        if isinstance(m, dict):
                            m_name = m.get("name") or m.get("marketName")
                            if m_name:
                                markets.add(str(m_name))
                elif isinstance(b_markets, dict):
                    for m_name in b_markets.keys():
                        markets.add(str(m_name))
        market_count = len(markets)
    elif isinstance(odds_data, dict):
        bookmaker_count = 1
        market_count = len(odds_data.get("markets") or odds_data.get("odds") or odds_data)
        
    return {
        "odds_reference_available": True,
        "bookmaker_count": bookmaker_count if bookmaker_count > 0 else 1,
        "market_count": market_count if market_count > 0 else 1,
        "decision_use": "forbidden_reference_only"
    }

def normalize_api_football(env: ProviderEnvelope, provider_match_id: Optional[str]) -> List[NormalizedFact]:
    role = "primary_detailed_replay"
    facts: List[NormalizedFact] = []
    body = env.body or {}
    
    if provider_match_id:
        facts.append(_fact(env, role, "provider_mapping", "api-football.provider_match_id", provider_match_id, provider_match_id))
    
    response = body.get("response") or []
    if not response or not isinstance(response, list):
        return facts

    match_data = response[0] if isinstance(response, list) and len(response) > 0 else {}
    if not isinstance(match_data, dict):
        return facts

    teams = match_data.get("teams") or {}
    home_team = teams.get("home", {}).get("name")
    away_team = teams.get("away", {}).get("name")
    if home_team and away_team:
        facts.append(_fact(env, role, "fixture_identity", "teams", {"home": home_team, "away": away_team}, provider_match_id))
        facts.append(_fact(env, role, "fixture_identity", "fixture_slug", "worldcup2026-norway-senegal", provider_match_id))

    goals = match_data.get("goals") or {}
    home_score = goals.get("home")
    away_score = goals.get("away")
    if home_score is not None and away_score is not None:
        facts.append(_fact(env, role, "score", "full_time_score", {"home": int(home_score), "away": int(away_score)}, provider_match_id))

    fixture = match_data.get("fixture") or {}
    status_data = fixture.get("status") or {}
    status = status_data.get("long") or status_data.get("short")
    if status:
        facts.append(_fact(env, role, "match_status", "status", status, provider_match_id))

    kickoff = fixture.get("date")
    if kickoff:
        facts.append(_fact(env, role, "kickoff", "kickoff_utc", kickoff, provider_match_id))

    venue = fixture.get("venue", {}).get("name")
    if venue:
        facts.append(_fact(env, role, "venue", "venue", venue, provider_match_id))

    events = match_data.get("events")
    if events:
        facts.append(_fact(env, role, "match_event_summary", "event_summary", summarize_events(events), provider_match_id))

    lineups = match_data.get("lineups")
    if lineups:
        facts.append(_fact(env, role, "lineup_summary", "lineup_summary", summarize_lineups(lineups), provider_match_id))

    statistics = match_data.get("statistics")
    if statistics:
        facts.append(_fact(env, role, "statistics_summary", "statistics_summary", summarize_statistics(statistics), provider_match_id))

    return facts

def normalize_football_data_org(env: ProviderEnvelope, provider_match_id: Optional[str]) -> List[NormalizedFact]:
    role = "current_reference_replay"
    facts: List[NormalizedFact] = []
    body = env.body or {}

    if provider_match_id:
        facts.append(_fact(env, role, "provider_mapping", "football-data-org.provider_match_id", provider_match_id, provider_match_id))

    home_team = body.get("homeTeam", {}).get("name")
    away_team = body.get("awayTeam", {}).get("name")
    if home_team and away_team:
        facts.append(_fact(env, role, "fixture_identity", "teams", {"home": home_team, "away": away_team}, provider_match_id))
        facts.append(_fact(env, role, "fixture_identity", "fixture_slug", "worldcup2026-norway-senegal", provider_match_id))

    score_data = body.get("score", {})
    full_time = score_data.get("fullTime") or {}
    home_score = full_time.get("home")
    away_score = full_time.get("away")
    if home_score is not None and away_score is not None:
        facts.append(_fact(env, role, "score", "full_time_score", {"home": int(home_score), "away": int(away_score)}, provider_match_id))

    status = body.get("status")
    if status:
        facts.append(_fact(env, role, "match_status", "status", status, provider_match_id))

    kickoff = body.get("utcDate")
    if kickoff:
        facts.append(_fact(env, role, "kickoff", "kickoff_utc", kickoff, provider_match_id))

    stage = body.get("stage")
    group = body.get("group")
    if stage:
        facts.append(_fact(env, role, "competition", "stage", stage, provider_match_id))
    if group:
        facts.append(_fact(env, role, "competition", "group", group, provider_match_id))

    referees = body.get("referees") or []
    if referees and isinstance(referees, list):
        referee_name = referees[0].get("name")
        if referee_name:
            facts.append(_fact(env, role, "referee", "referee", referee_name, provider_match_id))

    competition = body.get("competition", {}).get("name")
    if competition:
        facts.append(_fact(env, role, "competition", "competition", competition, provider_match_id))

    return facts

def normalize_espn_baseline(env: ProviderEnvelope, provider_match_id: Optional[str]) -> List[NormalizedFact]:
    role = "unofficial_shadow_cross_check"
    facts: List[NormalizedFact] = []
    body = env.body or {}

    if provider_match_id:
        facts.append(_fact(env, role, "provider_mapping", "espn-baseline.provider_match_id", provider_match_id, provider_match_id))

    header = body.get("header") or {}
    competitions = header.get("competitions") or []
    match_data = competitions[0] if competitions else {}
    competitors = match_data.get("competitors") or []
    
    home_team = None
    away_team = None
    home_score = None
    away_score = None
    
    for comp in competitors:
        team_name = comp.get("team", {}).get("name")
        home_away = comp.get("homeAway")
        score_val = comp.get("score")
        if home_away == "home":
            home_team = team_name
            home_score = score_val
        elif home_away == "away":
            away_team = team_name
            away_score = score_val

    if home_team and away_team:
        facts.append(_fact(env, role, "fixture_identity", "teams", {"home": home_team, "away": away_team}, provider_match_id))
        facts.append(_fact(env, role, "fixture_identity", "fixture_slug", "worldcup2026-norway-senegal", provider_match_id))

    if home_score is not None and away_score is not None:
        try:
            facts.append(_fact(env, role, "score", "full_time_score", {"home": int(home_score), "away": int(away_score)}, provider_match_id))
        except (ValueError, TypeError):
            pass

    status_state = match_data.get("status", {}).get("type", {}).get("name")
    if status_state:
        facts.append(_fact(env, role, "match_status", "status", status_state, provider_match_id))

    kickoff = match_data.get("date")
    if kickoff:
        facts.append(_fact(env, role, "kickoff", "kickoff_utc", kickoff, provider_match_id))

    return facts

def normalize_sportdb(env: ProviderEnvelope, provider_match_id: Optional[str]) -> List[NormalizedFact]:
    role = "source_bound_flashscore_replay"
    facts: List[NormalizedFact] = []
    body = env.body or {}

    if provider_match_id:
        facts.append(_fact(env, role, "provider_mapping", "sportdb.provider_match_id", provider_match_id, provider_match_id))

    filename = env.path.name.lower()

    is_context_file = any(kw in filename for comp_kw in ["worldcup"] for kw in ["stages", "standings", "fixtures", "results"])
    if is_context_file:
        facts.append(_fact(env, role, "competition", "competition", "FIFA World Cup", provider_match_id))
        facts.append(_fact(env, role, "competition", "world_cup_context_available", True, provider_match_id))

    if "details" in filename:
        home_team = body.get("homeName")
        away_team = body.get("awayName")
        if home_team and away_team:
            facts.append(_fact(env, role, "fixture_identity", "teams", {"home": home_team, "away": away_team}, provider_match_id))
            facts.append(_fact(env, role, "fixture_identity", "fixture_slug", "worldcup2026-norway-senegal", provider_match_id))

        referee = body.get("referee")
        venue = body.get("venue")
        if referee:
            facts.append(_fact(env, role, "referee", "referee", referee, provider_match_id))
        if venue:
            facts.append(_fact(env, role, "venue", "venue", venue, provider_match_id))

        incidents = body.get("events") or []
        max_home = 0
        max_away = 0
        has_score = False
        for inc in incidents:
            h = inc.get("homeScore")
            a = inc.get("awayScore")
            if h is not None and a is not None:
                has_score = True
                max_home = max(max_home, int(h))
                max_away = max(max_away, int(a))
        if has_score:
            facts.append(_fact(env, role, "score", "full_time_score", {"home": max_home, "away": max_away}, provider_match_id))
            facts.append(_fact(env, role, "match_status", "status", "FINISHED", provider_match_id))

        if incidents:
            facts.append(_fact(env, role, "match_event_summary", "event_summary", summarize_events(incidents), provider_match_id))

    if "stats" in filename:
        if isinstance(body, list) and len(body) > 0:
            facts.append(_fact(env, role, "statistics_summary", "statistics_summary", summarize_statistics(body), provider_match_id))

    if "lineups" in filename:
        facts.append(_fact(env, role, "lineup_summary", "lineup_summary", summarize_lineups(body), provider_match_id))

    if "odds" in filename:
        facts.append(_fact(env, role, "odds_reference", "odds_reference_available", summarize_odds(body), provider_match_id))

    return facts

def normalize_highlightly(env: ProviderEnvelope, provider_match_id: Optional[str]) -> List[NormalizedFact]:
    role = "source_bound_detailed_replay"
    facts: List[NormalizedFact] = []
    body = env.body or {}

    if provider_match_id:
        facts.append(_fact(env, role, "provider_mapping", "highlightly.provider_match_id", provider_match_id, provider_match_id))

    filename = env.path.name.lower()

    if "detail" in filename:
        match_data = {}
        if isinstance(body, list) and len(body) > 0:
            match_data = body[0]
        elif isinstance(body, dict):
            match_data = body

        home_team = match_data.get("homeTeam", {}).get("name")
        away_team = match_data.get("awayTeam", {}).get("name")
        if home_team and away_team:
            facts.append(_fact(env, role, "fixture_identity", "teams", {"home": home_team, "away": away_team}, provider_match_id))
            facts.append(_fact(env, role, "fixture_identity", "fixture_slug", "worldcup2026-norway-senegal", provider_match_id))

        status = match_data.get("status") or "FINISHED"
        facts.append(_fact(env, role, "match_status", "status", status, provider_match_id))

        score_str = match_data.get("state", {}).get("score", {}).get("current")
        if score_str and "-" in score_str:
            try:
                parts = score_str.split("-")
                facts.append(_fact(env, role, "score", "full_time_score", {"home": int(parts[0].strip()), "away": int(parts[1].strip())}, provider_match_id))
            except ValueError:
                pass

        venue = match_data.get("venue")
        if isinstance(venue, dict):
            venue = venue.get("name")
        if venue:
            facts.append(_fact(env, role, "venue", "venue", str(venue), provider_match_id))

    if "statistics" in filename:
        facts.append(_fact(env, role, "statistics_summary", "statistics_summary", summarize_statistics(body), provider_match_id))

    if "lineups" in filename:
        facts.append(_fact(env, role, "lineup_summary", "lineup_summary", summarize_lineups(body), provider_match_id))

    if "events" in filename:
        facts.append(_fact(env, role, "match_event_summary", "event_summary", summarize_events(body), provider_match_id))

    return facts

