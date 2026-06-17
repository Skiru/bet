from datetime import UTC, datetime

import pytest

from bet.enrichment.football.contracts import FootballFactCompleteness
from bet.enrichment.football.parser import (
    FootballParserError,
    FootballParserErrorCode,
    merge_completed_match_facts,
    parse_api_football_fixture_envelope,
    parse_api_football_statistics_envelope,
)


def test_parse_fixture_success():
    raw = {
        "fixture": {"id": 123, "status": {"short": "FT"}, "date": "2023-01-01T15:00:00+00:00"},
        "league": {"id": 456, "name": "L", "season": 2023},
        "teams": {
            "home": {"id": 1, "name": "H"},
            "away": {"id": 2, "name": "A"}
        },
        "goals": {"home": 2, "away": 1},
        "score": {"penalty": {"home": None, "away": None}}
    }
    fix = parse_api_football_fixture_envelope(raw, "123")
    assert fix is not None
    assert fix.home_score == 2
    assert fix.away_score == 1
    assert fix.kickoff_at == datetime(2023, 1, 1, 15, tzinfo=UTC)

def test_parse_fixture_penalties():
    raw = {
        "fixture": {"id": 123, "status": {"short": "PEN"}, "date": "2023-01-01T15:00:00+00:00"},
        "league": {"id": 456, "name": "L", "season": 2023},
        "teams": {
            "home": {"id": 1, "name": "H"},
            "away": {"id": 2, "name": "A"}
        },
        "goals": {"home": 1, "away": 1},
        "score": {"penalty": {"home": 4, "away": 3}}
    }
    fix = parse_api_football_fixture_envelope(raw, "123")
    assert fix.home_penalty_score == 4
    assert fix.away_penalty_score == 3
    assert fix.home_score == 1

def test_parse_stats_valid():
    raw = [
        {"team": {"id": 1}, "statistics": [{"type": "Total Shots", "value": 10}, {"type": "Ball Possession", "value": "55%"}]},
        {"team": {"id": 2}, "statistics": [{"type": "Total Shots", "value": 5}, {"type": "Ball Possession", "value": "45%"}]}
    ]
    parsed = parse_api_football_statistics_envelope(raw, "1", "2")
    assert parsed["1"]["Total Shots"] == 10
    assert parsed["1"]["Ball Possession"] == 55.0

def test_parse_stats_unexpected_participant():
    raw = [
        {"team": {"id": 3}, "statistics": [{"type": "Total Shots", "value": 10}]}
    ]
    with pytest.raises(FootballParserError) as exc_info:
        parse_api_football_statistics_envelope(raw, "1", "2")
    assert exc_info.value.error_code == FootballParserErrorCode.UNEXPECTED_PARTICIPANT

def test_parse_stats_duplicate_conflict():
    raw = [
        {"team": {"id": 1}, "statistics": [{"type": "Total Shots", "value": 10}, {"type": "Total Shots", "value": 11}]}
    ]
    with pytest.raises(FootballParserError) as exc_info:
        parse_api_football_statistics_envelope(raw, "1", "2")
    assert exc_info.value.error_code == FootballParserErrorCode.CONFLICTING_DUPLICATE_METRIC

def test_merge_match_facts():
    raw_fixture = {
        "fixture": {"id": 123, "status": {"short": "FT"}, "date": "2023-01-01T15:00:00+00:00"},
        "league": {"id": 456, "name": "L", "season": 2023},
        "teams": {
            "home": {"id": 1, "name": "H"},
            "away": {"id": 2, "name": "A"}
        },
        "goals": {"home": 2, "away": 1}
    }
    fix = parse_api_football_fixture_envelope(raw_fixture, "123")
    parsed_stats = {"1": {}, "2": {}}
    facts = merge_completed_match_facts(fix, parsed_stats, "b_id", None)
    assert facts.home.completeness == FootballFactCompleteness.SCORE_ONLY
    assert facts.away.completeness == FootballFactCompleteness.SCORE_ONLY
