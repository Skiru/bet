"""Contracts and validators for agent artifacts generated from work orders."""
from __future__ import annotations

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
        "required_statuses": ["PASS", "BLOCK", "COMMAND_REQUEST"],
        "schema_requirements": policy.schema_requirements,
        "forbidden_outputs": policy.forbidden_outputs,
        "hard_rules": policy.hard_rules,
    }


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

    def _refs_cover_required_steps(evidence_refs: list[str], required_steps: tuple[str, ...]) -> bool:
        return all(any(required_step in ref for ref in evidence_refs) for required_step in required_steps)

    def _contains_provider_promotion(node: Any) -> bool:
        forbidden_tokens = (
            "promote",
            "promotion",
            "preferred_provider",
            "promoted_provider",
            "selected_provider",
            "provider_selection",
            "selection_change",
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
        if isinstance(node, list):
            return any(_contains_provider_promotion(item) for item in node)
        if isinstance(node, str):
            lowered = node.strip().lower()
            return any(token in lowered for token in forbidden_tokens)
        return False

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
    allowed_statuses = req_output.get("required_statuses", ["PASS", "BLOCK", "COMMAND_REQUEST"])
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
            errors.append("COMMAND_REQUEST artifacts must contain a non-empty command_request")
        else:
            import shlex
            import os
            argv = []
            if isinstance(cmd_req, dict):
                argv = cmd_req.get("argv")
                if not isinstance(argv, list) or not argv:
                    errors.append("Structured command_request must contain a non-empty 'argv' list")
                    argv = []
            elif isinstance(cmd_req, str):
                meta = [";", "&", "|", "<", ">", "$", "(", ")", "*", "?", "[", "]", "\\", "!", "{", "}"]
                if any(m in cmd_req for m in meta):
                    errors.append("COMMAND_REQUEST command_request string contains disallowed shell metacharacters")
                try:
                    argv = shlex.split(cmd_req)
                except Exception as e:
                    errors.append(f"Failed to parse command_request string: {e}")
                    argv = []
            else:
                errors.append("command_request must be a string or a structured object")
                
            if argv:
                meta = [";", "&", "|", "<", ">", "$", "(", ")", "*", "?", "[", "]", "\\", "!", "{", "}"]
                for arg in argv:
                    if any(m in str(arg) for m in meta):
                        errors.append(f"COMMAND_REQUEST argument '{arg}' contains disallowed shell metacharacters")
                executable = argv[0]
                allowed_execs = {"python", "python3", "pytest", ".venv/bin/python3", ".venv/bin/python", ".venv/bin/pytest", "sleep", "/bin/sleep"}
                is_safe_exec = False
                base_exec = os.path.basename(executable)
                if base_exec in allowed_execs or executable in allowed_execs:
                    is_safe_exec = True
                elif executable.endswith(".py") and ("scripts/" in executable or "tools/" in executable):
                    is_safe_exec = True
                if not is_safe_exec:
                    errors.append(f"COMMAND_REQUEST executable '{executable}' is not in the allowlist of safe executables")

        forbidden_signals = ["pick", "picks", "selection", "selections", "bet", "betting_decision", "edge", "ev", "expected_value", "stake", "staking", "coupon", "accumulator", "parlay"]
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
        if artifact_data.get("production_selectable") != schema_reqs["production_selectable"]:
            errors.append(f"production_selectable must be {schema_reqs['production_selectable']}")
            
    if is_pass and "betting_decisions_enabled" in schema_reqs:
        if artifact_data.get("betting_decisions_enabled") != schema_reqs["betting_decisions_enabled"]:
            errors.append(f"betting_decisions_enabled must be {schema_reqs['betting_decisions_enabled']}")
            
    if is_pass and schema_reqs.get("sources_required"):
        if not _non_empty_list(sources):
            errors.append("sources must be a non-empty list")

    # 6. Forbidden fields in the actual artifact payload
    forbidden_keys = work_order_data.get("forbidden_outputs", [])
    if forbidden_keys:
        signals = find_forbidden_decision_signals(payload)
        for sig in signals:
            errors.append(f"Forbidden decision signal found in payload: {sig}")
            
    # 7. Step-specific contract checks
    if step_id == "S2.3":
        if "unknowns" not in artifact_data:
            errors.append("S2.3 artifact must contain an 'unknowns' list")
        if is_pass:
            if not _payload_contains_any(payload, ("gaps", "enrichment_gaps")):
                errors.append("S2.3 PASS payload must contain 'gaps' or 'enrichment_gaps'")
            if not _payload_contains_any(
                payload,
                ("gaps_bounded", "bounded_gaps", "gaps_blocking", "blocking_gaps", "gaps_status"),
            ):
                errors.append("S2.3 PASS must explicitly state whether gaps are bounded or blocking")
             
    elif step_id == "S2.5":
        if is_pass:
            if not _payload_contains_any(payload, ("providers", "observations", "provider_observations")):
                errors.append("S2.5 PASS payload must contain provider/source observations")
            if _contains_provider_promotion(payload):
                errors.append("S2.5 PASS must not contain provider promotion or selection changes")
             
    elif step_id == "S2.7":
        if is_pass:
            if not _payload_contains_any(payload, ("disputed_facts", "reconciliation")):
                errors.append("S2.7 PASS payload must contain 'disputed_facts' or 'reconciliation'")
            if not _non_empty_list(evidence_refs):
                errors.append("S2.7 PASS artifact must contain non-empty 'evidence_refs'")
            disputed_facts = payload.get("disputed_facts")
            reconciliation = payload.get("reconciliation")
            has_explicit_unknowns = _payload_contains_any(payload, ("unknown_facts", "unknowns", "unresolved_facts"))
            reconciliation_marks_unknowns = isinstance(reconciliation, dict) and any(
                key in reconciliation for key in ("unknown_facts", "unknowns", "disputed_facts", "unresolved_facts")
            )
            if not _non_empty_list(disputed_facts) and not has_explicit_unknowns and not reconciliation_marks_unknowns:
                errors.append("S2.7 PASS must explicitly mark disputed or unknown facts")
             
    elif step_id == "S2.9":
        if is_pass:
            if not payload:
                errors.append("S2.9 PASS payload must not be empty")
            readiness_verdict = payload.get("readiness")
            if not _non_empty_string(readiness_verdict):
                errors.append("S2.9 PASS payload must contain a readiness verdict")
            if not _non_empty_list(evidence_refs):
                errors.append("S2.9 PASS artifact must contain non-empty 'evidence_refs'")
            elif not _refs_cover_required_steps(evidence_refs, ("S2.3", "S2.5", "S2.7")):
                errors.append("S2.9 PASS evidence_refs must include S2.3, S2.5, and S2.7 artifact refs")
            if set(payload.keys()) == {"s3_may_proceed"}:
                errors.append("S2.9 PASS must not rely on s3_may_proceed alone")
            if payload.get("s3_may_proceed") is True:
                if str(readiness_verdict).strip().upper() != "PASS":
                    errors.append("S2.9 PASS may set s3_may_proceed=true only when readiness is explicitly PASS")
                if not _refs_cover_required_steps(evidence_refs, ("S2.3", "S2.5", "S2.7")):
                    errors.append("S2.9 PASS may set s3_may_proceed=true only with S2.3/S2.5/S2.7 evidence refs")
             
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
                if not any(any(alias in key for alias in aliases) for key in payload_keys):
                    errors.append(f"S5 PASS payload must contain context check for category '{label}'")

            # Validate S5_CONTEXT_RISK_CANDIDATE_SET_V2 fields if present
            if "candidates" in payload:
                for field in ("source_s4_path", "source_s4_sha256", "source_git_sha", "manifest_sha", "work_order_id", "agent_id", "policy_version", "input_candidate_count", "rejected_candidates", "accounting"):
                    if field not in payload:
                        errors.append(f"S5 PASS payload must contain '{field}'")
                
                candidates = payload.get("candidates", [])
                rejected = payload.get("rejected_candidates", [])
                input_count = payload.get("input_candidate_count", 0)
                if isinstance(candidates, list) and isinstance(rejected, list):
                    if len(candidates) + len(rejected) != input_count:
                        errors.append(f"S5 candidate accounting mismatch: len(candidates)={len(candidates)} + len(rejected)={len(rejected)} != input_candidate_count={input_count}")
                
                accounting = payload.get("accounting") or {}
                if not isinstance(accounting, dict):
                    errors.append("S5 PASS payload 'accounting' must be a dict")
                else:
                    for k in ("unaccounted_candidate_ids", "duplicate_candidate_ids", "overlapping_terminal_categories"):
                        if k not in accounting:
                            errors.append(f"S5 PASS payload accounting must contain '{k}'")
                        elif accounting[k] != []:
                            errors.append(f"S5 PASS payload accounting.{k} must be empty")

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
            "injuries_lineups": "TODO_FILL_BY_AGENT",
            "motivation_tournament_context": "TODO_FILL_BY_AGENT",
            "travel_fatigue": "TODO_FILL_BY_AGENT",
            "morale_recent_form": "TODO_FILL_BY_AGENT",
            "upset_volatility_risk": "TODO_FILL_BY_AGENT",
        }
        
    return template


def find_repo_root(start_path: Path | str) -> Path:
    """Helper to locate repo root containing config/pipeline_manifest.json or .git."""
    from pathlib import Path
    curr = Path(start_path).resolve()
    for _ in range(6):
        if (curr / "config" / "pipeline_manifest.json").exists() or (curr / ".git").exists():
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
    from bet.pipeline.run_evidence import sha256_file, repo_head_sha, manifest_hash
    from bet.pipeline.integration_artifacts import resolve_manifest_step_output

    if not isinstance(s5_data, dict):
        raise ValueError("S5_CANDIDATE_ACCOUNTING_MISMATCH: s5_data is not a dictionary")
    
    payload = s5_data.get("payload", {})
    if not isinstance(payload, dict):
        raise ValueError("S5_CANDIDATE_ACCOUNTING_MISMATCH: s5_data payload is not a dictionary")

    # Check current run/day
    if s5_data.get("betting_day") != betting_day:
        raise ValueError(f"S5_WORK_ORDER_MISMATCH: betting_day mismatch: expected {betting_day}, got {s5_data.get('betting_day')}")
    if s5_data.get("run_id") != run_id:
        raise ValueError(f"S5_WORK_ORDER_MISMATCH: run_id mismatch: expected {run_id}, got {s5_data.get('run_id')}")

    # Check work_order_id
    expected_work_order = f"WO-{run_id}-S5"
    if payload.get("work_order_id") != expected_work_order:
        raise ValueError(f"S5_WORK_ORDER_MISMATCH: work_order_id mismatch: expected {expected_work_order}, got {payload.get('work_order_id')}")
        
    # Check agent_id
    if payload.get("agent_id") != "bet-risk-gatekeeper":
        raise ValueError(f"S5_AGENT_MISMATCH: agent_id mismatch: expected 'bet-risk-gatekeeper', got {payload.get('agent_id')}")

    repo_root = find_repo_root(run_root)
    
    # Git SHA check
    expected_git_sha = repo_head_sha(repo_root)
    if (payload.get("source_git_sha") or payload.get("git_sha")) != expected_git_sha:
        raise ValueError(f"S5_GIT_SHA_MISMATCH: Git SHA mismatch: expected {expected_git_sha}, got {payload.get('source_git_sha')}")
        
    # Manifest SHA check
    expected_manifest_sha = manifest_hash(repo_root)
    if (payload.get("manifest_sha") or payload.get("manifest_hash")) != expected_manifest_sha:
        raise ValueError(f"S5_MANIFEST_SHA_MISMATCH: Manifest SHA mismatch: expected {expected_manifest_sha}, got {payload.get('manifest_sha')}")

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
        raise ValueError(f"S5_SOURCE_PATH_MISMATCH: Failed to resolve S4 predecessor: {exc}")

    # S4 Path check
    source_s4_path = payload.get("source_s4_path")
    if not source_s4_path:
        raise ValueError("S5_SOURCE_PATH_MISMATCH: source_s4_path is missing")
    if Path(source_s4_path).resolve() != s4_path.resolve():
        raise ValueError(f"S5_SOURCE_PATH_MISMATCH: S4 path mismatch: expected {s4_path}, got {source_s4_path}")
        
    # S4 SHA check
    source_s4_sha256 = payload.get("source_s4_sha256")
    actual_s4_sha = sha256_file(s4_path)
    if source_s4_sha256 != actual_s4_sha:
        raise ValueError(f"S5_SOURCE_HASH_MISMATCH: S4 hash mismatch: expected {actual_s4_sha}, got {source_s4_sha256}")

    # Partition and candidates checks
    retained = payload.get("candidates", [])
    rejected = payload.get("rejected_candidates", [])
    input_candidate_count = payload.get("input_candidate_count")

    retained_ids = []
    for idx, c in enumerate(retained):
        cid = c.get("candidate_id")
        if not cid:
            raise ValueError(f"S5_CANDIDATE_ACCOUNTING_MISMATCH: Retained candidate at index {idx} has no candidate_id")
        retained_ids.append(cid)
        
        # Verify mandatory analytical/pricing/context/risk/provenance fields
        if "home_team" not in c or "away_team" not in c:
            raise ValueError(f"S5_CANDIDATE_ACCOUNTING_MISMATCH: Retained candidate {cid} is missing analytical fields (home_team/away_team)")
        if not ("market" in c or "best_market" in c or "market_type" in c or "market_name" in c):
            raise ValueError(f"S5_CANDIDATE_ACCOUNTING_MISMATCH: Retained candidate {cid} is missing analytical market field")
        if not ("odds" in c or "best_odds" in c or "odds_decimal" in c or "odds_markets" in c):
            raise ValueError(f"S5_CANDIDATE_ACCOUNTING_MISMATCH: Retained candidate {cid} is missing pricing fields")
        if "sport" not in c or "competition" not in c:
            raise ValueError(f"S5_CANDIDATE_ACCOUNTING_MISMATCH: Retained candidate {cid} is missing context fields (sport/competition)")
        if not ("safety_score" in c or "risk" in c or "safety_markets" in c or "risk_flags" in c):
            raise ValueError(f"S5_CANDIDATE_ACCOUNTING_MISMATCH: Retained candidate {cid} is missing risk fields")

    rejected_ids = []
    for idx, c in enumerate(rejected):
        cid = c.get("candidate_id")
        if not cid:
            raise ValueError(f"S5_CANDIDATE_ACCOUNTING_MISMATCH: Rejected candidate at index {idx} has no candidate_id")
        rejected_ids.append(cid)
        
        # stable rejection reasons
        reasons = c.get("rejection_reasons") or c.get("reason_codes") or c.get("reasons") or c.get("reason")
        if not reasons:
            raise ValueError(f"S5_REJECTION_REASON_MISSING: Rejected candidate {cid} has no rejection reasons")
        if isinstance(reasons, list) and len(reasons) == 0:
            raise ValueError(f"S5_REJECTION_REASON_MISSING: Rejected candidate {cid} rejection reasons list is empty")
        if isinstance(reasons, str) and not reasons.strip():
            raise ValueError(f"S5_REJECTION_REASON_MISSING: Rejected candidate {cid} rejection reasons string is empty")

    # uniqueness checks
    if len(retained_ids) != len(set(retained_ids)):
        raise ValueError("S5_CANDIDATE_DUPLICATE: Duplicate candidate IDs found in retained candidates")
    if len(rejected_ids) != len(set(rejected_ids)):
        raise ValueError("S5_CANDIDATE_DUPLICATE: Duplicate candidate IDs found in rejected candidates")
        
    # overlap checks
    overlap = set(retained_ids) & set(rejected_ids)
    if overlap:
        raise ValueError(f"S5_TERMINAL_OVERLAP: Candidate IDs overlap between retained and rejected sets: {overlap}")

    # S4 candidates partition check
    s4_candidates = s4_data.get("candidates") or s4_data.get("payload", {}).get("candidates") or []
    s4_ids = [c.get("candidate_id") for c in s4_candidates if c.get("candidate_id")]
    
    if set(retained_ids) | set(rejected_ids) != set(s4_ids):
        raise ValueError(f"S5_CANDIDATE_ACCOUNTING_MISMATCH: Partition of S4 candidates does not match: S5 union has {len(set(retained_ids) | set(rejected_ids))} candidates, but S4 has {len(set(s4_ids))}")
        
    if input_candidate_count != len(s4_ids):
        raise ValueError(f"S5_CANDIDATE_ACCOUNTING_MISMATCH: S5 input_candidate_count {input_candidate_count} does not match S4 candidates count {len(s4_ids)}")

    if len(retained_ids) + len(rejected_ids) != len(s4_ids):
        raise ValueError(f"S5_CANDIDATE_ACCOUNTING_MISMATCH: S5 candidates count sum {len(retained_ids) + len(rejected_ids)} does not match S4 candidates count {len(s4_ids)}")

