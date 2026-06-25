"""Contracts and validators for agent artifacts generated from work orders."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from bet.pipeline.manifest import PipelineManifest
from bet.pipeline.artifact_gate import find_forbidden_decision_signals


def agent_steps_from_manifest(manifest: PipelineManifest | dict[str, Any]) -> list[str]:
    """Extract list of step IDs from manifest that are configured as agent_artifact."""
    steps_list = []
    if hasattr(manifest, "steps"):
        steps = manifest.steps
    elif isinstance(manifest, dict) and "steps" in manifest:
        steps = manifest["steps"]
    else:
        return []

    for step in steps:
        step_id = None
        exec_mode = None
        if hasattr(step, "id"):
            step_id = step.id
            exec_mode = getattr(step, "execution_mode", None)
        elif isinstance(step, dict):
            step_id = step.get("id")
            exec_mode = step.get("execution_mode")
        
        if step_id and exec_mode == "agent_artifact":
            steps_list.append(step_id)
    return steps_list


def required_agent_output_contract(step_id: str) -> dict[str, Any]:
    """Retrieve output contract requirements for a specific step."""
    from bet.pipeline.agent_work_orders import POLICIES
    if step_id not in POLICIES:
        raise ValueError(f"No policy defined for step_id: {step_id}")
    policy = POLICIES[step_id]
    return {
        "artifact_type": "AGENT_ARTIFACT",
        "step_id": step_id,
        "required_statuses": ["PASS", "BLOCK"],
        "schema_requirements": policy.schema_requirements,
        "forbidden_outputs": policy.forbidden_outputs,
        "hard_rules": policy.hard_rules,
    }


def validate_agent_artifact_for_work_order(
    artifact_data: dict[str, Any],
    work_order_data: dict[str, Any],
) -> list[str]:
    """Compare an agent-produced artifact against its work order rules."""
    errors = []
    
    # 1. basic matching
    step_id = work_order_data.get("step_id")
    if artifact_data.get("step_id") != step_id:
        errors.append(f"step_id mismatch: expected {step_id}, got {artifact_data.get('step_id')}")
        
    run_id = work_order_data.get("run_id")
    if artifact_data.get("run_id") != run_id:
        errors.append(f"run_id mismatch: expected {run_id}, got {artifact_data.get('run_id')}")
        
    betting_day = work_order_data.get("betting_day")
    if artifact_data.get("betting_day") != betting_day:
        errors.append(f"betting_day mismatch: expected {betting_day}, got {artifact_data.get('betting_day')}")
        
    # 2. artifact_type check
    if artifact_data.get("artifact_type") != "AGENT_ARTIFACT":
        errors.append(f"artifact_type must be AGENT_ARTIFACT, got {artifact_data.get('artifact_type')}")
        
    # 3. status check
    req_output = work_order_data.get("required_output", {})
    allowed_statuses = req_output.get("required_statuses", ["PASS", "BLOCK"])
    status = artifact_data.get("status")
    if status not in allowed_statuses:
        errors.append(f"status '{status}' not in allowed statuses {allowed_statuses}")
        
    # 4. schema requirements check
    schema_reqs = req_output.get("schema_requirements", {})
    if schema_reqs.get("point_in_time_as_of"):
        p_time = artifact_data.get("point_in_time_as_of")
        if not p_time or not isinstance(p_time, str):
            errors.append("point_in_time_as_of must be a non-empty string")
            
    if schema_reqs.get("source_bound"):
        if not artifact_data.get("source_bound", False):
            errors.append("source_bound must be true")
            
    if schema_reqs.get("no_pick_edge_stake_coupon_emitted"):
        if not artifact_data.get("no_pick_edge_stake_coupon_emitted", False):
            errors.append("no_pick_edge_stake_coupon_emitted must be true")
            
    if "production_selectable" in schema_reqs:
        if artifact_data.get("production_selectable") != schema_reqs["production_selectable"]:
            errors.append(f"production_selectable must be {schema_reqs['production_selectable']}")
            
    if "betting_decisions_enabled" in schema_reqs:
        if artifact_data.get("betting_decisions_enabled") != schema_reqs["betting_decisions_enabled"]:
            errors.append(f"betting_decisions_enabled must be {schema_reqs['betting_decisions_enabled']}")
            
    if schema_reqs.get("sources_required"):
        sources = artifact_data.get("sources", [])
        if not sources or not isinstance(sources, list):
            errors.append("sources must be a non-empty list")

    # 5. Forbidden fields in the actual artifact payload
    forbidden_keys = work_order_data.get("forbidden_outputs", [])
    if forbidden_keys:
        payload = artifact_data.get("payload", {})
        signals = find_forbidden_decision_signals(payload)
        for sig in signals:
            errors.append(f"Forbidden decision signal found in payload: {sig}")
            
    # 6. Step-specific contract checks
    payload = artifact_data.get("payload", {})
    if step_id == "S2.3":
        if "unknowns" not in artifact_data:
            errors.append("S2.3 artifact must contain an 'unknowns' list")
        if "gaps" not in payload and "enrichment_gaps" not in payload:
            errors.append("S2.3 payload must contain 'gaps' or 'enrichment_gaps'")
            
    elif step_id == "S2.5":
        if "providers" not in payload and "observations" not in payload:
            errors.append("S2.5 payload must contain 'providers' or 'observations'")
            
    elif step_id == "S2.7":
        if "disputed_facts" not in payload and "reconciliation" not in payload:
            errors.append("S2.7 payload must contain 'disputed_facts' or 'reconciliation'")
        if "evidence_refs" not in artifact_data or not artifact_data.get("evidence_refs"):
            errors.append("S2.7 artifact must contain non-empty 'evidence_refs'")
            
    elif step_id == "S2.9":
        if "s3_may_proceed" not in payload and "readiness" not in payload:
            errors.append("S2.9 payload must specify 's3_may_proceed' or 'readiness'")
            
    elif step_id == "S5":
        categories = ["injuries", "motivation", "travel", "morale", "upset_risk"]
        for cat in categories:
            found = False
            for k in payload.keys():
                if cat in k.lower():
                    found = True
                    break
            if not found:
                errors.append(f"S5 payload must contain context check for category '{cat}'")

    return errors


def agent_artifact_template_for_step(step_id: str, betting_day: str, run_id: str) -> dict[str, Any]:
    """Construct an empty artifact template matching step contract expectations."""
    from bet.pipeline.agent_work_orders import POLICIES
    if step_id not in POLICIES:
        raise ValueError(f"No policy defined for step_id: {step_id}")
    
    template = {
        "schema_version": 1,
        "artifact_type": "AGENT_ARTIFACT",
        "step_id": step_id,
        "status": "PASS",
        "betting_day": betting_day,
        "run_id": run_id,
        "sport": None,
        "fixture_id": None,
        "fixture_key": None,
        "point_in_time_as_of": "2026-06-25T12:00:00Z",
        "source_bound": True,
        "no_pick_edge_stake_coupon_emitted": True,
        "production_selectable": False,
        "betting_decisions_enabled": False,
        "sources": [],
        "unknowns": [],
        "blocked_reasons": [],
        "evidence_refs": [],
        "payload": {}
    }
    
    if step_id == "S2.3":
        template["payload"] = {
            "enrichment_gaps": []
        }
        template["unknowns"] = ["missing_team_names"]
        template["sources"] = ["tipsters_s2"]
    elif step_id == "S2.5":
        template["payload"] = {
            "observations": []
        }
        template["sources"] = ["tipsters_s2", "odds_portal"]
    elif step_id == "S2.7":
        template["payload"] = {
            "disputed_facts": []
        }
        template["evidence_refs"] = [f"artifact_S2.5_for_{run_id}"]
        template["sources"] = ["tipsters_s2"]
    elif step_id == "S2.9":
        template["payload"] = {
            "s3_may_proceed": True
        }
        template["sources"] = ["reconciled_facts_s2.7"]
    elif step_id == "S5":
        template["payload"] = {
            "injuries_context": {},
            "motivation_context": {},
            "travel_schedule": {},
            "morale_context": {},
            "upset_risk": {}
        }
        template["sources"] = ["injuries_db", "travel_db"]
        
    return template
