from datetime import UTC, datetime
from typing import Any

from bet.enrichment.football.contracts import (
    FootballCompletedMatchFacts,
    FootballFactCompleteness,
    FootballFixtureIdentity,
    FootballProviderStatus,
    FootballSide,
    FootballTeamMatchFacts,
)


def parse_api_football_fixture_envelope(
    raw_fixture: dict[str, Any], requested_provider_fixture_id: str
) -> FootballFixtureIdentity | None:
    fix = raw_fixture.get("fixture", {})
    league = raw_fixture.get("league", {})
    teams = raw_fixture.get("teams", {})
    goals = raw_fixture.get("goals", {})
    score = raw_fixture.get("score", {})

    fix_id = str(fix.get("id", ""))
    if fix_id != requested_provider_fixture_id:
        return None

    status_short = fix.get("status", {}).get("short", "")
    if status_short not in ("FT", "AET", "PEN"):
        return None

    home_team = teams.get("home", {})
    away_team = teams.get("away", {})

    if not home_team or not away_team:
        return None

    home_id = str(home_team.get("id", ""))
    away_id = str(away_team.get("id", ""))
    if not home_id or not away_id or home_id == away_id:
        return None

    home_name = str(home_team.get("name", ""))
    away_name = str(away_team.get("name", ""))
    if not home_name or not away_name:
        return None

    try:
        home_goals = int(goals.get("home"))
        away_goals = int(goals.get("away"))
    except (TypeError, ValueError):
        return None

    if home_goals < 0 or away_goals < 0:
        return None

    # Penalty separation
    home_pen = None
    away_pen = None
    if status_short == "PEN":
        try:
            pen = score.get("penalty", {})
            h_pen = pen.get("home")
            a_pen = pen.get("away")
            if h_pen is not None and a_pen is not None:
                home_pen = int(h_pen)
                away_pen = int(a_pen)
                if home_pen < 0 or away_pen < 0:
                    home_pen = None
                    away_pen = None
        except (TypeError, ValueError):
            pass

    date_str = fix.get("date", "")
    try:
        # Expected format YYYY-MM-DDTHH:MM:SS+00:00
        kickoff = datetime.fromisoformat(date_str).astimezone(UTC)
    except (ValueError, TypeError):
        return None

    return FootballFixtureIdentity(
        provider_fixture_id=fix_id,
        provider_competition_id=str(league.get("id", "")),
        competition_name=str(league.get("name", "")),
        country=league.get("country") if league.get("country") is not None else None,
        season=int(league.get("season", 0)),
        round_name=league.get("round") if league.get("round") is not None else None,
        kickoff_at=kickoff,
        provider_status=FootballProviderStatus(status_short),
        canonical_status="finished",
        home_provider_team_id=home_id,
        away_provider_team_id=away_id,
        home_team_name=home_name,
        away_team_name=away_name,
        home_score=home_goals,
        away_score=away_goals,
        home_penalty_score=home_pen,
        away_penalty_score=away_pen,
        parser_version="1.0",
        schema_version="1"
    )

def _parse_metric(val: Any) -> float | None:
    if val is None:
        return None
    if isinstance(val, str):
        if val.endswith("%"):
            try:
                val = float(val[:-1])
            except ValueError:
                return None
        else:
            try:
                val = float(val)
            except ValueError:
                return None
    try:
        val = float(val)
    except (TypeError, ValueError):
        return None
    import math
    if math.isnan(val) or math.isinf(val):
        return None
    return val

def parse_api_football_statistics_envelope(
    raw_stats: list[dict[str, Any]], expected_home_id: str, expected_away_id: str
) -> dict[str, dict[str, int | float | None]]:
    result = {expected_home_id: {}, expected_away_id: {}}
    if not isinstance(raw_stats, list):
        return result

    for team_stats in raw_stats:
        team_id = str(team_stats.get("team", {}).get("id", ""))
        if team_id not in result:
            # reject unexpected team ID
            return {expected_home_id: {}, expected_away_id: {}}

        stats = team_stats.get("statistics", [])
        if not isinstance(stats, list):
            continue

        parsed = {}
        for stat in stats:
            typ = stat.get("type")
            val = _parse_metric(stat.get("value"))
            if val is not None and val < 0:
                val = None
            if typ == "Ball Possession" and val is not None:
                if val < 0 or val > 100:
                    val = None

            if typ and val is not None:
                if typ in parsed and parsed[typ] != val:
                    # duplicate conflicting
                    parsed[typ] = None # invalid
                else:
                    parsed[typ] = val

        # filter out invalidated
        parsed = {k: v for k, v in parsed.items() if v is not None}
        result[team_id] = parsed

    return result

def merge_completed_match_facts(
    fixture: FootballFixtureIdentity,
    parsed_stats: dict[str, dict[str, int | float | None]],
    fixture_bundle_id: str,
    stats_bundle_id: str | None
) -> FootballCompletedMatchFacts:

    def build_team_facts(team_id: str, side: FootballSide, goals: int) -> FootballTeamMatchFacts:
        stats = parsed_stats.get(team_id, {})

        def get_int(k: str) -> int | None:
            v = stats.get(k)
            return int(v) if v is not None else None

        def get_float(k: str) -> float | None:
            return stats.get(k)

        shots = get_int("Total Shots")
        shots_on_target = get_int("Shots on Goal")
        possession_pct = get_float("Ball Possession")
        fouls = get_int("Fouls")
        yellow_cards = get_int("Yellow Cards")
        red_cards = get_int("Red Cards")
        offsides = get_int("Offsides")
        corners = get_int("Corner Kicks")
        goalkeeper_saves = get_int("Goalkeeper Saves")

        metrics = {
            "shots": shots,
            "shots_on_target": shots_on_target,
            "possession_pct": possession_pct,
            "fouls": fouls,
            "yellow_cards": yellow_cards,
            "red_cards": red_cards,
            "offsides": offsides,
            "corners": corners,
            "goalkeeper_saves": goalkeeper_saves
        }

        available = tuple(sorted([k for k, v in metrics.items() if v is not None]))
        missing = tuple(sorted([k for k, v in metrics.items() if v is None]))

        if len(available) == 9:
            comp = FootballFactCompleteness.COMPLETE
        elif len(available) > 0:
            comp = FootballFactCompleteness.PARTIAL
        else:
            comp = FootballFactCompleteness.SCORE_ONLY

        return FootballTeamMatchFacts(
            provider_fixture_id=fixture.provider_fixture_id,
            provider_team_id=team_id,
            side=side,
            goals=goals,
            shots=shots,
            shots_on_target=shots_on_target,
            possession_pct=possession_pct,
            fouls=fouls,
            yellow_cards=yellow_cards,
            red_cards=red_cards,
            offsides=offsides,
            corners=corners,
            goalkeeper_saves=goalkeeper_saves,
            available_metrics=available,
            missing_metrics=missing,
            completeness=comp
        )

    home_facts = build_team_facts(fixture.home_provider_team_id, FootballSide.HOME, fixture.home_score)
    away_facts = build_team_facts(fixture.away_provider_team_id, FootballSide.AWAY, fixture.away_score)

    return FootballCompletedMatchFacts(
        fixture=fixture,
        home=home_facts,
        away=away_facts,
        fixture_evidence_bundle_id=fixture_bundle_id,
        statistics_evidence_bundle_id=stats_bundle_id,
        normalization_version="1.0"
    )
