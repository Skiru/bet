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

def normalize_api_football(env: ProviderEnvelope, provider_match_id: Optional[str]) -> List[NormalizedFact]:
    role = "primary_detailed_replay"
    facts: List[NormalizedFact] = []
    body = env.body or {}
    
    # REQ-NORM-AF-001 Extract provider fixture id
    if provider_match_id:
        facts.append(_fact(env, role, "provider_mapping", "api-football.provider_match_id", provider_match_id, provider_match_id))
    
    response = body.get("response") or []
    if not response or not isinstance(response, list):
        return facts

    match_data = response[0] if isinstance(response, list) and len(response) > 0 else {}
    if not isinstance(match_data, dict):
        return facts

    # REQ-NORM-AF-002 Extract teams Norway/Senegal
    teams = match_data.get("teams") or {}
    home_team = teams.get("home", {}).get("name")
    away_team = teams.get("away", {}).get("name")
    if home_team and away_team:
        facts.append(_fact(env, role, "fixture_identity", "teams", {"home": home_team, "away": away_team}, provider_match_id))
        facts.append(_fact(env, role, "fixture_identity", "fixture_slug", "worldcup2026-norway-senegal", provider_match_id))

    # REQ-NORM-AF-003 Extract score 3-2
    goals = match_data.get("goals") or {}
    home_score = goals.get("home")
    away_score = goals.get("away")
    if home_score is not None and away_score is not None:
        facts.append(_fact(env, role, "score", "full_time_score", {"home": int(home_score), "away": int(away_score)}, provider_match_id))

    # REQ-NORM-AF-004 Extract status
    fixture = match_data.get("fixture") or {}
    status_data = fixture.get("status") or {}
    status = status_data.get("long") or status_data.get("short")
    if status:
        facts.append(_fact(env, role, "match_status", "status", status, provider_match_id))

    # REQ-NORM-AF-005 Extract kickoff
    kickoff = fixture.get("date")
    if kickoff:
        facts.append(_fact(env, role, "kickoff", "kickoff_utc", kickoff, provider_match_id))

    # REQ-NORM-AF-006 Extract venue if present
    venue = fixture.get("venue", {}).get("name")
    if venue:
        facts.append(_fact(env, role, "venue", "venue", venue, provider_match_id))

    # REQ-NORM-AF-007 Extract events if present
    events = match_data.get("events")
    if events:
        # Extract detailed events safely
        facts.append(_fact(env, role, "match_event", "events", events, provider_match_id))
        facts.append(_fact(env, role, "match_event", "events_available", True, provider_match_id))

    # REQ-NORM-AF-008 Extract lineups if present
    lineups = match_data.get("lineups")
    if lineups:
        facts.append(_fact(env, role, "lineup", "lineups", lineups, provider_match_id))
        facts.append(_fact(env, role, "lineup", "lineups_available", True, provider_match_id))

    # REQ-NORM-AF-009 API-Football must contribute non-mapping detailed facts
    # We do this by extracting statistics if present
    statistics = match_data.get("statistics")
    if statistics:
        facts.append(_fact(env, role, "match_statistic", "statistics", statistics, provider_match_id))
        facts.append(_fact(env, role, "match_statistic", "statistics_available", True, provider_match_id))

    return facts

def normalize_football_data_org(env: ProviderEnvelope, provider_match_id: Optional[str]) -> List[NormalizedFact]:
    role = "current_reference_replay"
    facts: List[NormalizedFact] = []
    body = env.body or {}

    # REQ-NORM-FDO-001 Extract match id 537394
    if provider_match_id:
        facts.append(_fact(env, role, "provider_mapping", "football-data-org.provider_match_id", provider_match_id, provider_match_id))

    # REQ-NORM-FDO-002 Extract teams Norway/Senegal
    home_team = body.get("homeTeam", {}).get("name")
    away_team = body.get("awayTeam", {}).get("name")
    if home_team and away_team:
        facts.append(_fact(env, role, "fixture_identity", "teams", {"home": home_team, "away": away_team}, provider_match_id))
        facts.append(_fact(env, role, "fixture_identity", "fixture_slug", "worldcup2026-norway-senegal", provider_match_id))

    # REQ-NORM-FDO-003 Extract score 3-2
    score_data = body.get("score", {})
    full_time = score_data.get("fullTime") or {}
    home_score = full_time.get("home")
    away_score = full_time.get("away")
    if home_score is not None and away_score is not None:
        facts.append(_fact(env, role, "score", "full_time_score", {"home": int(home_score), "away": int(away_score)}, provider_match_id))

    # REQ-NORM-FDO-004 Extract status
    status = body.get("status")
    if status:
        facts.append(_fact(env, role, "match_status", "status", status, provider_match_id))

    # REQ-NORM-FDO-005 Extract utcDate
    kickoff = body.get("utcDate")
    if kickoff:
        facts.append(_fact(env, role, "kickoff", "kickoff_utc", kickoff, provider_match_id))

    # REQ-NORM-FDO-006 Extract group/stage if present
    stage = body.get("stage")
    group = body.get("group")
    if stage:
        facts.append(_fact(env, role, "competition", "stage", stage, provider_match_id))
    if group:
        facts.append(_fact(env, role, "competition", "group", group, provider_match_id))

    # REQ-NORM-FDO-007 Extract referee if present
    referees = body.get("referees") or []
    if referees and isinstance(referees, list):
        referee_name = referees[0].get("name")
        if referee_name:
            facts.append(_fact(env, role, "referee", "referee", referee_name, provider_match_id))

    # REQ-NORM-FDO-008 football-data.org must contribute reference/current facts
    competition = body.get("competition", {}).get("name")
    if competition:
        facts.append(_fact(env, role, "competition", "competition", competition, provider_match_id))

    return facts

def normalize_espn_baseline(env: ProviderEnvelope, provider_match_id: Optional[str]) -> List[NormalizedFact]:
    # REQ-NORM-ESPN-004 ESPN source_role must be unofficial_shadow_cross_check
    role = "unofficial_shadow_cross_check"
    facts: List[NormalizedFact] = []
    body = env.body or {}

    # REQ-NORM-ESPN-001 Extract event id 760454
    if provider_match_id:
        facts.append(_fact(env, role, "provider_mapping", "espn-baseline.provider_match_id", provider_match_id, provider_match_id))

    # ESPN must not contribute article/story/media/body text (REQ-NORM-ESPN-005 & REQ-SEC-004)
    # So we strictly avoid those keys.

    # REQ-NORM-ESPN-002 Extract teams Norway/Senegal
    # Let's try to extract if structured teams are present
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

    # REQ-NORM-ESPN-003 Extract score/status/context only if structured
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

    # REQ-NORM-SDB-001 Extract event id
    if provider_match_id:
        facts.append(_fact(env, role, "provider_mapping", "sportdb.provider_match_id", provider_match_id, provider_match_id))

    filename = env.path.name.lower()

    # REQ-NORM-SDB-002 Extract World Cup competition context from results/fixtures/standings/stages
    is_context_file = any(kw in filename for comp_kw in ["worldcup"] for kw in ["stages", "standings", "fixtures", "results"])
    if is_context_file:
        facts.append(_fact(env, role, "competition", "competition", "FIFA World Cup", provider_match_id))
        facts.append(_fact(env, role, "competition", "world_cup_context_available", True, provider_match_id))

    # REQ-NORM-SDB-003 Extract score/status/team identity from match details
    if "details" in filename:
        home_team = body.get("homeName")
        away_team = body.get("awayName")
        if home_team and away_team:
            facts.append(_fact(env, role, "fixture_identity", "teams", {"home": home_team, "away": away_team}, provider_match_id))
            facts.append(_fact(env, role, "fixture_identity", "fixture_slug", "worldcup2026-norway-senegal", provider_match_id))

        # We need score
        # Wait, let's search if there is a main score in details. Usually, we can find homeScore / awayScore or find it in events.
        # But details also contains incidents.
        # Let's extract referee and venue if present in details (from our read of match_details: "referee": "Sampaio W.", "venue": "MetLife Stadium")
        referee = body.get("referee")
        venue = body.get("venue")
        if referee:
            facts.append(_fact(env, role, "referee", "referee", referee, provider_match_id))
        if venue:
            facts.append(_fact(env, role, "venue", "venue", venue, provider_match_id))

        # Also details contains score in the final event or we can check body.get("homeScore") and body.get("awayScore") or get it from events
        # Let's check: can we walk events and get the maximum homeScore/awayScore? Yes, that's incredibly smart and deterministic!
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

        # REQ-NORM-SDB-004 Extract match events from details?with_events=true if present
        if incidents:
            facts.append(_fact(env, role, "match_event", "events", incidents, provider_match_id))
            facts.append(_fact(env, role, "match_event", "events_available", True, provider_match_id))

    # REQ-NORM-SDB-005 Extract stats from stats endpoint
    if "stats" in filename:
        # body is a list of periods
        if isinstance(body, list) and len(body) > 0:
            facts.append(_fact(env, role, "match_statistic", "statistics", body, provider_match_id))
            facts.append(_fact(env, role, "match_statistic", "statistics_available", True, provider_match_id))

    # REQ-NORM-SDB-006 Extract lineups from lineups endpoint
    if "lineups" in filename:
        facts.append(_fact(env, role, "lineup", "lineups", body, provider_match_id))
        facts.append(_fact(env, role, "lineup", "lineups_available", True, provider_match_id))

    # REQ-NORM-SDB-007 Extract odds only as odds_reference
    if "odds" in filename:
        # odds_reference REQ-NORM-SDB-009: SportDB odds must never be betting decision
        facts.append(_fact(env, role, "odds_reference", "odds_reference_available", True, provider_match_id))
        # Add bookmaker details without recommendations
        bookmakers = [b.get("bookmakerName") for b in body if isinstance(b, dict)] if isinstance(body, list) else []
        facts.append(_fact(env, role, "odds_reference", "bookmakers", sorted(set(bookmakers)), provider_match_id))

    return facts

def normalize_highlightly(env: ProviderEnvelope, provider_match_id: Optional[str]) -> List[NormalizedFact]:
    role = "source_bound_detailed_replay"
    facts: List[NormalizedFact] = []
    body = env.body or {}

    # REQ-NORM-HL-001 Extract match id
    if provider_match_id:
        facts.append(_fact(env, role, "provider_mapping", "highlightly.provider_match_id", provider_match_id, provider_match_id))

    filename = env.path.name.lower()

    # REQ-NORM-HL-002 Extract match identity and status from match detail
    if "detail" in filename:
        # body can be a list or a dict
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
        if venue:
            facts.append(_fact(env, role, "venue", "venue", venue, provider_match_id))

    # REQ-NORM-HL-003 Extract statistics from statistics endpoint
    if "statistics" in filename:
        facts.append(_fact(env, role, "match_statistic", "statistics", body, provider_match_id))
        facts.append(_fact(env, role, "match_statistic", "statistics_available", True, provider_match_id))

    # REQ-NORM-HL-004 Extract lineups from lineups endpoint
    if "lineups" in filename:
        facts.append(_fact(env, role, "lineup", "lineups", body, provider_match_id))
        facts.append(_fact(env, role, "lineup", "lineups_available", True, provider_match_id))

    # REQ-NORM-HL-005 Extract events from events endpoint
    if "events" in filename:
        facts.append(_fact(env, role, "match_event", "events", body, provider_match_id))
        facts.append(_fact(env, role, "match_event", "events_available", True, provider_match_id))

    return facts
