# ruff: noqa: E501
import math
from enum import StrEnum
from typing import Any

from bet.enrichment.football.contracts import (
    FootballCompletedMatchFacts,
    FootballFactCompleteness,
    FootballFixtureIdentity,
    FootballProviderStatus,
    FootballSide,
    FootballTeamMatchFacts,
)
from bet.enrichment.football.time import parse_canonical_or_offset_datetime


class FootballParserErrorCode(StrEnum):
    RECORD_NOT_FOUND = "RECORD_NOT_FOUND"
    NOT_COMPLETED = "NOT_COMPLETED"
    SCHEMA_MISMATCH = "SCHEMA_MISMATCH"
    INVALID_IDENTITY = "INVALID_IDENTITY"
    INVALID_SCORE = "INVALID_SCORE"
    INVALID_TIMESTAMP = "INVALID_TIMESTAMP"
    INVALID_METRIC = "INVALID_METRIC"
    CONFLICTING_DUPLICATE_METRIC = "CONFLICTING_DUPLICATE_METRIC"
    UNEXPECTED_PARTICIPANT = "UNEXPECTED_PARTICIPANT"
    STATISTICS_UNAVAILABLE = "STATISTICS_UNAVAILABLE"

class FootballParserError(Exception):
    def __init__(self, error_code: FootballParserErrorCode, message: str) -> None:
        super().__init__(f"[{error_code.value}] {message}")
        self.error_code = error_code
        self.message = message

def parse_api_football_fixture_envelope(
    raw_fixture: dict[str, Any], requested_provider_fixture_id: str
) -> FootballFixtureIdentity:
    if not isinstance(raw_fixture, dict):
        raise FootballParserError(FootballParserErrorCode.SCHEMA_MISMATCH, "raw_fixture must be a dict")

    fix = raw_fixture.get("fixture")
    if not isinstance(fix, dict):
        raise FootballParserError(FootballParserErrorCode.SCHEMA_MISMATCH, "missing or invalid 'fixture' key in envelope")

    league = raw_fixture.get("league")
    if not isinstance(league, dict):
        raise FootballParserError(FootballParserErrorCode.SCHEMA_MISMATCH, "missing or invalid 'league' key in envelope")

    teams = raw_fixture.get("teams")
    if not isinstance(teams, dict):
        raise FootballParserError(FootballParserErrorCode.SCHEMA_MISMATCH, "missing or invalid 'teams' key in envelope")

    goals = raw_fixture.get("goals")
    if not isinstance(goals, dict):
        raise FootballParserError(FootballParserErrorCode.SCHEMA_MISMATCH, "missing or invalid 'goals' key in envelope")

    score = raw_fixture.get("score")
    if score is not None and not isinstance(score, dict):
        raise FootballParserError(FootballParserErrorCode.SCHEMA_MISMATCH, "invalid 'score' key in envelope")

    fix_id = str(fix.get("id", ""))
    if not fix_id:
        raise FootballParserError(FootballParserErrorCode.INVALID_IDENTITY, "fixture id is missing or empty")
    if fix_id != requested_provider_fixture_id:
        raise FootballParserError(FootballParserErrorCode.RECORD_NOT_FOUND, f"fixture id {fix_id} does not match requested {requested_provider_fixture_id}")

    status_dict = fix.get("status")
    if not isinstance(status_dict, dict):
        raise FootballParserError(FootballParserErrorCode.SCHEMA_MISMATCH, "invalid 'status' structure")
    status_short = status_dict.get("short", "")
    if status_short not in ("FT", "AET", "PEN"):
        raise FootballParserError(FootballParserErrorCode.NOT_COMPLETED, f"fixture status '{status_short}' is not FT, AET, or PEN")

    home_team = teams.get("home")
    away_team = teams.get("away")
    if not isinstance(home_team, dict) or not isinstance(away_team, dict):
        raise FootballParserError(FootballParserErrorCode.SCHEMA_MISMATCH, "missing home or away team in envelope")

    home_id = str(home_team.get("id", ""))
    away_id = str(away_team.get("id", ""))
    if not home_id or not away_id:
        raise FootballParserError(FootballParserErrorCode.INVALID_IDENTITY, "missing team provider id")
    if home_id == away_id:
        raise FootballParserError(FootballParserErrorCode.INVALID_IDENTITY, "home and away team ids must be distinct")

    home_name = str(home_team.get("name", ""))
    away_name = str(away_team.get("name", ""))
    if not home_name or not away_name:
        raise FootballParserError(FootballParserErrorCode.INVALID_IDENTITY, "missing team names")

    try:
        raw_home_goals = goals.get("home")
        raw_away_goals = goals.get("away")
        if raw_home_goals is None or raw_away_goals is None:
            raise FootballParserError(FootballParserErrorCode.SCHEMA_MISMATCH, "missing goals fields")
        home_goals = int(raw_home_goals)
        away_goals = int(raw_away_goals)
    except (TypeError, ValueError) as e:
        if isinstance(e, FootballParserError):
            raise e
        raise FootballParserError(FootballParserErrorCode.INVALID_SCORE, "goals are not valid integers") from e

    if home_goals < 0 or away_goals < 0:
        raise FootballParserError(FootballParserErrorCode.INVALID_SCORE, "goals cannot be negative")

    # Penalty separation
    home_pen = None
    away_pen = None
    if status_short == "PEN":
        pen = score.get("penalty")
        if not isinstance(pen, dict):
            raise FootballParserError(FootballParserErrorCode.SCHEMA_MISMATCH, "missing or invalid penalty score structure for PEN fixture")
        h_pen = pen.get("home")
        a_pen = pen.get("away")
        if h_pen is None or a_pen is None:
            raise FootballParserError(FootballParserErrorCode.INVALID_SCORE, "missing penalty scores for PEN status")
        try:
            home_pen = int(h_pen)
            away_pen = int(a_pen)
        except (TypeError, ValueError) as e:
            raise FootballParserError(FootballParserErrorCode.INVALID_SCORE, "penalty scores must be valid integers") from e
        if home_pen < 0 or away_pen < 0:
            raise FootballParserError(FootballParserErrorCode.INVALID_SCORE, "penalty scores cannot be negative")

    date_str = fix.get("date", "")
    try:
        kickoff = parse_canonical_or_offset_datetime(date_str)
    except Exception as e:
        raise FootballParserError(FootballParserErrorCode.INVALID_TIMESTAMP, f"invalid kickoff timestamp: {date_str}") from e

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
        parser_version="2.0",
        schema_version="1"
    )

def _parse_metric(val: Any, metric_type: str) -> float | None:
    if val is None:
        return None

    f_val = None
    if isinstance(val, str):
        cleaned = val.strip()
        if cleaned.endswith("%"):
            try:
                f_val = float(cleaned[:-1])
            except ValueError as e:
                raise FootballParserError(FootballParserErrorCode.INVALID_METRIC, f"Malformed percentage metric {metric_type}: {val}") from e
        else:
            try:
                f_val = float(cleaned)
            except ValueError as e:
                raise FootballParserError(FootballParserErrorCode.INVALID_METRIC, f"Malformed metric {metric_type}: {val}") from e
    elif isinstance(val, (int, float)):
        f_val = float(val)
    else:
        raise FootballParserError(FootballParserErrorCode.INVALID_METRIC, f"Unsupported metric type for {metric_type}: {val}")

    if math.isnan(f_val) or math.isinf(f_val):
        raise FootballParserError(FootballParserErrorCode.INVALID_METRIC, f"Metric {metric_type} is NaN or Inf: {val}")

    if f_val < 0:
        raise FootballParserError(FootballParserErrorCode.INVALID_METRIC, f"Metric {metric_type} is negative: {val}")

    if metric_type == "Ball Possession":
        if not (0.0 <= f_val <= 100.0):
            raise FootballParserError(FootballParserErrorCode.INVALID_METRIC, f"Ball Possession percentage out of range: {val}")

    return f_val

def parse_api_football_statistics_envelope(
    raw_stats: list[dict[str, Any]], expected_home_id: str, expected_away_id: str
) -> dict[str, dict[str, int | float | None]]:
    result = {expected_home_id: {}, expected_away_id: {}}
    if not raw_stats:
        return result

    if not isinstance(raw_stats, list):
        raise FootballParserError(FootballParserErrorCode.SCHEMA_MISMATCH, "raw_stats must be a list")

    for team_stats in raw_stats:
        if not isinstance(team_stats, dict):
            raise FootballParserError(FootballParserErrorCode.SCHEMA_MISMATCH, "team_stats must be a dict")

        team_dict = team_stats.get("team")
        if not isinstance(team_dict, dict):
            raise FootballParserError(FootballParserErrorCode.SCHEMA_MISMATCH, "missing or invalid team in statistics")

        team_id = str(team_dict.get("id", ""))
        if not team_id:
            raise FootballParserError(FootballParserErrorCode.INVALID_IDENTITY, "team id is missing in statistics")

        if team_id not in (expected_home_id, expected_away_id):
            raise FootballParserError(FootballParserErrorCode.UNEXPECTED_PARTICIPANT, f"Unexpected team ID in statistics: {team_id}")

        stats_list = team_stats.get("statistics")
        if stats_list is None:
            continue
        if not isinstance(stats_list, list):
            raise FootballParserError(FootballParserErrorCode.SCHEMA_MISMATCH, "statistics must be a list")

        parsed = {}
        for stat in stats_list:
            if not isinstance(stat, dict):
                raise FootballParserError(FootballParserErrorCode.SCHEMA_MISMATCH, "each statistic must be a dict")
            typ = stat.get("type")
            if not typ:
                raise FootballParserError(FootballParserErrorCode.SCHEMA_MISMATCH, "statistic type is missing")

            raw_val = stat.get("value")
            val = _parse_metric(raw_val, typ)

            if val is not None:
                if typ in parsed:
                    if parsed[typ] != val:
                        raise FootballParserError(
                            FootballParserErrorCode.CONFLICTING_DUPLICATE_METRIC,
                            f"Conflicting duplicate metric for {typ}: {parsed[typ]} vs {val}"
                        )
                parsed[typ] = val

        result[team_id] = parsed

    return result

def merge_completed_match_facts(
    fixture: FootballFixtureIdentity,
    parsed_stats: dict[str, dict[str, int | float | None]],
    fixture_bundle_id: str,
    stats_bundle_id: str | None
) -> FootballCompletedMatchFacts:

    def build_team_facts(team_id: str, opponent_id: str, side: FootballSide, goals: int) -> FootballTeamMatchFacts:
        stats = parsed_stats.get(team_id, {})

        def get_int(k: str) -> int | None:
            v = stats.get(k)
            return int(v) if v is not None else None

        def get_float(k: str) -> float | None:
            v = stats.get(k)
            return float(v) if v is not None else None

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
            provider_opponent_team_id=opponent_id,
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

    home_facts = build_team_facts(
        fixture.home_provider_team_id,
        fixture.away_provider_team_id,
        FootballSide.HOME,
        fixture.home_score
    )
    away_facts = build_team_facts(
        fixture.away_provider_team_id,
        fixture.home_provider_team_id,
        FootballSide.AWAY,
        fixture.away_score
    )

    return FootballCompletedMatchFacts(
        fixture=fixture,
        home=home_facts,
        away=away_facts,
        fixture_evidence_bundle_id=fixture_bundle_id,
        statistics_evidence_bundle_id=stats_bundle_id,
        normalization_version="2.0"
    )
