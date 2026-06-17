# ruff: noqa: E501
import pytest

from bet.enrichment.football.contracts import (
    FootballFactCompleteness,
    FootballSide,
    FootballTeamMatchFacts,
)


def test_team_match_facts_valid():
    facts = FootballTeamMatchFacts(
        provider_fixture_id="123",
        provider_team_id="1",
        provider_opponent_team_id="2",
        side=FootballSide.HOME,
        goals=2,
        shots=10,
        shots_on_target=5,
        possession_pct=55.0,
        fouls=12,
        yellow_cards=2,
        red_cards=0,
        offsides=1,
        corners=4,
        goalkeeper_saves=3,
        available_metrics=("corners", "fouls", "goalkeeper_saves", "offsides", "possession_pct", "red_cards", "shots", "shots_on_target", "yellow_cards"),
        missing_metrics=(),
        completeness=FootballFactCompleteness.COMPLETE
    )
    assert facts.completeness == FootballFactCompleteness.COMPLETE

def test_team_match_facts_partial():
    # Only 3 metrics present
    facts = FootballTeamMatchFacts(
        provider_fixture_id="123",
        provider_team_id="1",
        provider_opponent_team_id="2",
        side=FootballSide.HOME,
        goals=2,
        shots=10,
        shots_on_target=5,
        possession_pct=None,
        fouls=12,
        yellow_cards=None,
        red_cards=None,
        offsides=None,
        corners=None,
        goalkeeper_saves=None,
        available_metrics=("fouls", "shots", "shots_on_target"),
        missing_metrics=("corners", "goalkeeper_saves", "offsides", "possession_pct", "red_cards", "yellow_cards"),
        completeness=FootballFactCompleteness.PARTIAL
    )
    assert facts.completeness == FootballFactCompleteness.PARTIAL

def test_team_match_facts_score_only():
    facts = FootballTeamMatchFacts(
        provider_fixture_id="123",
        provider_team_id="1",
        provider_opponent_team_id="2",
        side=FootballSide.HOME,
        goals=2,
        shots=None,
        shots_on_target=None,
        possession_pct=None,
        fouls=None,
        yellow_cards=None,
        red_cards=None,
        offsides=None,
        corners=None,
        goalkeeper_saves=None,
        available_metrics=(),
        missing_metrics=("corners", "fouls", "goalkeeper_saves", "offsides", "possession_pct", "red_cards", "shots", "shots_on_target", "yellow_cards"),
        completeness=FootballFactCompleteness.SCORE_ONLY
    )
    assert facts.completeness == FootballFactCompleteness.SCORE_ONLY

def test_team_match_facts_invalid_possession():
    with pytest.raises(ValueError):
        FootballTeamMatchFacts(
            provider_fixture_id="123",
            provider_team_id="1",
            provider_opponent_team_id="2",
            side=FootballSide.HOME,
            goals=2,
            shots=10,
            shots_on_target=5,
            possession_pct=150.0,
            fouls=12,
            yellow_cards=2,
            red_cards=0,
            offsides=1,
            corners=4,
            goalkeeper_saves=3,
            available_metrics=("corners", "fouls", "goalkeeper_saves", "offsides", "possession_pct", "red_cards", "shots", "shots_on_target", "yellow_cards"),
            missing_metrics=(),
            completeness=FootballFactCompleteness.COMPLETE
        )
