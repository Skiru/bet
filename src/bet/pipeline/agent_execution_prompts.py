"""Prompt rendering helpers for agent work orders in BET PIPELINE V5."""
from __future__ import annotations

from typing import Any


STEP_FOCUS = {
    "S2.3": [
        "Detect missing data and enrichment gaps in current fixtures.",
        "Categorize gaps as BLOCKING or NON_BLOCKING.",
    ],
    "S2.5": [
        "Collect provider observations for shortlisted fixtures.",
        "Preserve provider names, retrieval timestamps, and exact claims.",
    ],
    "S2.7": [
        "Reconcile conflicting claims across providers.",
        "Mark unresolved conflicts explicitly without guessing.",
    ],
    "S2.9": [
        "Evaluate data readiness for stats and probability modeling.",
        "Check whether all required facts are present for each fixture.",
    ],
    "S5": [
        "Evaluate context, motivation, lineups, travel, and volatility risks.",
        "Flag unacceptable risk factors fail-closed.",
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

    return "\n".join(prompt_lines)
