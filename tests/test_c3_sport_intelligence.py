"""C3 acceptance tests for sport and market intelligence protocols."""
from __future__ import annotations

import pytest
from src.bet.pipeline.sports.models import ContextFactorV1, SportEventDossierV1
from src.bet.pipeline.sports.registry import GLOBAL_SPORT_PROTOCOL_REGISTRY
from src.bet.pipeline.market_evidence_sufficiency import evaluate_evidence_sufficiency
from src.bet.pipeline.contracts.canonical_json import hash_canonical_json


def test_football_corners_cannot_be_high_without_stats():
    """Verify football corners market returns LOW grade when corner stats are missing."""
    event = {
        "canonical_event_id": "EVT_FB_001",
        "sport": "football",
        "home_team": "Arsenal",
        "away_team": "Chelsea",
        "competition": "Premier League",
        "discovery_status": "VERIFIED",
    }
    row = {"market_family": "corners", "line": "9.5"}

    grade, blockers = evaluate_evidence_sufficiency("football", "corners", event, row, {})
    assert grade in ("LOW", "UNKNOWN")
    assert "MISSING_CORNER_STATS" in blockers or "MISSING_FOOTBALL_CORNER_REQUIREMENTS" in blockers


def test_tennis_workload_triggers_interval_widening_not_rejection():
    """Verify tennis player with rest_hours < 18 triggers interval widening, not hard rejection."""
    protocol = GLOBAL_SPORT_PROTOCOL_REGISTRY.get_strict("tennis")
    event = {
        "canonical_event_id": "EVT_TEN_001",
        "sport": "tennis",
        "home_team": "Player A",
        "away_team": "Player B",
        "competition": "Wimbledon",
        "ranking_proxy": "TOP_10",
        "form_proxy": "GOOD",
        "surface": "Grass",
    }
    evidence_pack = {"rest_hours": 12}  # Short rest

    decision = protocol.evaluate_market_readiness(
        canonical_event_id="EVT_TEN_001",
        market_family="match_winner",
        event_data=event,
        row_data={},
        evidence_pack=evidence_pack,
    )

    assert decision.quality_grade == "HIGH"
    assert decision.allowed_action == "READY_FOR_PRICING"
    assert "HIGH_CONSECUTIVE_DAY_WORKLOAD_WIDEN_INTERVAL" in decision.reason_codes


def test_unknown_hockey_goalie_blocks_pricing():
    """Verify unknown starting goalie in hockey blocks pricing (downgrades to ANALYSIS_ONLY)."""
    protocol = GLOBAL_SPORT_PROTOCOL_REGISTRY.get_strict("hockey")
    event = {
        "canonical_event_id": "EVT_HOC_001",
        "sport": "hockey",
        "home_team": "Rangers",
        "away_team": "Bruins",
        "competition": "NHL",
    }

    decision = protocol.evaluate_market_readiness(
        canonical_event_id="EVT_HOC_001",
        market_family="puck_line",
        event_data=event,
        row_data={},
        evidence_pack={},
    )

    assert decision.allowed_action == "ANALYSIS_ONLY"
    assert "UNKNOWN_STARTER_GOALIE" in decision.missing_requirements


def test_dossier_hashing_determinism():
    """Verify SportEventDossierV1 validates and hashes deterministically."""
    factor = ContextFactorV1(
        factor_type="WEATHER",
        observed_at="2026-07-27T10:00:00Z",
        category="ENVIRONMENT",
        direction="NEUTRAL",
    )
    dossier = SportEventDossierV1(
        dossier_id="DOS_001",
        canonical_event_id="EVT_FB_001",
        sport="football",
        competition="Premier League",
        home_team="Arsenal",
        away_team="Chelsea",
        event_start_time="2026-07-27T15:00:00Z",
        context_factors=[factor],
    )
    data = dossier.model_dump(exclude={"dossier_sha256"})
    h1 = hash_canonical_json(data)
    h2 = hash_canonical_json(data)
    assert h1 == h2
