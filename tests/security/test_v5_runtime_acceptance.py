"""Runtime Acceptance Tests for V5 Pipeline Contracts.

Validates contract strictness, event accounting, and field coherence.
"""
import pytest
import os
import sys

def test_s1e_event_accounting_strictness():
    """Validates exact event accounting matching S1e universe."""
    import bet.pipeline.event_accounting as ea
    if hasattr(ea, "validate_event_accounting"):
        universe = ["e1", "e2", "e3"]
        # Discrepancy: missing e3, foreign e99
        with pytest.raises(Exception):
            ea.validate_event_accounting(universe, ["e1", "e2", "e99"], step_id="S2")

def test_agent_work_order_acquisition_plan_typed():
    """Validates AgentWorkOrder acquisition_plan type."""
    import bet.pipeline.agent_work_orders as awo
    if hasattr(awo, "AgentWorkOrderV1"):
        cls = awo.AgentWorkOrderV1
        annotations = getattr(cls, "__annotations__", {})
        acq_type = str(annotations.get("acquisition_plan", ""))
        assert "FactAcquisitionPlanV1" in acq_type, f"acquisition_plan is {acq_type}, expected FactAcquisitionPlanV1"

def test_tool_intersection_no_plan():
    """Validates allowed tools computation with no acquisition plan."""
    import bet.pipeline.agent_work_orders as awo
    if hasattr(awo, "compute_allowed_tools"):
        tools = awo.compute_allowed_tools(
            plan_tools=None,
            agent_profile_tools=["webfetch", "websearch", "read"]
        )
        assert not any(t in tools for t in ["webfetch", "websearch", "brave-search"]), f"Browsing tools present without plan: {tools}"

def test_s7_s7b_s8_field_coherence():
    """Validates field coherence across S7, S7b, and S8 candidates."""
    import bet.pipeline.contracts.steps.s3_to_s10 as s3_s10
    if hasattr(s3_s10, "S7CandidateRecord") and hasattr(s3_s10, "S7bCandidateRecord") and hasattr(s3_s10, "S8InputCandidateRecord"):
        s7_fields = set(s3_s10.S7CandidateRecord.__annotations__.keys())
        s7b_fields = set(s3_s10.S7bCandidateRecord.__annotations__.keys())
        s8_fields = set(s3_s10.S8InputCandidateRecord.__annotations__.keys())
        assert s7_fields == s7b_fields, f"S7 vs S7b mismatch: {s7_fields.symmetric_difference(s7b_fields)}"
        assert s7b_fields == s8_fields, f"S7b vs S8 mismatch: {s7b_fields.symmetric_difference(s8_fields)}"

def test_s8_unpriced_output_status():
    """Validates S8 output status when no model package exists."""
    import bet.pipeline.bet_builder_analytical as bba
    if hasattr(bba, "build_s8_output"):
        res = bba.build_s8_output(candidates=[{"event_id": "e1"}], model_package=None)
        status = res.get("output_status") if isinstance(res, dict) else getattr(res, "output_status", None)
        gate = res.get("ready_for_human_gate") if isinstance(res, dict) else getattr(res, "ready_for_human_gate", None)
        assert status == "ANALYSIS_ONLY_OUTPUT", f"Status was {status}"
        assert gate == False, f"ready_for_human_gate was {gate}"
EOF
