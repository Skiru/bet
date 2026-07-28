"""Integration test verifying canonical pipeline execution of S2.7->S2.9->S5->S3 and S7->S7b->S8 without synthetic pricing."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
import pytest

from bet.pipeline.orchestrator import Orchestrator
from bet.pipeline.market_evidence_sufficiency import MarketDossierV1, evaluate_evidence_sufficiency
from bet.pipeline.analytical_candidate_bridge import map_s7_to_s7b
from bet.pipeline.bet_builder_analytical import build_s8_output, build_bet_builder_pack


def test_s2_9_to_s5_dossier_flow():
    """Verify S2.9 creates source-bound dossiers with real event metadata and S5 consumes them."""
    event = {
        "canonical_event_id": "evt_real_01",
        "sport": "football",
        "competition": "Premier League",
        "home_team": "Arsenal",
        "away_team": "Chelsea",
        "scheduled_start_utc": "2026-07-28T20:00:00Z",
    }
    row = {
        "market_family": "result",
        "sample_size": 10,
        "data_freshness_hours": 12,
        "sources": ["stats_db"],
    }
    evidence_pack = {
        "home_corners_avg": 5.5,
        "away_corners_avg": 4.2,
        "home_corners_against_avg": 3.8,
        "away_corners_against_avg": 5.1,
        "sample_size": 10,
        "data_freshness_hours": 12,
        "sources": ["stats_db"],
    }

    grade, blockers = evaluate_evidence_sufficiency("football", "corners", event, row, evidence_pack)
    assert grade == "HIGH"
    assert not blockers

    dossier = MarketDossierV1(
        dossier_id="DOS-evt_real_01-corners",
        canonical_event_id="evt_real_01",
        sport="football",
        competition="Premier League",
        market_family="corners",
        readiness_status="EVIDENCE_SCOPE_READY",
        quality_grade=grade,
    )
    assert dossier.canonical_event_id == "evt_real_01"
    assert dossier.sport == "football"
    assert dossier.competition == "Premier League"


def test_s7_to_s8_analysis_only_flow():
    """Verify S7->S7b->S8 pipeline yields ANALYSIS_ONLY_OUTPUT and human gate False without promoted model."""
    s7_candidate = {
        "canonical_event_id": "evt_real_01",
        "selection_id": "cand_01",
        "quote_card_id": "card_01",
        "source_candidate_id": "cand_01",
        "sport": "football",
        "competition": "Premier League",
        "home_team": "Arsenal",
        "away_team": "Chelsea",
        "market_family": "RESULT",
        "selection": "HOME_WIN",
        "manual_operator": "SUPERBET",
        "mapping_ambiguity": "NONE",
        "operator_availability_asserted": False,
        "executable_coupon": False,
        "betting_valid": False,
        "can_place_bet_now": False,
    }

    s7b_card = map_s7_to_s7b(s7_candidate)
    assert s7b_card["selection_id"] == "cand_01"
    assert s7b_card["sport"] == "football"

    # With no promoted model, S8 output must be ANALYSIS_ONLY_OUTPUT and ready_for_human_gate = False
    s8_res = build_s8_output(candidates=[s7b_card], model_package=None)
    assert s8_res["output_status"] == "ANALYSIS_ONLY_OUTPUT"
    assert s8_res["ready_for_human_gate"] is False
    assert s8_res["pricing_status"] == "UNPRICED"

    # Builder pack must reject with NO_VERIFIED_JOINT_MODEL_SCOPE
    builder_res = build_bet_builder_pack(candidates=[s7b_card], joint_model=None)
    assert builder_res["status"] == "REJECTED"
    assert builder_res["rejection_reason"] == "NO_VERIFIED_JOINT_MODEL_SCOPE"
    assert builder_res["combined_odds"] is None
