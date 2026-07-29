"""Prompt rendering helpers for agent work orders in BET PIPELINE V5."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


STEP_FOCUS = {
    "S2.3": [
        "Focus on enrichment gaps, unknowns, missing sources, and whether gaps are bounded or blocking.",
    ],
    "S2.5": [
        "Focus on provider observations only as source-bound enrichment evidence.",
    ],
    "S2.7": [
        "Focus on fact reconciliation, disputed facts, unknowns, and evidence refs.",
    ],
    "S2.9": [
        "Focus on readiness only and whether S3 may proceed.",
    ],
    "S5": [
        "Focus on injuries/lineups, motivation/tournament context, travel/fatigue, morale/recent form, and upset/volatility risk.",
    ],
}


def render_agent_execution_prompt(work_order: dict[str, Any] | Any) -> str:
    """Render a strict copy-paste execution prompt for a Kilo/agent session.

    Consumes both regular AgentWorkOrder and ChunkWorkOrderV1 without missing key errors.
    """
    if hasattr(work_order, "model_dump"):
        wo = work_order.model_dump()
    elif isinstance(work_order, dict):
        wo = dict(work_order)
    else:
        wo = dict(getattr(work_order, "__dict__", {}))

    wo_id = wo.get("work_order_id") or wo.get("chunk_id") or "WO-UNKNOWN"
    pipeline_id = wo.get("pipeline_id") or "bet_pipeline_v1"
    agent_name = wo.get("agent") or wo.get("agent_name") or "bet-executor"
    step_id = wo.get("step_id") or "S2.3"
    betting_day = wo.get("betting_day") or ""
    run_id = wo.get("run_id") or ""
    runtime_mode = wo.get("runtime_mode") or "DRY_RUN"

    prompt_lines: list[str] = [
        f"TASK_ID=AGENT_ARTIFACT_EXECUTION_{step_id}",
        f"WORK_ORDER_ID={wo_id}",
        f"PIPELINE_ID={pipeline_id}",
        f"BETTING_DAY={betting_day}",
        f"RUN_ID={run_id}",
        f"STEP_ID={step_id}",
        f"AGENT={agent_name}",
        f"RUNTIME_MODE={runtime_mode}",
        "",
        "ROLE:",
        "You are executing a deterministic AGENT_ARTIFACT work order.",
        "Use only the evidence already referenced by this work order.",
        "Return BLOCK instead of guessing.",
        "Do not emit pick, edge, stake, coupon, parlay or accumulator.",
        "Do not write to betting/data, betting/coupons, reports or production DB.",
    ]

    if wo.get("acquisition_plan"):
        prompt_lines.append("Use only the allowed tools and queries listed in the FACT ACQUISITION PLAN. Open-ended browsing remains forbidden.")
    else:
        prompt_lines.append("Do not call external APIs or browse externally; use only the evidence provided in the input artifacts.")

    prompt_lines.extend([
        "Do not include secrets.",
        "Do not include production write instructions.",
        "",
        "INPUT REFS:",
    ])

    input_refs = wo.get("input_refs") or ()
    for ref in input_refs:
        ref_dict = ref if isinstance(ref, dict) else getattr(ref, "__dict__", {})
        prompt_lines.append(
            "- "
            f"step_id={ref_dict.get('step_id')} "
            f"artifact_kind={ref_dict.get('artifact_kind')} "
            f"path={ref_dict.get('path')} "
            f"required={ref_dict.get('required')} "
            f"sha256={ref_dict.get('sha256')}"
        )

    req_out = wo.get("required_output") or {}
    exp_path = req_out.get("expected_path") if isinstance(req_out, dict) else wo.get("expected_artifact_path", "")
    exp_type = req_out.get("artifact_type") if isinstance(req_out, dict) else wo.get("expected_artifact_type", "AGENT_ARTIFACT")

    prompt_lines.extend(
        [
            "",
            "EXPECTED OUTPUT:",
            f"expected_path={exp_path}",
            f"artifact_type={exp_type}",
            f"allowed_statuses={wo.get('allowed_artifact_statuses', ('PASS', 'BLOCK'))}",
            "",
            "HARD RULES:",
        ]
    )

    for rule in wo.get("hard_rules", ()):
        prompt_lines.append(f"- {rule}")

    prompt_lines.extend(
        [
            "",
            "FORBIDDEN OUTPUTS:",
        ]
    )

    for verb in wo.get("forbidden_outputs", ()):
        prompt_lines.append(f"- {verb}")

    if step_id in STEP_FOCUS:
        prompt_lines.append("")
        prompt_lines.append("STEP FOCUS:")
        for focus in STEP_FOCUS[step_id]:
            prompt_lines.append(f"- {focus}")

    if wo.get("acquisition_plan"):
        prompt_lines.extend([
            "",
            "FACT ACQUISITION PLAN:",
            json.dumps(wo["acquisition_plan"], indent=2),
        ])

    return "\n".join(prompt_lines)


def load_work_order(path: str | Path) -> dict[str, Any]:
    """Load work order JSON from disk."""
    p = Path(path).resolve(strict=True)
    return json.loads(p.read_text(encoding="utf-8"))


def expected_artifact_path_from_work_order(work_order: dict[str, Any] | Any) -> Path:
    """Extract expected artifact output path from a work order."""
    if hasattr(work_order, "model_dump"):
        wo = work_order.model_dump()
    elif isinstance(work_order, dict):
        wo = dict(work_order)
    else:
        wo = {}
    req_out = wo.get("required_output") or {}
    if isinstance(req_out, dict) and req_out.get("expected_path"):
        return Path(req_out["expected_path"])
    return Path(wo.get("expected_artifact_path") or "")


def render_agent_artifact_skeleton(work_order: dict[str, Any] | Any, status: str = "BLOCK") -> dict[str, Any]:
    """Render a dict skeleton artifact for a work order."""
    if hasattr(work_order, "model_dump"):
        wo = work_order.model_dump()
    elif isinstance(work_order, dict):
        wo = dict(work_order)
    else:
        wo = {}
    step_id = wo.get("step_id") or "S2.3"
    wo_id = wo.get("work_order_id") or wo.get("chunk_id") or ""
    wo_sha = wo.get("work_order_sha256") or wo.get("chunk_work_order_sha256") or "1" * 64
    agent = wo.get("agent") or wo.get("agent_name") or "bet-executor"
    day = wo.get("betting_day") or ""
    run_id = wo.get("run_id") or ""

    return {
        "schema_version": 1,
        "artifact_type": "AGENT_ARTIFACT",
        "step_id": step_id,
        "status": status,
        "betting_day": day,
        "run_id": run_id,
        "work_order_id": wo_id,
        "work_order_sha256": wo_sha,
        "producer_agent_id": agent,
        "agent_id": agent,
        "source_bound": True,
        "no_pick_edge_stake_coupon_emitted": True,
        "production_selectable": False,
        "betting_decisions_enabled": False,
        "sources": ["agent_execution"],
        "unknowns": [],
        "blocked_reasons": ["TEMPLATE_NOT_FILLED"],
        "evidence_refs": [],
        "event_records": [],
        "payload": {"approval_state": "NOT_FINAL_TEMPLATE", "s3_may_proceed": False},
    }


def validate_rendered_prompt(prompt_text: str, work_order: dict[str, Any] | Any) -> list[str]:
    """Validate that a rendered prompt contains all required work order elements."""
    errors = []
    if not prompt_text or not isinstance(prompt_text, str):
        errors.append("PROMPT_EMPTY")
        return errors
    if hasattr(work_order, "model_dump"):
        wo = work_order.model_dump()
    elif isinstance(work_order, dict):
        wo = dict(work_order)
    else:
        wo = {}
    wo_id = wo.get("work_order_id") or wo.get("chunk_id")
    if wo_id and wo_id not in prompt_text:
        errors.append(f"WORK_ORDER_ID_MISSING:{wo_id}")
    return errors
