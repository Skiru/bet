"""Contracts and validators for agent artifacts generated from work orders."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from bet.pipeline.artifact_gate import find_forbidden_decision_signals
from bet.pipeline.manifest import PipelineManifest


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


def required_agent_output_contract(
    step_id: str,
    *,
    manifest: Any | None = None,
    work_order: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Retrieve output contract requirements for a specific step."""
    from bet.pipeline.agent_work_orders import POLICIES
    from bet.pipeline.manifest import get_step_hard_rules

    if step_id not in POLICIES:
        raise ValueError(f"No policy defined for step_id: {step_id}")
    policy = POLICIES[step_id]

    if work_order and isinstance(work_order.get("hard_rules"), list):
        hard_rules = list(work_order["hard_rules"])
    else:
        hard_rules = get_step_hard_rules(step_id, manifest=manifest)

    return {
        "artifact_type": "AGENT_ARTIFACT",
        "step_id": step_id,
        "required_statuses": ["PASS", "BLOCK", "COMMAND_REQUEST"],
        "schema_requirements": policy.schema_requirements,
        "forbidden_outputs": policy.forbidden_outputs,
        "hard_rules": hard_rules,
    }


def _is_exact_step_ref(ref: str, step_id: str) -> bool:
    lowered = ref.lower()
    if any(bad in lowered for bad in ("fake", "garbage", "not-artifact", "not_artifact")) or ref.endswith(".txt"):
        return False
    name = Path(ref).name
    pattern = rf"(?:^|[\/\._\-]){re.escape(step_id)}(?:$|[\/\._\-])"
    return bool(re.search(pattern, name) or re.search(pattern, ref))


def _refs_cover_required_steps(
    evidence_refs: list[str], required_steps: tuple[str, ...]
) -> bool:
    for required_step in required_steps:
        if not any(_is_exact_step_ref(ref, required_step) for ref in evidence_refs):
            return False
    return True


def _contains_provider_promotion(node: Any) -> bool:
    forbidden_tokens = (
        "promote_provider",
        "provider_promotion",
        "preferred_provider",
        "promoted_provider",
        "selected_provider",
        "switch_provider",
    )
    if isinstance(node, dict):
        for key, value in node.items():
            normalized_key = str(key).strip().lower()
            if any(token in normalized_key for token in forbidden_tokens):
                return True
            if _contains_provider_promotion(value):
                return True
        return False
    if isinstance(node, (list, tuple)):
        return any(_contains_provider_promotion(item) for item in node)
    if isinstance(node, str):
        lowered = node.strip().lower()
        for token in forbidden_tokens:
            if token in lowered:
                # Check if this token appears as a positive assignment or directive
                if re.search(rf"\b{re.escape(token)}\s*[:=]|\b{re.escape(token)}\s+to\b", lowered):
                    return True
        if any(token in lowered for token in forbidden_tokens):
            negated_phrases = (
                "do_not_change_provider_selection",
                "no_provider_promotion",
                "must_not_promote",
                "no provider promotion",
                "do not promote",
                "disallowed",
                "forbidden",
            )
            if not any(phrase in lowered for phrase in negated_phrases):
                return True
    return False


def validate_agent_artifact_for_work_order(
    artifact_data: dict[str, Any],
    work_order_data: dict[str, Any],
) -> list[str]:
    """Compare an agent-produced artifact against its work order rules."""

    def _non_empty_list(value: Any) -> bool:
        return isinstance(value, list) and len(value) > 0

    def _non_empty_string(value: Any) -> bool:
        return isinstance(value, str) and bool(value.strip())

    def _payload_contains_any(payload: dict[str, Any], keys: tuple[str, ...]) -> bool:
        return any(key in payload for key in keys)

    def _has_placeholder(node: Any, is_pass_status: bool = False) -> str | None:
        if isinstance(node, str):
            s = node.strip()
            if s.startswith("TODO_") or s in (
                "TODO_FILL_BY_AGENT",
                "NOT_FINAL_TEMPLATE",
                "TEMPLATE_NOT_FILLED",
            ):
                return f"placeholder value found: '{node}'"
        elif isinstance(node, dict):
            for k, v in node.items():
                if isinstance(k, str):
                    ks = k.strip()
                    if ks.startswith("TODO_") or ks in (
                        "TODO_FILL_BY_AGENT",
                        "NOT_FINAL_TEMPLATE",
                        "TEMPLATE_NOT_FILLED",
                    ):
                        return f"placeholder key found: '{k}'"
                    if is_pass_status and ks in ("template_status", "approval_state"):
                        return f"template-only key '{k}' forbidden in PASS artifacts"
                res = _has_placeholder(v, is_pass_status)
                if res:
                    return res
        elif isinstance(node, (list, tuple, set)):
            for item in node:
                res = _has_placeholder(item, is_pass_status)
                if res:
                    return res
        return None

    errors = []

    # 1. basic matching
    step_id = work_order_data.get("step_id")
    if artifact_data.get("step_id") != step_id:
        errors.append(
            f"step_id mismatch: expected {step_id}, got {artifact_data.get('step_id')}"
        )

    run_id = work_order_data.get("run_id")
    if artifact_data.get("run_id") != run_id:
        errors.append(
            f"run_id mismatch: expected {run_id}, got {artifact_data.get('run_id')}"
        )

    betting_day = work_order_data.get("betting_day")
    if artifact_data.get("betting_day") != betting_day:
        errors.append(
            f"betting_day mismatch: expected {betting_day}, got {artifact_data.get('betting_day')}"
        )

    # Determine run root and work order path
    req_output = work_order_data.get("required_output", {})
    expected_artifact_path_str = req_output.get("expected_path")
    if expected_artifact_path_str:
        art_parent = Path(expected_artifact_path_str).parent
        wo_path = art_parent / f"{step_id}_work_order.json"
        run_root = art_parent.parent
    else:
        wo_input_refs = work_order_data.get("input_refs", [])
        run_root = None
        for ref in wo_input_refs:
            ref_path = ref.get("path") if isinstance(ref, dict) else getattr(ref, "path", None)
            if ref_path:
                p_ref = Path(ref_path).resolve()
                if len(p_ref.parents) >= 2:
                    run_root = p_ref.parents[1]
                    break
        if run_root is None:
            repo_root = find_repo_root(Path(__file__))
            run_root = repo_root / "pipeline_runs" / betting_day / run_id
        wo_path = run_root / "artifacts" / f"{step_id}_work_order.json"

    # 1. Verify predecessors have not changed after work-order creation
    wo_input_refs = work_order_data.get("input_refs", [])
    for ref in wo_input_refs:
        ref_step_id = (
            ref.get("step_id")
            if isinstance(ref, dict)
            else getattr(ref, "step_id", None)
        )
        ref_path = (
            ref.get("path") if isinstance(ref, dict) else getattr(ref, "path", None)
        )
        ref_sha = (
            ref.get("sha256") if isinstance(ref, dict) else getattr(ref, "sha256", None)
        )
        if ref_path and ref_sha:
            p = Path(ref_path).resolve()
            if not p.exists():
                errors.append(
                    f"Predecessor path {ref_path} for {ref_step_id} does not exist"
                )
            else:
                from bet.pipeline.canonical_continuity import file_sha256

                actual_sha = file_sha256(p)
                if actual_sha != ref_sha:
                    errors.append(
                        f"Predecessor {ref_step_id} mutated after work-order creation: {actual_sha} vs {ref_sha}"
                    )

    # 2. Load the actual persisted work order from disk and verify its hash
    status_val = artifact_data.get("status")

    if status_val in ("PASS", "COMMAND_REQUEST"):
        if not wo_path.exists():
            errors.append(f"Persisted work order file missing at {wo_path}")
        else:
            from bet.pipeline.canonical_continuity import file_sha256

            actual_wo_sha = file_sha256(wo_path)
            if status_val in ("PASS", "COMMAND_REQUEST"):
                if "work_order_id" not in artifact_data:
                    errors.append(f"{status_val} artifact missing 'work_order_id'")
                elif artifact_data["work_order_id"] != work_order_data.get("work_order_id"):
                    errors.append(
                        f"work_order_id mismatch: {artifact_data['work_order_id']} vs {work_order_data.get('work_order_id')}"
                    )

                if "work_order_sha256" not in artifact_data:
                    errors.append(f"{status_val} artifact missing 'work_order_sha256'")
                elif artifact_data["work_order_sha256"] != actual_wo_sha:
                    errors.append(
                        f"work_order_sha256 mismatch: {artifact_data['work_order_sha256']} vs {actual_wo_sha}"
                    )

    # 2b. Producer agent binding check
    expected_agent = work_order_data.get("agent")
    actual_producer = (
        artifact_data.get("producer_agent_id")
        or artifact_data.get("payload", {}).get("producer_agent_id")
        or artifact_data.get("payload", {}).get("agent_id")
        or artifact_data.get("agent")
    )
    if status_val in ("PASS", "COMMAND_REQUEST"):
        if not actual_producer:
            errors.append(f"{status_val} artifact missing producer_agent_id / agent_id binding")
        elif actual_producer != expected_agent:
            errors.append(
                f"producer_agent_id mismatch: expected {expected_agent}, got {actual_producer}"
            )
    elif actual_producer and actual_producer != expected_agent:
        errors.append(
            f"producer_agent_id mismatch: expected {expected_agent}, got {actual_producer}"
        )

    # 2. artifact_type check
    if artifact_data.get("artifact_type") != "AGENT_ARTIFACT":
        errors.append(
            f"artifact_type must be AGENT_ARTIFACT, got {artifact_data.get('artifact_type')}"
        )

    # 3. status check
    req_output = work_order_data.get("required_output", {})
    allowed_statuses = req_output.get(
        "required_statuses", ["PASS", "BLOCK", "COMMAND_REQUEST"]
    )
    status = artifact_data.get("status")
    if status not in allowed_statuses:
        errors.append(f"status '{status}' not in allowed statuses {allowed_statuses}")

    payload = artifact_data.get("payload", {})
    if not isinstance(payload, dict):
        errors.append("payload must be an object")
        payload = {}

    blocked_reasons = artifact_data.get("blocked_reasons", [])
    sources = artifact_data.get("sources", [])
    evidence_refs = artifact_data.get("evidence_refs", [])
    is_pass = status == "PASS"
    is_block = status == "BLOCK"

    # 4. common safety invariants
    placeholder_error = _has_placeholder(artifact_data, is_pass_status=is_pass)
    if placeholder_error:
        errors.append(f"Artifact contains placeholder data: {placeholder_error}")

    if is_pass:
        if blocked_reasons != []:
            errors.append("PASS artifact must have empty blocked_reasons")
        if artifact_data.get("command_request") or payload.get("command_request"):
            errors.append("PASS artifact must not contain any command_request")

        # 9. Every PASS agent artifact must include valid event_records covering the full universe
        s1e_file = run_root / "data" / f"{betting_day}_s1e_event_universe.json"
        if s1e_file.exists():
            try:
                s1e_data = json.loads(s1e_file.read_text(encoding="utf-8"))
                universe_ids = set(s1e_data.get("canonical_event_ids", []))
            except Exception:
                universe_ids = set()
            if universe_ids:
                event_records = payload.get("event_records")
                if not isinstance(event_records, list):
                    errors.append(
                        "PASS agent artifact payload must contain 'event_records' list"
                    )
                else:
                    rec_ids = []
                    for idx, rec in enumerate(event_records):
                        if not isinstance(rec, dict):
                            errors.append(f"event_records[{idx}] must be a dictionary")
                            continue
                        eid = rec.get("canonical_event_id")
                        if not eid:
                            errors.append(
                                f"event_records[{idx}] missing 'canonical_event_id'"
                            )
                            continue
                        rec_ids.append(eid)
                    from collections import Counter

                    dups = [k for k, v in Counter(rec_ids).items() if v > 1]
                    if dups:
                        errors.append(f"Duplicate event IDs in event_records: {dups}")
                    rec_set = set(rec_ids)
                    missing_ids = sorted(universe_ids - rec_set)
                    extra_ids = sorted(rec_set - universe_ids)
                    if missing_ids:
                        errors.append(
                            f"Missing event IDs in event_records: {missing_ids}"
                        )
                    if extra_ids:
                        errors.append(
                            f"Extra/unknown event IDs in event_records: {extra_ids}"
                        )

    if artifact_data.get("no_pick_edge_stake_coupon_emitted") is not True:
        errors.append("no_pick_edge_stake_coupon_emitted must be true")

    if artifact_data.get("production_selectable") is not False:
        errors.append("production_selectable must be false")

    if artifact_data.get("betting_decisions_enabled") is not False:
        errors.append("betting_decisions_enabled must be false")

    if is_block and not _non_empty_list(blocked_reasons):
        errors.append("BLOCK artifacts must contain non-empty blocked_reasons")

    if status == "COMMAND_REQUEST":
        cmd_req = artifact_data.get("command_request")
        if cmd_req is None:
            cmd_req = payload.get("command_request")
        if not cmd_req:
            errors.append(
                "COMMAND_REQUEST artifacts must contain a non-empty command_request"
            )
        else:
            from bet.pipeline.command_registry import (
                CommandRequestError,
                resolve_command_request,
            )

            try:
                resolve_command_request(cmd_req)
            except CommandRequestError as exc:
                errors.append(str(exc))

        forbidden_signals = [
            "pick",
            "picks",
            "selection",
            "selections",
            "bet",
            "betting_decision",
            "edge",
            "ev",
            "expected_value",
            "stake",
            "staking",
            "coupon",
            "accumulator",
            "parlay",
        ]
        for key in payload.keys():
            if any(sig in str(key).lower() for sig in forbidden_signals):
                errors.append(f"COMMAND_REQUEST payload contains forbidden key: {key}")

    # 5. PASS-only schema requirements check
    schema_reqs = req_output.get("schema_requirements", {})
    if is_pass and schema_reqs.get("point_in_time_as_of"):
        p_time = artifact_data.get("point_in_time_as_of")
        if not _non_empty_string(p_time):
            errors.append("point_in_time_as_of must be a non-empty string")

    if is_pass and schema_reqs.get("source_bound"):
        if not artifact_data.get("source_bound", False):
            errors.append("source_bound must be true")

    if is_pass and "production_selectable" in schema_reqs:
        if (
            artifact_data.get("production_selectable")
            != schema_reqs["production_selectable"]
        ):
            errors.append(
                f"production_selectable must be {schema_reqs['production_selectable']}"
            )

    if is_pass and "betting_decisions_enabled" in schema_reqs:
        if (
            artifact_data.get("betting_decisions_enabled")
            != schema_reqs["betting_decisions_enabled"]
        ):
            errors.append(
                f"betting_decisions_enabled must be {schema_reqs['betting_decisions_enabled']}"
            )

    if is_pass and schema_reqs.get("sources_required"):
        if not _non_empty_list(sources):
            errors.append("sources must be a non-empty list")

    # 6. Forbidden fields in the actual artifact payload
    forbidden_keys = work_order_data.get("forbidden_outputs", [])
    if forbidden_keys:
        scan_payload = payload
        if step_id == "S5":
            # S5 must preserve S4 analytical identity and pricing facts such as
            # `selection` and `ev`. They are inputs, not an execution decision.
            # Decision-shaped fields outside the candidate partitions remain
            # forbidden, and candidate records get a narrower execution scan.
            scan_payload = {
                key: value
                for key, value in payload.items()
                if key not in {"candidates", "rejected_candidates"}
            }
            execution_keys = {
                "internal_pick",
                "recommended_pick",
                "stake",
                "staking",
                "coupon",
                "parlay",
                "accumulator",
                "betting_decision",
            }
            for category in ("candidates", "rejected_candidates"):
                for index, candidate in enumerate(payload.get(category, [])):
                    if isinstance(candidate, dict):
                        for key in candidate:
                            if str(key).strip().lower() in execution_keys:
                                errors.append(
                                    f"Forbidden execution signal found in payload.{category}[{index}]: {key}"
                                )
        signals = find_forbidden_decision_signals(scan_payload)
        for sig in signals:
            errors.append(f"Forbidden decision signal found in payload: {sig}")

    # 7. Step-specific contract checks
    if step_id == "S2.3":
        if "unknowns" not in artifact_data:
            errors.append("S2.3 artifact must contain an 'unknowns' list")
        if is_pass:
            if not _payload_contains_any(payload, ("gaps", "enrichment_gaps")):
                errors.append(
                    "S2.3 PASS payload must contain 'gaps' or 'enrichment_gaps'"
                )
            if not _payload_contains_any(
                payload,
                (
                    "gaps_bounded",
                    "bounded_gaps",
                    "gaps_blocking",
                    "blocking_gaps",
                    "gaps_status",
                ),
            ):
                errors.append(
                    "S2.3 PASS must explicitly state whether gaps are bounded or blocking"
                )

    elif step_id == "S2.5":
        if is_pass:
            if not _payload_contains_any(
                payload, ("providers", "observations", "provider_observations")
            ):
                errors.append(
                    "S2.5 PASS payload must contain provider/source observations"
                )
            if _contains_provider_promotion(payload):
                errors.append(
                    "S2.5 PASS must not contain provider promotion or selection changes"
                )

    elif step_id == "S2.7":
        if is_pass:
            if not _payload_contains_any(payload, ("disputed_facts", "reconciliation")):
                errors.append(
                    "S2.7 PASS payload must contain 'disputed_facts' or 'reconciliation'"
                )
            if not _non_empty_list(evidence_refs):
                errors.append(
                    "S2.7 PASS artifact must contain non-empty 'evidence_refs'"
                )
            disputed_facts = payload.get("disputed_facts")
            reconciliation = payload.get("reconciliation")
            has_explicit_unknowns = _payload_contains_any(
                payload, ("unknown_facts", "unknowns", "unresolved_facts")
            )
            reconciliation_marks_unknowns = isinstance(reconciliation, dict) and any(
                key in reconciliation
                for key in (
                    "unknown_facts",
                    "unknowns",
                    "disputed_facts",
                    "unresolved_facts",
                )
            )
            if (
                not _non_empty_list(disputed_facts)
                and not has_explicit_unknowns
                and not reconciliation_marks_unknowns
            ):
                errors.append(
                    "S2.7 PASS must explicitly mark disputed or unknown facts"
                )

    elif step_id == "S2.9":
        if is_pass:
            if not payload:
                errors.append("S2.9 PASS payload must not be empty")
            readiness_verdict = payload.get("readiness")
            if not _non_empty_string(readiness_verdict):
                errors.append("S2.9 PASS payload must contain a readiness verdict")
            elif readiness_verdict != "PASS":
                errors.append("S2.9 PASS payload readiness verdict must be PASS")

            if set(payload.keys()) == {"s3_may_proceed"}:
                errors.append("S2.9 PASS must not rely on s3_may_proceed alone")

            if payload.get("s3_may_proceed") is not True:
                errors.append("S2.9 PASS s3_may_proceed must be true")

            if not _non_empty_list(evidence_refs):
                errors.append(
                    "S2.9 PASS artifact must contain non-empty 'evidence_refs'"
                )
            elif not _refs_cover_required_steps(
                evidence_refs, ("S2.3", "S2.5", "S2.7")
            ):
                errors.append(
                    "S2.9 PASS evidence_refs must include S2.3, S2.5, and S2.7 artifact refs"
                )

            # Semantic S2.9 Validation
            # Resolve run root dynamically from work order input refs
            run_root = None
            wo_input_refs = work_order_data.get("input_refs", [])
            for ref in wo_input_refs:
                ref_path = (
                    ref.get("path")
                    if isinstance(ref, dict)
                    else getattr(ref, "path", None)
                )
                if ref_path:
                    run_root = Path(ref_path).resolve().parents[1]
                    break
            if not run_root:
                repo_root = find_repo_root(Path(__file__))
                run_root = repo_root / "pipeline_runs" / betting_day / run_id
            resolved_run_root = run_root.resolve()

            bindings = payload.get("predecessor_bindings") or payload.get("bindings")
            if not isinstance(bindings, list):
                errors.append(
                    "S2.9 PASS payload must contain 'predecessor_bindings' list"
                )
                bindings = []

            bound_steps = {}
            for b in bindings:
                if not isinstance(b, dict):
                    errors.append("Binding must be a dictionary")
                    continue
                sid = b.get("step_id")
                if not sid:
                    errors.append("Binding missing 'step_id'")
                    continue
                if sid in bound_steps:
                    errors.append(f"Duplicate binding for {sid}")
                bound_steps[sid] = b

            expected_steps = {"S2.3", "S2.5", "S2.7"}
            if set(bound_steps.keys()) != expected_steps:
                errors.append(
                    f"S2.9 PASS must contain exactly S2.3, S2.5, and S2.7 bindings, got {sorted(bound_steps.keys())}"
                )

            wo_input_refs = work_order_data.get("input_refs", [])
            wo_refs_by_step = {}
            for ref in wo_input_refs:
                ref_step_id = (
                    ref.get("step_id")
                    if isinstance(ref, dict)
                    else getattr(ref, "step_id", None)
                )
                if ref_step_id:
                    wo_refs_by_step[ref_step_id] = ref

            for sid in expected_steps:
                b = bound_steps.get(sid)
                if not b:
                    continue

                for field in (
                    "path",
                    "sha256",
                    "artifact_type",
                    "betting_day",
                    "run_id",
                    "status",
                ):
                    if field not in b:
                        errors.append(f"S2.9 binding for {sid} missing field '{field}'")

                if b.get("status") != "PASS":
                    errors.append(f"S2.9 binding for {sid} status must be PASS")

                if b.get("betting_day") != betting_day or b.get("run_id") != run_id:
                    errors.append(f"S2.9 binding for {sid} day/run mismatch")

                b_path_str = b.get("path", "")
                b_sha = b.get("sha256", "")

                p = Path(b_path_str)
                if not p.is_absolute():
                    resolved_p = (run_root / p).resolve()
                else:
                    resolved_p = p.resolve()

                try:
                    rel = resolved_p.relative_to(resolved_run_root)
                    curr = resolved_run_root
                    for part in rel.parts:
                        curr = curr / part
                        if curr.is_symlink():
                            errors.append(
                                f"Symlink detected in run-confined path: {curr}"
                            )
                except ValueError:
                    errors.append(
                        f"Path escapes run root: {resolved_p} vs {resolved_run_root}"
                    )

                if not resolved_p.exists():
                    errors.append(f"Predecessor path {resolved_p} does not exist")
                else:
                    from bet.pipeline.canonical_continuity import file_sha256

                    actual_sha = file_sha256(resolved_p)
                    if b_sha != actual_sha:
                        errors.append(
                            f"S2.9 binding for {sid} SHA-256 mismatch with actual file"
                        )

                    wo_ref = wo_refs_by_step.get(sid)
                    if wo_ref:
                        wo_path = (
                            wo_ref.get("path")
                            if isinstance(wo_ref, dict)
                            else getattr(wo_ref, "path", None)
                        )
                        wo_sha = (
                            wo_ref.get("sha256")
                            if isinstance(wo_ref, dict)
                            else getattr(wo_ref, "sha256", None)
                        )
                        if wo_path and Path(wo_path).resolve() != resolved_p:
                            errors.append(
                                f"S2.9 binding for {sid} path mismatch with work order"
                            )
                        if wo_sha and wo_sha != b_sha:
                            errors.append(
                                f"S2.9 binding for {sid} SHA-256 mismatch with work order"
                            )
                    else:
                        errors.append(f"Predecessor {sid} is missing from work order")

                    try:
                        with resolved_p.open("r", encoding="utf-8") as f:
                            pred_data = json.load(f)
                        if pred_data.get("step_id") != sid:
                            errors.append(
                                f"Semantic validation failed for {sid}: step_id mismatch"
                            )
                        if pred_data.get("status") != "PASS":
                            errors.append(
                                f"Semantic validation failed for {sid}: status must be PASS"
                            )
                        if (
                            pred_data.get("betting_day") != betting_day
                            or pred_data.get("run_id") != run_id
                        ):
                            errors.append(
                                f"Semantic validation failed for {sid}: day/run mismatch"
                            )
                    except Exception as e:
                        errors.append(f"Failed semantic validation for {sid}: {e}")

    elif step_id == "S5":
        if is_pass:
            if not _non_empty_list(evidence_refs):
                errors.append("S5 PASS artifact must contain non-empty 'evidence_refs'")
            category_aliases = {
                "injuries/lineups": ("injuries", "lineup"),
                "motivation/tournament context": ("motivation", "tournament"),
                "travel/fatigue": ("travel", "fatigue"),
                "morale/recent form": ("morale", "recent_form", "recent form"),
                "upset/volatility risk": ("upset", "volatility"),
            }
            payload_keys = [str(key).lower() for key in payload.keys()]
            for label, aliases in category_aliases.items():
                if not any(
                    any(alias in key for alias in aliases) for key in payload_keys
                ):
                    errors.append(
                        f"S5 PASS payload must contain context check for category '{label}'"
                    )

            # Validate S5_CONTEXT_RISK_CANDIDATE_SET_V2 fields if present
            if "candidates" in payload:
                for field in (
                    "source_s4_path",
                    "source_s4_sha256",
                    "source_git_sha",
                    "manifest_sha",
                    "work_order_id",
                    "agent_id",
                    "policy_version",
                    "input_candidate_count",
                    "rejected_candidates",
                    "accounting",
                ):
                    if field not in payload:
                        errors.append(f"S5 PASS payload must contain '{field}'")

                candidates = payload.get("candidates", [])
                rejected = payload.get("rejected_candidates", [])
                input_count = payload.get("input_candidate_count", 0)
                if isinstance(candidates, list) and isinstance(rejected, list):
                    if len(candidates) + len(rejected) != input_count:
                        errors.append(
                            f"S5 candidate accounting mismatch: len(candidates)={len(candidates)} + len(rejected)={len(rejected)} != input_candidate_count={input_count}"
                        )

                accounting = payload.get("accounting") or {}
                if not isinstance(accounting, dict):
                    errors.append("S5 PASS payload 'accounting' must be a dict")
                else:
                    for k in (
                        "unaccounted_candidate_ids",
                        "duplicate_candidate_ids",
                        "overlapping_terminal_categories",
                    ):
                        if k not in accounting:
                            errors.append(
                                f"S5 PASS payload accounting must contain '{k}'"
                            )
                        elif accounting[k] != []:
                            errors.append(
                                f"S5 PASS payload accounting.{k} must be empty"
                            )

    return errors


def agent_artifact_template_for_step(
    step_id: str, betting_day: str, run_id: str
) -> dict[str, Any]:
    """Construct an empty artifact template matching step contract expectations."""
    from bet.pipeline.agent_work_orders import POLICIES

    if step_id not in POLICIES:
        raise ValueError(f"No policy defined for step_id: {step_id}")

    template = {
        "schema_version": 1,
        "artifact_type": "AGENT_ARTIFACT",
        "step_id": step_id,
        "status": "BLOCK",
        "betting_day": betting_day,
        "run_id": run_id,
        "sport": None,
        "fixture_id": None,
        "fixture_key": None,
        "point_in_time_as_of": None,
        "source_bound": False,
        "no_pick_edge_stake_coupon_emitted": True,
        "production_selectable": False,
        "betting_decisions_enabled": False,
        "sources": [],
        "unknowns": ["TODO_FILL_BY_AGENT"],
        "blocked_reasons": ["TEMPLATE_NOT_FILLED"],
        "evidence_refs": [],
        "payload": {
            "template_status": "TODO_FILL_BY_AGENT",
            "approval_state": "NOT_FINAL_TEMPLATE",
        },
    }

    if step_id == "S2.3":
        template["payload"] = {
            "template_status": "TODO_FILL_BY_AGENT",
            "approval_state": "NOT_FINAL_TEMPLATE",
            "enrichment_gaps": ["TODO_FILL_BY_AGENT"],
            "missing_sources": ["TODO_FILL_BY_AGENT"],
            "unknowns_summary": ["TODO_FILL_BY_AGENT"],
            "gaps_status": "TODO_FILL_BY_AGENT",
        }
    elif step_id == "S2.5":
        template["payload"] = {
            "template_status": "TODO_FILL_BY_AGENT",
            "approval_state": "NOT_FINAL_TEMPLATE",
            "provider_observations": ["TODO_FILL_BY_AGENT"],
            "source_observations": ["TODO_FILL_BY_AGENT"],
            "provider_change_note": "DO_NOT_CHANGE_PROVIDER_SELECTION",
        }
    elif step_id == "S2.7":
        template["payload"] = {
            "template_status": "TODO_FILL_BY_AGENT",
            "approval_state": "NOT_FINAL_TEMPLATE",
            "disputed_facts": ["TODO_FILL_BY_AGENT"],
            "reconciliation": {
                "unknown_facts": ["TODO_FILL_BY_AGENT"],
                "decision_basis": "TODO_FILL_BY_AGENT",
            },
        }
    elif step_id == "S2.9":
        template["payload"] = {
            "template_status": "TODO_FILL_BY_AGENT",
            "approval_state": "NOT_FINAL_TEMPLATE",
            "readiness": "TODO_FILL_BY_AGENT",
            "readiness_basis": "TODO_FILL_BY_AGENT",
            "s3_may_proceed": False,
        }
    elif step_id == "S5":
        template["payload"] = {
            "template_status": "TODO_FILL_BY_AGENT",
            "approval_state": "NOT_FINAL_TEMPLATE",
            "policy_version": "S5_CONTEXT_RISK_V2",
            "work_order_id": f"WO-{run_id}-S5",
            "agent_id": "bet-risk-gatekeeper",
            "source_s4_path": "TODO_EXACT_S4_PATH_FROM_WORK_ORDER",
            "source_s4_sha256": "TODO_EXACT_S4_SHA256_FROM_WORK_ORDER",
            "source_git_sha": "TODO_CURRENT_GIT_SHA",
            "manifest_sha": "TODO_CURRENT_MANIFEST_SHA256",
            "input_candidate_count": 0,
            "candidates": [],
            "rejected_candidates": [],
            "accounting": {
                "unaccounted_candidate_ids": [],
                "duplicate_candidate_ids": [],
                "overlapping_terminal_categories": [],
            },
            "injuries_lineups": "TODO_FILL_BY_AGENT",
            "motivation_tournament_context": "TODO_FILL_BY_AGENT",
            "travel_fatigue": "TODO_FILL_BY_AGENT",
            "morale_recent_form": "TODO_FILL_BY_AGENT",
            "upset_volatility_risk": "TODO_FILL_BY_AGENT",
        }

    return template


def find_repo_root(start_path: Path | str) -> Path:
    """Helper to locate repo root containing config/pipeline_manifest.json or .git."""
    curr = Path(start_path).resolve()
    for _ in range(6):
        # A bare `.git` directory is not sufficient: sandboxed runners may
        # expose placeholder mount points that are not repositories.  The
        # canonical manifest is the stable project-root marker we need here.
        if (curr / "config" / "pipeline_manifest.json").is_file():
            return curr
        curr = curr.parent
    return Path(__file__).resolve().parents[3]


def validate_s5_artifact_v2(
    s5_data: dict[str, Any],
    run_root: Path,
    betting_day: str,
    run_id: str,
    manifest: Any = None,
) -> None:
    """Strong validation of S5_CONTEXT_RISK_CANDIDATE_SET_V2.

    Verifies that the S5 artifact is sound, complete, and exactly binds to S4 and other run state.
    """
    from pathlib import Path

    from bet.pipeline.canonical_continuity import (
        bind_candidate_identity,
        selection_identity_fields,
        validate_exact_partition,
    )
    from bet.pipeline.integration_artifacts import resolve_manifest_step_output
    from bet.pipeline.run_evidence import manifest_hash, repo_head_sha, sha256_file

    if not isinstance(s5_data, dict):
        raise ValueError(
            "S5_CANDIDATE_ACCOUNTING_MISMATCH: s5_data is not a dictionary"
        )

    payload = s5_data.get("payload", {})
    if not isinstance(payload, dict):
        raise ValueError(
            "S5_CANDIDATE_ACCOUNTING_MISMATCH: s5_data payload is not a dictionary"
        )

    if (
        s5_data.get("schema_version") != 1
        or s5_data.get("artifact_type") != "AGENT_ARTIFACT"
        or s5_data.get("step_id") != "S5"
        or s5_data.get("status") != "PASS"
        or s5_data.get("source_bound") is not True
        or s5_data.get("no_pick_edge_stake_coupon_emitted") is not True
        or s5_data.get("production_selectable") is not False
        or s5_data.get("betting_decisions_enabled") is not False
    ):
        raise ValueError("S5_TOP_LEVEL_CONTRACT_INVALID")

    # Check current run/day
    if s5_data.get("betting_day") != betting_day:
        raise ValueError(
            f"S5_WORK_ORDER_MISMATCH: betting_day mismatch: expected {betting_day}, got {s5_data.get('betting_day')}"
        )
    if s5_data.get("run_id") != run_id:
        raise ValueError(
            f"S5_WORK_ORDER_MISMATCH: run_id mismatch: expected {run_id}, got {s5_data.get('run_id')}"
        )

    # Check work_order_id
    expected_work_order = f"WO-{run_id}-S5"
    if payload.get("work_order_id") != expected_work_order:
        raise ValueError(
            f"S5_WORK_ORDER_MISMATCH: work_order_id mismatch: expected {expected_work_order}, got {payload.get('work_order_id')}"
        )

    # Check agent_id
    if payload.get("agent_id") != "bet-risk-gatekeeper":
        raise ValueError(
            f"S5_AGENT_MISMATCH: agent_id mismatch: expected 'bet-risk-gatekeeper', got {payload.get('agent_id')}"
        )

    repo_root = find_repo_root(run_root)

    # Git SHA check
    expected_git_sha = repo_head_sha(repo_root)
    if (payload.get("source_git_sha") or payload.get("git_sha")) != expected_git_sha:
        raise ValueError(
            f"S5_GIT_SHA_MISMATCH: Git SHA mismatch: expected {expected_git_sha}, got {payload.get('source_git_sha')}"
        )

    # Manifest SHA check
    expected_manifest_sha = manifest_hash(repo_root)
    if (
        payload.get("manifest_sha") or payload.get("manifest_hash")
    ) != expected_manifest_sha:
        raise ValueError(
            f"S5_MANIFEST_SHA_MISMATCH: Manifest SHA mismatch: expected {expected_manifest_sha}, got {payload.get('manifest_sha')}"
        )

    # S4 Predecessor Resolution
    try:
        s4_path, s4_data = resolve_manifest_step_output(
            manifest=manifest,
            run_root=run_root,
            step_id="S4",
            betting_day=betting_day,
            run_id=run_id,
            expected_artifact_type="S4_VALUATION_CANDIDATE_SET_V2",
        )
    except Exception as exc:
        raise ValueError(
            f"S5_SOURCE_PATH_MISMATCH: Failed to resolve S4 predecessor: {exc}"
        )

    # S4 Path check
    source_s4_path = payload.get("source_s4_path")
    if not source_s4_path:
        raise ValueError("S5_SOURCE_PATH_MISMATCH: source_s4_path is missing")
    if Path(source_s4_path).resolve() != s4_path.resolve():
        raise ValueError(
            f"S5_SOURCE_PATH_MISMATCH: S4 path mismatch: expected {s4_path}, got {source_s4_path}"
        )

    # S4 SHA check
    source_s4_sha256 = payload.get("source_s4_sha256")
    actual_s4_sha = sha256_file(s4_path)
    if source_s4_sha256 != actual_s4_sha:
        raise ValueError(
            f"S5_SOURCE_HASH_MISMATCH: S4 hash mismatch: expected {actual_s4_sha}, got {source_s4_sha256}"
        )

    # Partition and candidates checks
    retained = payload.get("candidates", [])
    rejected = payload.get("rejected_candidates", [])
    input_candidate_count = payload.get("input_candidate_count")

    retained_ids = []
    for idx, c in enumerate(retained):
        cid = c.get("candidate_id")
        if not cid:
            raise ValueError(
                f"S5_CANDIDATE_ACCOUNTING_MISMATCH: Retained candidate at index {idx} has no candidate_id"
            )
        retained_ids.append(cid)
        bound = bind_candidate_identity(c)
        if bound.get("candidate_id") != cid or c.get("selection_id") != cid:
            raise ValueError(f"S5_CANONICAL_IDENTITY_MISMATCH: {cid}")

        # Verify mandatory analytical/pricing/context/risk/provenance fields
        if "home_team" not in c or "away_team" not in c:
            raise ValueError(
                f"S5_CANDIDATE_ACCOUNTING_MISMATCH: Retained candidate {cid} is missing analytical fields (home_team/away_team)"
            )
        if not (
            "market" in c
            or "best_market" in c
            or "market_type" in c
            or "market_name" in c
        ):
            raise ValueError(
                f"S5_CANDIDATE_ACCOUNTING_MISMATCH: Retained candidate {cid} is missing analytical market field"
            )

        # Pricing and analytical status resolution
        analytical_status = c.get("analytical_status")
        if not analytical_status:
            analytical_status = "ANALYTICAL_READY"
        if analytical_status == "ANALYTICAL_BLOCKED":
            raise ValueError(
                f"S5_CANDIDATE_ACCOUNTING_MISMATCH: Retained candidate {cid} has analytical_status 'ANALYTICAL_BLOCKED' but is retained for S6"
            )
        if analytical_status not in ("ANALYTICAL_READY", "REVIEW_ONLY_PARTIAL_DATA"):
            raise ValueError(
                f"S5_CANDIDATE_ACCOUNTING_MISMATCH: Retained candidate {cid} has invalid analytical_status: '{analytical_status}'"
            )

        pricing_status = c.get("pricing_status")
        if not pricing_status:
            if c.get("odds_decimal") or c.get("best_odds") or c.get("odds"):
                pricing_status = "PRICED"
            else:
                pricing_status = "PRICE_PENDING"

        if pricing_status not in (
            "PRICED",
            "PRICE_PENDING",
            "PRICING_DEGRADED",
            "PRICING_BLOCKED_INVALID_INPUT",
        ):
            raise ValueError(
                f"S5_CANDIDATE_ACCOUNTING_MISMATCH: Retained candidate {cid} has invalid pricing_status: '{pricing_status}'"
            )

        if pricing_status == "PRICED":
            odds_val = c.get("odds_decimal") or c.get("best_odds")
            if not odds_val:
                raise ValueError(
                    f"S5_CANDIDATE_ACCOUNTING_MISMATCH: Retained candidate {cid} with pricing_status 'PRICED' is missing valid odds"
                )
            try:
                if float(odds_val) <= 0:
                    raise ValueError()
            except (ValueError, TypeError):
                raise ValueError(
                    f"S5_CANDIDATE_ACCOUNTING_MISMATCH: Retained candidate {cid} with pricing_status 'PRICED' has invalid or non-positive odds: {odds_val}"
                )

            odds_source = (
                c.get("odds_source")
                or c.get("best_market", {}).get("bookmaker")
                or c.get("bookmaker")
            )
            odds_as_of = (
                c.get("odds_as_of")
                or c.get("best_market", {}).get("as_of")
                or c.get("probability_as_of")
            )
            if not odds_source:
                raise ValueError(
                    f"S5_CANDIDATE_ACCOUNTING_MISMATCH: Retained candidate {cid} with pricing_status 'PRICED' is missing pricing source"
                )
            if not odds_as_of:
                raise ValueError(
                    f"S5_CANDIDATE_ACCOUNTING_MISMATCH: Retained candidate {cid} with pricing_status 'PRICED' is missing as-of timestamp"
                )
        else:
            ev = c.get("ev")
            if ev is not None and ev != "unavailable":
                raise ValueError(
                    f"S5_CANDIDATE_ACCOUNTING_MISMATCH: Retained candidate {cid} with pricing_status '{pricing_status}' must have null/unavailable EV, got: {ev}"
                )

            kelly = c.get("kelly") or c.get("kelly_criterion")
            if kelly is not None and kelly != "unavailable":
                raise ValueError(
                    f"S5_CANDIDATE_ACCOUNTING_MISMATCH: Retained candidate {cid} with pricing_status '{pricing_status}' must have null/unavailable Kelly, got: {kelly}"
                )

            stake = c.get("stake") or c.get("stake_decimal")
            if stake is not None and stake != "unavailable":
                raise ValueError(
                    f"S5_CANDIDATE_ACCOUNTING_MISMATCH: Retained candidate {cid} with pricing_status '{pricing_status}' must have null/unavailable stake, got: {stake}"
                )

            bettable = c.get("bettable")
            if bettable is not None and bettable is not False:
                raise ValueError(
                    f"S5_CANDIDATE_ACCOUNTING_MISMATCH: Retained candidate {cid} with pricing_status '{pricing_status}' must have bettable=False, got: {bettable}"
                )

        if "sport" not in c or "competition" not in c:
            raise ValueError(
                f"S5_CANDIDATE_ACCOUNTING_MISMATCH: Retained candidate {cid} is missing context fields (sport/competition)"
            )
        if not (
            "safety_score" in c
            or "risk" in c
            or "safety_markets" in c
            or "risk_flags" in c
        ):
            raise ValueError(
                f"S5_CANDIDATE_ACCOUNTING_MISMATCH: Retained candidate {cid} is missing risk fields"
            )
        context_checks = c.get("context_checks")
        required_context = {
            "injuries_lineups",
            "motivation_tournament_context",
            "travel_fatigue",
            "morale_recent_form",
            "upset_volatility_risk",
        }
        if (
            not isinstance(context_checks, dict)
            or set(context_checks) & required_context != required_context
        ):
            raise ValueError(f"S5_CONTEXT_EVIDENCE_MISSING: {cid}")
        for name in required_context:
            check = context_checks[name]
            if (
                not isinstance(check, dict)
                or str(check.get("status") or "").upper()
                not in {"CLEAR", "RISK_ACCEPTABLE", "BLOCK", "UNKNOWN"}
                or not check.get("as_of_utc")
                or not check.get("source_refs")
            ):
                raise ValueError(f"S5_CONTEXT_EVIDENCE_INVALID: {cid}:{name}")
        if not isinstance(c.get("risk_flags"), list) or not isinstance(
            c.get("counter_evidence"), list
        ):
            raise ValueError(f"S5_RISK_EVIDENCE_INVALID: {cid}")

    rejected_ids = []
    for idx, c in enumerate(rejected):
        cid = c.get("candidate_id")
        if not cid:
            raise ValueError(
                f"S5_CANDIDATE_ACCOUNTING_MISMATCH: Rejected candidate at index {idx} has no candidate_id"
            )
        rejected_ids.append(cid)
        if c.get("selection_id") != cid:
            raise ValueError(f"S5_CANONICAL_IDENTITY_MISMATCH: {cid}")
        bind_candidate_identity(c)

        # stable rejection reasons
        reasons = (
            c.get("rejection_reasons")
            or c.get("reason_codes")
            or c.get("reasons")
            or c.get("reason")
        )
        if not reasons:
            raise ValueError(
                f"S5_REJECTION_REASON_MISSING: Rejected candidate {cid} has no rejection reasons"
            )
        if isinstance(reasons, list) and len(reasons) == 0:
            raise ValueError(
                f"S5_REJECTION_REASON_MISSING: Rejected candidate {cid} rejection reasons list is empty"
            )
        if isinstance(reasons, str) and not reasons.strip():
            raise ValueError(
                f"S5_REJECTION_REASON_MISSING: Rejected candidate {cid} rejection reasons string is empty"
            )

    # uniqueness checks
    if len(retained_ids) != len(set(retained_ids)):
        raise ValueError(
            "S5_CANDIDATE_DUPLICATE: Duplicate candidate IDs found in retained candidates"
        )
    if len(rejected_ids) != len(set(rejected_ids)):
        raise ValueError(
            "S5_CANDIDATE_DUPLICATE: Duplicate candidate IDs found in rejected candidates"
        )

    # overlap checks
    overlap = set(retained_ids) & set(rejected_ids)
    if overlap:
        raise ValueError(
            f"S5_TERMINAL_OVERLAP: Candidate IDs overlap between retained and rejected sets: {overlap}"
        )

    # S4 candidates partition check
    s4_candidates = (
        s4_data.get("candidates") or s4_data.get("payload", {}).get("candidates") or []
    )
    s4_ids = [c.get("candidate_id") for c in s4_candidates if c.get("candidate_id")]

    if set(retained_ids) | set(rejected_ids) != set(s4_ids):
        raise ValueError(
            f"S5_CANDIDATE_ACCOUNTING_MISMATCH: Partition of S4 candidates does not match: S5 union has {len(set(retained_ids) | set(rejected_ids))} candidates, but S4 has {len(set(s4_ids))}"
        )

    if input_candidate_count != len(s4_ids):
        raise ValueError(
            f"S5_CANDIDATE_ACCOUNTING_MISMATCH: S5 input_candidate_count {input_candidate_count} does not match S4 candidates count {len(s4_ids)}"
        )

    if len(retained_ids) + len(rejected_ids) != len(s4_ids):
        raise ValueError(
            f"S5_CANDIDATE_ACCOUNTING_MISMATCH: S5 candidates count sum {len(retained_ids) + len(rejected_ids)} does not match S4 candidates count {len(s4_ids)}"
        )

    validate_exact_partition(
        s4_candidates,
        {"candidates": retained, "rejected_candidates": rejected},
    )
    source_by_id = {candidate["selection_id"]: candidate for candidate in s4_candidates}
    for candidate in retained + rejected:
        candidate_id = candidate["selection_id"]
        source = source_by_id[candidate_id]
        if selection_identity_fields(
            candidate, candidate["canonical_event_id"]
        ) != selection_identity_fields(source, source["canonical_event_id"]):
            raise ValueError(f"S5_SELECTION_IDENTITY_MUTATED: {candidate_id}")
