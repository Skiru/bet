"""Render deterministic execution prompts for agent work orders."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from bet.pipeline.agent_artifact_contracts import agent_artifact_template_for_step


REQUIRED_WORK_ORDER_KEYS = (
    "work_order_id",
    "pipeline_id",
    "betting_day",
    "run_id",
    "step_id",
    "agent",
    "runtime_mode",
    "input_refs",
    "required_output",
    "hard_rules",
    "forbidden_outputs",
    "instructions",
)


STEP_FOCUS = {
    "S2.3": [
        "Focus on enrichment gaps, unknowns, missing sources, and whether gaps are bounded or blocking.",
        "Flag missing required identity or source evidence explicitly.",
    ],
    "S2.5": [
        "Focus on provider observations only as source-bound enrichment evidence.",
        "Do not promote providers, change provider selection, or suggest provider switching.",
    ],
    "S2.7": [
        "Focus on fact reconciliation, disputed facts, unknowns, and evidence refs.",
        "If facts cannot be reconciled from provided evidence, keep them UNKNOWN or BLOCK.",
    ],
    "S2.9": [
        "Focus on readiness only and whether S3 may proceed.",
        "PASS requires evidence refs tied to S2.3, S2.5, and S2.7 artifacts.",
        "BLOCK if the available evidence is insufficient for a safe readiness decision.",
    ],
    "S5": [
        "Focus on injuries/lineups, motivation/tournament context, travel/fatigue, morale/recent form, and upset/volatility risk.",
        "Do not emit a coupon and do not bypass S7, S7b, or S8.",
    ],
}


FINAL_OUTPUT_SCHEMA = {
    "schema_version": 1,
    "artifact_type": "AGENT_ARTIFACT",
    "step_id": "<match work order step_id>",
    "status": "PASS|BLOCK",
    "betting_day": "<match work order betting_day>",
    "run_id": "<match work order run_id>",
    "sport": "string|null",
    "fixture_id": "string|number|null",
    "fixture_key": "string|null",
    "point_in_time_as_of": "ISO-8601 string|null",
    "source_bound": "boolean",
    "no_pick_edge_stake_coupon_emitted": True,
    "production_selectable": False,
    "betting_decisions_enabled": False,
    "sources": ["source-id"],
    "unknowns": ["UNKNOWN item"],
    "blocked_reasons": ["reason when status=BLOCK"],
    "evidence_refs": ["artifact ref"],
    "payload": {"step_specific": "content"},
}


def load_work_order(path: Path) -> dict[str, Any]:
    """Load a work order JSON object from disk."""
    path = Path(path)
    if not path.is_file():
        raise ValueError(f"Work order file not found: {path}")

    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in work order {path}: {exc}") from exc
    except OSError as exc:
        raise ValueError(f"Failed to read work order {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"Work order JSON top-level must be an object at {path}")

    missing = [key for key in REQUIRED_WORK_ORDER_KEYS if key not in data]
    if missing:
        raise ValueError(f"Work order missing required keys: {', '.join(missing)}")

    return data


def expected_artifact_path_from_work_order(work_order: dict[str, Any]) -> Path:
    """Resolve the expected artifact path defined by the work order."""
    required_output = work_order.get("required_output")
    if not isinstance(required_output, dict):
        raise ValueError("Work order required_output must be an object")

    expected_path = required_output.get("expected_path")
    if not isinstance(expected_path, str) or not expected_path.strip():
        raise ValueError("Work order required_output.expected_path must be a non-empty string")

    return Path(expected_path)


def render_agent_artifact_skeleton(work_order: dict[str, Any]) -> dict[str, Any]:
    """Render a safe, non-approving artifact skeleton for the target step."""
    step_id = str(work_order.get("step_id", "")).strip()
    betting_day = str(work_order.get("betting_day", "")).strip()
    run_id = str(work_order.get("run_id", "")).strip()

    skeleton = agent_artifact_template_for_step(step_id, betting_day, run_id)
    skeleton["work_order_id"] = work_order.get("work_order_id")
    skeleton["payload"]["work_order_id"] = work_order.get("work_order_id")
    return skeleton


def render_agent_execution_prompt(work_order: dict[str, Any]) -> str:
    """Render a strict copy-paste execution prompt for a Kilo/agent session."""
    prompt_lines: list[str] = [
        f"TASK_ID=AGENT_ARTIFACT_EXECUTION_{work_order['step_id']}",
        f"WORK_ORDER_ID={work_order['work_order_id']}",
        f"PIPELINE_ID={work_order['pipeline_id']}",
        f"BETTING_DAY={work_order['betting_day']}",
        f"RUN_ID={work_order['run_id']}",
        f"STEP_ID={work_order['step_id']}",
        f"AGENT={work_order['agent']}",
        f"RUNTIME_MODE={work_order['runtime_mode']}",
        "",
        "ROLE:",
        "You are executing a deterministic AGENT_ARTIFACT work order.",
        "Use only the evidence already referenced by this work order.",
        "Return BLOCK instead of guessing.",
        "Do not emit pick, edge, stake, coupon, parlay or accumulator.",
        "Do not write to betting/data, betting/coupons, reports or production DB.",
    ]

    if work_order.get("acquisition_plan"):
        prompt_lines.append("Use only the allowed tools and queries listed in the FACT ACQUISITION PLAN. Open-ended browsing remains forbidden.")
    else:
        prompt_lines.append("Do not call external APIs or browse externally; use only the evidence provided in the input artifacts.")

    prompt_lines.extend([
        "Do not include secrets.",
        "Do not include production write instructions.",
        "",
        "INPUT REFS:",
    ])

    for ref in work_order["input_refs"]:
        prompt_lines.append(
            "- "
            f"step_id={ref.get('step_id')} "
            f"artifact_kind={ref.get('artifact_kind')} "
            f"path={ref.get('path')} "
            f"required={ref.get('required')} "
            f"sha256={ref.get('sha256')}"
        )

    prompt_lines.extend(
        [
            "",
            "EXPECTED OUTPUT:",
            f"- path={expected_artifact_path_from_work_order(work_order)}",
            f"- artifact_type={work_order['required_output'].get('artifact_type')}",
            f"- allowed_statuses={','.join(work_order['required_output'].get('required_statuses', []))}",
            "",
            "FORBIDDEN OUTPUTS:",
        ]
    )
    prompt_lines.extend(f"- {item}" for item in work_order["forbidden_outputs"])

    prompt_lines.extend(["", "HARD RULES:"])
    prompt_lines.extend(f"- {item}" for item in work_order["hard_rules"])

    instructions = work_order["instructions"]
    prompt_lines.extend(
        [
            "",
            "SUMMARY:",
            str(instructions.get("summary", "")),
            "",
            "STEP FOCUS:",
        ]
    )
    prompt_lines.extend(f"- {item}" for item in STEP_FOCUS.get(work_order["step_id"], []))

    if work_order.get("acquisition_plan"):
        acq = work_order["acquisition_plan"]
        prompt_lines.extend(
            [
                "",
                "FACT ACQUISITION PLAN:",
                f"- plan_id={acq.get('plan_id')}",
                f"- canonical_event_id={acq.get('canonical_event_id')}",
                f"- sport={acq.get('sport')}",
                f"- max_queries={acq.get('max_queries', 10)}",
            ]
        )
        reqs = acq.get("requirements") or acq.get("fact_requirements") or []
        for req in reqs:
            if isinstance(req, dict):
                tools_str = ",".join(req.get("allowed_tools", ()))
                prompt_lines.append(
                    f"  * requirement_id={req.get('requirement_id')} "
                    f"fact_type={req.get('fact_type')} "
                    f"level={req.get('requirement_level')} "
                    f"tools={tools_str} "
                    f"max_age_hours={req.get('max_age_hours', 48)} "
                    f"min_sources={req.get('min_independent_sources', 1)}"
                )
            elif isinstance(req, str):
                prompt_lines.append(f"  * requirement={req}")

    prompt_lines.extend(["", "MUST DO:"])
    prompt_lines.extend(f"- {item}" for item in instructions.get("must_do", []))

    prompt_lines.extend(["", "MUST NOT DO:"])
    prompt_lines.extend(f"- {item}" for item in instructions.get("must_not_do", []))

    prompt_lines.extend(
        [
            "",
            "UNKNOWN POLICY:",
            str(instructions.get("unknown_policy", "")),
            "",
            "OUTPUT CONTRACT:",
        ]
    )
    prompt_lines.extend(f"- {item}" for item in instructions.get("output_contract", []))

    prompt_lines.extend(
        [
            "",
            "JSON ARTIFACT SCHEMA SKELETON:",
            "```json",
            json.dumps(render_agent_artifact_skeleton(work_order), indent=2, sort_keys=True),
            "```",
            "",
            "FINAL OUTPUT SCHEMA:",
            "```json",
            json.dumps(FINAL_OUTPUT_SCHEMA, indent=2, sort_keys=True),
            "```",
            "",
            "FINAL OUTPUT RULE:",
            "Return exactly one AGENT_ARTIFACT JSON object for the expected path.",
        ]
    )

    return "\n".join(prompt_lines).strip() + "\n"


def validate_rendered_prompt(prompt: str, work_order: dict[str, Any]) -> list[str]:
    """Validate a rendered prompt against required contract markers."""
    errors: list[str] = []
    required_fragments = [
        f"TASK_ID=AGENT_ARTIFACT_EXECUTION_{work_order['step_id']}",
        f"WORK_ORDER_ID={work_order['work_order_id']}",
        f"PIPELINE_ID={work_order['pipeline_id']}",
        f"BETTING_DAY={work_order['betting_day']}",
        f"RUN_ID={work_order['run_id']}",
        f"STEP_ID={work_order['step_id']}",
        f"AGENT={work_order['agent']}",
        f"RUNTIME_MODE={work_order['runtime_mode']}",
        str(expected_artifact_path_from_work_order(work_order)),
        "Return BLOCK instead of guessing.",
        "Do not emit pick, edge, stake, coupon, parlay or accumulator.",
        "Do not write to betting/data, betting/coupons, reports or production DB.",
        "JSON ARTIFACT SCHEMA SKELETON:",
        "FINAL OUTPUT SCHEMA:",
    ]
    if work_order.get("acquisition_plan"):
        required_fragments.append("Use only the allowed tools and queries listed in the FACT ACQUISITION PLAN.")
    else:
        required_fragments.append("Do not call external APIs or browse externally;")
    for fragment in required_fragments:
        if fragment not in prompt:
            errors.append(f"Prompt missing required fragment: {fragment}")

    for ref in work_order.get("input_refs", []):
        for fragment in (
            f"step_id={ref.get('step_id')}",
            f"path={ref.get('path')}",
            f"required={ref.get('required')}",
            f"sha256={ref.get('sha256')}",
        ):
            if fragment not in prompt:
                errors.append(f"Prompt missing input ref fragment: {fragment}")

    for forbidden_output in work_order.get("forbidden_outputs", []):
        if forbidden_output not in prompt:
            errors.append(f"Prompt missing forbidden output: {forbidden_output}")

    for hard_rule in work_order.get("hard_rules", []):
        if hard_rule not in prompt:
            errors.append(f"Prompt missing hard rule: {hard_rule}")

    for item in STEP_FOCUS.get(work_order.get("step_id"), []):
        if item not in prompt:
            errors.append(f"Prompt missing step focus item: {item}")

    for forbidden_fragment in (
        "BET_PIPELINE_WRITE_ACK",
        "I_UNDERSTAND_LIVE_PROVIDER_CALLS",
        "git push",
        "production execution",
    ):
        if forbidden_fragment in prompt:
            errors.append(f"Prompt contains forbidden fragment: {forbidden_fragment}")

    return errors
