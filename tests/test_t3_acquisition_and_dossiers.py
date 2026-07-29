"""Checkpoint T3 tests: bounded acquisition plans, prompt consistency, and sport dossier integration."""
from __future__ import annotations

import pytest
from bet.pipeline.sharding.models import FactAcquisitionPlanV1, FactRequirementV1, RetrievalReceiptV1
from bet.pipeline.agent_execution_prompts import render_agent_execution_prompt, validate_rendered_prompt
from bet.pipeline.sports.registry import GLOBAL_SPORT_PROTOCOL_REGISTRY


def test_t3_prompt_acquisition_plan_consistency(tmp_path):
    """Verify prompt distinguishes work order with vs without acquisition plan."""
    wo_no_plan = {
        "work_order_id": "WO_NO_PLAN",
        "pipeline_id": "bet_pipeline_v1",
        "betting_day": "2026-07-27",
        "run_id": "RUN_001",
        "step_id": "S2.3",
        "agent": "bet-researcher",
        "runtime_mode": "DRY_RUN",
        "input_refs": [],
        "required_output": {"expected_path": str(tmp_path / "out.json"), "artifact_type": "AGENT_ARTIFACT", "required_statuses": ["PASS"]},
        "hard_rules": ["RULE_1"],
        "forbidden_outputs": ["FORBIDDEN_1"],
        "instructions": {"summary": "Sum", "must_do": ["Do"], "must_not_do": ["Not"], "unknown_policy": "Block", "output_contract": ["Contract"]},
    }
    prompt_no_plan = render_agent_execution_prompt(wo_no_plan)
    assert "Do not call external APIs or browse externally" in prompt_no_plan
    assert not validate_rendered_prompt(prompt_no_plan, wo_no_plan)

    wo_with_plan = dict(wo_no_plan, acquisition_plan={
        "plan_id": "PLAN_001",
        "canonical_event_id": "EVT_001",
        "sport": "football",
        "max_queries": 5,
        "requirements": [{"requirement_id": "REQ_1", "fact_type": "LINEUPS", "requirement_level": "REQUIRED_FOR_PRICING", "allowed_tools": ["webfetch"], "max_age_hours": 24, "min_independent_sources": 1}],
    })
    prompt_with_plan = render_agent_execution_prompt(wo_with_plan)
    assert "Use only the allowed tools and queries listed in the FACT ACQUISITION PLAN." in prompt_with_plan
    assert "FACT ACQUISITION PLAN:" in prompt_with_plan
    assert not validate_rendered_prompt(prompt_with_plan, wo_with_plan)


def test_t3_retrieval_receipt_provenance_enum():
    """Verify RetrievalReceiptV1 requires valid provenance level enum."""
    rec = RetrievalReceiptV1(
        receipt_id="REC_001",
        tool="webfetch",
        query_or_url="https://example.com",
        retrieved_at="2026-07-27T10:00:00Z",
        normalized_excerpt="Excerpt",
        content_sha256="a" * 64,
        provenance_level="AGENT_ATTESTED_TOOL_RESULT",
    )
    assert rec.provenance_level == "AGENT_ATTESTED_TOOL_RESULT"


def test_t3_sport_protocol_market_effects():
    """Verify sport protocols apply market effects (feature, widen interval, downgrade, block)."""
    protocol = GLOBAL_SPORT_PROTOCOL_REGISTRY.get_strict("football")
    # Corner market missing stats returns LOW and ANALYSIS_ONLY
    dec = protocol.evaluate_market_readiness(
        canonical_event_id="EVT_001",
        market_family="corners",
        event_data={"home_team": "A", "away_team": "B", "competition": "EPL"},
        row_data={},
        evidence_pack={},
    )
    assert dec.quality_grade == "LOW"
    assert dec.allowed_action == "ANALYSIS_ONLY"
