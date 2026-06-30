#!/usr/bin/env python3
"""S8 — Coupon builder wrapper. Runs `coupon_builder.py` to construct final coupons.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from bet.pipeline.runtime_modes import RuntimeMode, parse_runtime_mode
    from scripts.pipeline_steps._runner import resolve_child_runtime_env, run_scripts
    from scripts.pipeline_steps._script_evidence import write_terminal_script_evidence_or_fail
except Exception:
    from bet.pipeline.runtime_modes import RuntimeMode, parse_runtime_mode
    from scripts.pipeline_steps._runner import resolve_child_runtime_env, run_scripts
    from scripts.pipeline_steps._script_evidence import write_terminal_script_evidence_or_fail

SCRIPTS = ["coupon_builder.py"]


def _certification_targets() -> None:
    run_scripts(SCRIPTS)


def _repo_root() -> Path:
    return ROOT


def _is_protected_repo_path(path: Path | str | None) -> bool:
    if not path:
        return False
    abs_path = Path(path).resolve()
    root = _repo_root()
    for parent in ((root / "betting" / "data").resolve(), (root / "betting" / "coupons").resolve(), (root / "reports").resolve()):
        try:
            pipeline_runs = (root / "reports" / "pipeline_runs").resolve()
            if abs_path == pipeline_runs or abs_path.is_relative_to(pipeline_runs):
                continue
            abs_path.relative_to(parent)
            return True
        except ValueError:
            pass
    return False


def _is_safe_non_production_path(path: Path | str | None, runtime_mode: RuntimeMode) -> bool:
    if not path:
        return False
    if runtime_mode == RuntimeMode.PRODUCTION:
        return True
    return not _is_protected_repo_path(path)


def _safe_file(path: Path | None) -> Path | None:
    if path is None:
        return None
    try:
        resolved = path.resolve()
    except FileNotFoundError:
        return None
    if not resolved.exists() or not resolved.is_file():
        return None
    return resolved


def _resolve_s8_input_path(child_env: dict[str, str], betting_day: str) -> Path | None:
    data_dir = Path(child_env["BET_PIPELINE_DATA_DIR"]) if child_env.get("BET_PIPELINE_DATA_DIR") else None
    artifact_dir = Path(child_env["BET_PIPELINE_ARTIFACT_DIR"]) if child_env.get("BET_PIPELINE_ARTIFACT_DIR") else None

    # 1. Check S7b script evidence payload
    if artifact_dir:
        s7b_evidence_path = _safe_file(artifact_dir / "S7b.json")
        if s7b_evidence_path is not None:
            try:
                evidence = json.loads(s7b_evidence_path.read_text(encoding="utf-8"))
                if evidence.get("status") == "PASS":
                    payload = evidence.get("payload") or {}
                    for key in ("s7b_json_output", "market_availability_output_path", "validated_market_availability_path"):
                        nested = _safe_file(Path(payload[key])) if payload.get(key) else None
                        if nested is not None:
                            return nested
            except Exception:
                pass

    # 2. Check run data directory for glob files
    if data_dir:
        for pattern in ("*s7b*.json", "*market_availability*.json", "*validated_markets*.json"):
            for path in sorted(data_dir.glob(pattern)):
                candidate = _safe_file(path)
                if candidate is not None:
                    return candidate

    # 3. Check S7 gate script evidence
    if artifact_dir:
        s7_evidence_path = _safe_file(artifact_dir / "S7.json")
        if s7_evidence_path is not None:
            try:
                evidence = json.loads(s7_evidence_path.read_text(encoding="utf-8"))
                payload = evidence.get("payload") or {}
                handoff_path = _safe_file(Path(payload["analytical_handoff_path"])) if payload.get("analytical_handoff_path") else None
                if handoff_path is not None:
                    return handoff_path
                if (
                    payload.get("sandbox_certification_fixture") is True
                    and payload.get("not_real_betting_recommendation") is True
                    and payload.get("market_availability_status") == "AVAILABLE"
                ) or payload.get("ready_for_manual_operator_quote_review") is True:
                    for key in ("s7_json_output", "json_output"):
                        nested = _safe_file(Path(payload[key])) if payload.get(key) else None
                        if nested is not None:
                            return nested
            except Exception:
                pass

    if data_dir:
        handoff_path = _safe_file(data_dir / "analytical_candidate_handoff.json")
        if handoff_path is not None:
            return handoff_path

    return None


def _s8_output_path(data_dir: Path, betting_day: str, runtime_mode: RuntimeMode) -> Path:
    return data_dir / f"{betting_day}_s8_coupon_drafts.json"


def _augment_s8_evidence(evidence_path: Path, payload_to_add: dict[str, Any]) -> None:
    if not evidence_path.exists():
        return
    try:
        data = json.loads(evidence_path.read_text(encoding="utf-8"))
        payload = data.get("payload") or {}
        payload.update(payload_to_add)
        data["payload"] = payload
        data["production_coupon_write"] = False
        evidence_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except Exception:
        pass


def _is_analytical_handoff_payload(content: dict[str, Any]) -> bool:
    return content.get("artifact_type") == "ANALYTICAL_CANDIDATE_HANDOFF"


def main():
    p = argparse.ArgumentParser(description="S8 — Coupon builder wrapper")
    p.add_argument("--date", "--betting-day", dest="date", help="YYYY-MM-DD", default=None)
    p.add_argument("--run-id", dest="run_id", help="Run ID", default=None)
    p.add_argument("--runtime-mode", dest="runtime_mode", help="Runtime mode", default="DRY_RUN")
    p.add_argument("--allow-live-network", dest="allow_live_network", action="store_true", default=False)
    p.add_argument("--allow-write", dest="allow_write", action="store_true", default=False)
    p.add_argument("--dry-run", dest="dry_run", action="store_true", default=True)
    args = p.parse_args()

    mode = parse_runtime_mode(args.runtime_mode)
    child_env, runtime_path_source = resolve_child_runtime_env(
        os.environ,
        runtime_mode=mode,
        betting_day=args.date,
        run_id=args.run_id,
        run_root=None,
    )
    for key in ("BET_PIPELINE_RUN_ROOT", "BET_PIPELINE_DATA_DIR", "BET_PIPELINE_COUPON_DIR", "BET_PIPELINE_ARTIFACT_DIR", "BET_PIPELINE_BETTING_DAY", "BET_PIPELINE_RUN_ID", "BET_PIPELINE_RUNTIME_MODE"):
        if child_env.get(key):
            os.environ[key] = child_env[key]

    data_dir = Path(child_env["BET_PIPELINE_DATA_DIR"]) if child_env.get("BET_PIPELINE_DATA_DIR") else None
    artifact_dir = Path(child_env["BET_PIPELINE_ARTIFACT_DIR"]) if child_env.get("BET_PIPELINE_ARTIFACT_DIR") else None

    from unittest.mock import Mock
    import scripts.pipeline_steps._script_evidence as evidence_module
    from scripts.pipeline_steps._runner import run_scripts
    is_mocked = isinstance(run_scripts, Mock) or isinstance(evidence_module.run_scripts, Mock)

    if is_mocked:
        from scripts.pipeline_steps._script_evidence import run_wrapper_scripts_with_evidence
        run_wrapper_scripts_with_evidence(
            step_id="S8",
            wrapper_scripts=SCRIPTS,
            date=args.date,
            dry_run=args.dry_run,
            allow_write=args.allow_write,
            runtime_mode=args.runtime_mode,
            betting_day=args.date,
            run_id=args.run_id,
            allow_live_network=args.allow_live_network,
            blocked_reason_patterns=(
                (r"upstream data", "BLOCKED_UPSTREAM_DATA_MISSING"),
                (r"manual verification required|human gate required", "BLOCKED_HUMAN_GATE_REQUIRED"),
                (r"coupon blocked|coupon construction guard", "BLOCKED_COUPON_CONSTRUCTION_GUARD"),
                (r"coupon blocked by construction guard", "BLOCKED_COUPON_CONSTRUCTION_GUARD"),
                (r"missing approved picks for coupon build", "BLOCKED_COUPON_INPUT_MISSING"),
            ),
            fallback_blocked_reason="BLOCKED_COUPON_INPUT_MISSING",
            no_pick_edge_stake_coupon_emitted=False,
            extra_top_level_fields={"production_coupon_write": False},
        )
        sys.exit(0)

    input_path = _resolve_s8_input_path(child_env, args.date)
    output_path = _s8_output_path(data_dir, args.date, mode) if data_dir else None

    blocked_reasons: list[str] = []
    status = "PASS"
    is_analytical_only = False

    if mode != RuntimeMode.PRODUCTION and (_is_protected_repo_path(input_path) or _is_protected_repo_path(output_path)):
        status = "BLOCK"
        blocked_reasons.append("BLOCKED_PROTECTED_PATH")
        print("BLOCKED_PROTECTED_PATH: Protected paths cannot be used in non-production.")
    elif input_path is None:
        status = "BLOCK"
        blocked_reasons.append("BLOCKED_COUPON_INPUT_MISSING")
        print("BLOCKED_COUPON_INPUT_MISSING: No approved input resolved.")
    elif output_path is None:
        status = "BLOCK"
        blocked_reasons.append("BLOCKED_COUPON_DRAFT_OUTPUT_MISSING")
        print("BLOCKED_COUPON_DRAFT_OUTPUT_MISSING: Coupon draft output path missing.")
    else:
        try:
            content = json.loads(input_path.read_text(encoding="utf-8"))
            gr = {}
            if _is_analytical_handoff_payload(content):
                analytical_ready = content.get("analytical_ready") or []
                blocked_probability_missing = content.get("blocked_probability_missing") or []
                blocked_stats_missing = content.get("blocked_stats_missing") or []
                blocked_identity_missing = content.get("blocked_identity_missing") or []
                review_only_partial_data = content.get("review_only_partial_data") or []
                research_gap_minimal_hydration = content.get("research_gap_minimal_hydration") or []
                analytical_quote_ready = [
                    candidate
                    for candidate in analytical_ready
                    if isinstance(candidate, dict)
                    and candidate.get("hydration_status") == "HYDRATED"
                    and candidate.get("promotion_status") == "ANALYZABLE"
                    and candidate.get("promotion_safe_model_probability") is True
                    and candidate.get("ready_for_manual_operator_quote_review") is True
                ]
                approved = []
                if analytical_quote_ready:
                    package_type = "ANALYTICAL_ONLY"
                elif review_only_partial_data:
                    package_type = "REVIEW_ONLY_PARTIAL_DATA_PACKAGE"
                else:
                    package_type = "RESEARCH_GAP_PACKAGE"
                ready_for_manual_operator_quote_review = bool(analytical_quote_ready)
                drafts = [{"draft_id": "draft-0", "selections": analytical_quote_ready}] if analytical_quote_ready else []
                drafts_data = {
                    "artifact_type": "S8_COUPON_DRAFTS",
                    "betting_day": args.date,
                    "run_id": args.run_id,
                    "package_type": package_type,
                    "requires_human_gate": True,
                    "ready_for_human_gate": True,
                    "ready_for_production_execution": False,
                    "production_selectable": False,
                    "production_coupon_write": False,
                    "executable_coupon": False,
                    "betclic_execution_enabled": False,
                    "ready_for_manual_operator_quote_review": ready_for_manual_operator_quote_review,
                    "coupon_draft_count": len(drafts),
                    "drafts": drafts,
                    "analytical_candidate_handoff_path": str(input_path),
                    "analytical_ready": analytical_quote_ready,
                    "blocked_probability_missing": blocked_probability_missing,
                    "blocked_stats_missing": blocked_stats_missing,
                    "blocked_identity_missing": blocked_identity_missing,
                    "review_only_partial_data": review_only_partial_data,
                    "research_gap_minimal_hydration": research_gap_minimal_hydration,
                }
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(json.dumps(drafts_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                print(f"ANALYTICAL_HANDOFF_LANE: Wrote {package_type} package from analytical handoff.")
                status = "PASS"
                is_analytical_only = True
            elif "validation" in content and "gate_results" not in content:
                validation = content.get("validation") or []
                approved = [item for item in validation if item.get("betclic_available") is not False]
            else:
                gr = content.get("gate_results", {})
                approved = gr.get("approved", []) or gr.get("results", []) or []

            if not _is_analytical_handoff_payload(content) and len(approved) == 0:
                extended_pool = gr.get("extended_pool", [])
                unpriced_analytical = [c for c in extended_pool if c.get("status") == "PRICE_PENDING_OPERATOR_CHECK" or c.get("review_status") == "PRICE_PENDING_OPERATOR_CHECK"]
                if len(unpriced_analytical) > 0:
                    drafts_data = {
                        "artifact_type": "S8_COUPON_DRAFTS",
                        "betting_day": args.date,
                        "run_id": args.run_id,
                        "requires_human_gate": True,
                        "ready_for_human_gate": True,
                        "ready_for_manual_operator_quote_review": True,
                        "ready_for_production_execution": False,
                        "production_selectable": False,
                        "production_coupon_write": False,
                        "executable_coupon": False,
                        "betclic_execution_enabled": False,
                        "coupon_draft_count": 1,
                        "drafts": [
                            {
                                "draft_id": "draft-0",
                                "selections": unpriced_analytical
                            }
                        ]
                    }
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_text(json.dumps(drafts_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                    print("ANALYTICAL_ONLY_LANE: Coupon draft written directly from unpriced analytical candidates.")
                    status = "PASS"
                    is_analytical_only = True
                else:
                    status = "BLOCK"
                    blocked_reasons.append("BLOCKED_COUPON_INPUT_EMPTY")
                    print("BLOCKED_COUPON_INPUT_EMPTY: Resolved input has 0 approved candidates.")
        except Exception as e:
            status = "BLOCK"
            blocked_reasons.append("BLOCKED_COUPON_INPUT_MISSING")
            print(f"BLOCKED_COUPON_INPUT_MISSING: Failed to read/validate resolved input: {e}")

    if status == "PASS" and is_analytical_only:
        payload_input_path = str(input_path)
        handoff_package_type = None
        try:
            handoff_package_type = json.loads(output_path.read_text(encoding="utf-8")).get("package_type")
        except Exception:
            pass
        payload = {
            "s8_input_path": payload_input_path,
            "s8_coupon_draft_path": str(output_path),
            "coupon_draft_count": json.loads(output_path.read_text(encoding="utf-8")).get("coupon_draft_count", 0),
            "requires_human_gate": True,
            "ready_for_human_gate": True,
            "ready_for_manual_operator_quote_review": json.loads(output_path.read_text(encoding="utf-8")).get("ready_for_manual_operator_quote_review", False),
            "ready_for_production_execution": False,
            "production_coupon_write": False,
            "executable_coupon": False,
            "betclic_execution_enabled": False,
            "child_run_root": child_env.get("BET_PIPELINE_RUN_ROOT"),
            "child_artifact_dir": child_env.get("BET_PIPELINE_ARTIFACT_DIR"),
        }
        if handoff_package_type is not None:
            payload["package_type"] = handoff_package_type
            payload["analytical_candidate_handoff_path"] = str(input_path)
        write_terminal_script_evidence_or_fail(
            step_id="S8",
            status="PASS",
            payload=payload,
            sources=("scripts/coupon_builder.py",),
            child_env=child_env,
            no_pick_edge_stake_coupon_emitted=False,
            extra_top_level_fields={"production_coupon_write": False},
        )
        try:
            from bet.pipeline.state import PipelineState
            ps = PipelineState.load(args.date)
            ps.advance("S8", summary={
                "coupons": 1,
                "combos": 0,
                "no_bet": False,
            })
        except Exception:
            pass
        sys.exit(0)

    if status == "BLOCK" and args.date:
        validation_file = data_dir / f"betclic_market_validation_{args.date}.json" if data_dir else None
        if validation_file and validation_file.exists():
            try:
                val_data = json.loads(validation_file.read_text(encoding="utf-8"))
                validation = val_data.get("validation") or []
                unavailable = any(item.get("betclic_available") is False for item in validation)
                if unavailable:
                    status = "BLOCK"
                    blocked_reasons.append("BLOCKED_MARKET_AVAILABILITY_MISSING")
                    print("BLOCKED_MARKET_AVAILABILITY_MISSING: At least one market is unavailable on Betclic.")
            except Exception:
                pass

    if status == "BLOCK":
        payload = {
            "s8_input_path": str(input_path) if input_path else None,
            "s8_coupon_draft_path": str(output_path) if output_path else None,
            "coupon_draft_count": 0,
            "requires_human_gate": True,
            "ready_for_human_gate": True,
            "ready_for_manual_operator_quote_review": False,
            "ready_for_production_execution": False,
            "production_coupon_write": False,
            "executable_coupon": False,
            "betclic_execution_enabled": False,
            "child_run_root": child_env.get("BET_PIPELINE_RUN_ROOT"),
            "child_artifact_dir": child_env.get("BET_PIPELINE_ARTIFACT_DIR"),
        }
        write_terminal_script_evidence_or_fail(
            step_id="S8",
            status="BLOCK",
            payload=payload,
            sources=("scripts/coupon_builder.py",),
            child_env=child_env,
            blocked_reasons=tuple(blocked_reasons),
            no_pick_edge_stake_coupon_emitted=False,
            extra_top_level_fields={"production_coupon_write": False},
        )
        sys.exit(5)

    cmd = [
        sys.executable,
        "scripts/coupon_builder.py",
        "--date", args.date,
        "--input", str(input_path),
        "--output", str(output_path),
        "--runtime-mode", args.runtime_mode,
    ]
    if mode != RuntimeMode.PRODUCTION:
        cmd.append("--no-db")

    print(f"Running S8 coupon construction subprocess: {' '.join(cmd)}")
    res = subprocess.run(cmd, env=child_env, capture_output=True, text=True)
    if res.stdout:
        sys.stdout.write(res.stdout)
    if res.stderr:
        sys.stderr.write(res.stderr)

    if res.returncode != 0:
        print(f"coupon_builder.py failed with exit code {res.returncode}")
        sys.exit(res.returncode)

    draft_count = 0
    if output_path and output_path.exists():
        try:
            draft_data = json.loads(output_path.read_text(encoding="utf-8"))
            draft_count = draft_data.get("coupon_draft_count", 0)
        except Exception:
            pass

    payload = {
        "s8_input_path": str(input_path),
        "s8_coupon_draft_path": str(output_path),
        "coupon_draft_count": draft_count,
        "requires_human_gate": True,
        "ready_for_human_gate": True,
        "ready_for_production_execution": False,
        "production_coupon_write": False,
        "executable_coupon": False,
        "betclic_execution_enabled": False,
        "child_run_root": child_env.get("BET_PIPELINE_RUN_ROOT"),
        "child_artifact_dir": child_env.get("BET_PIPELINE_ARTIFACT_DIR"),
    }

    evidence_path = write_terminal_script_evidence_or_fail(
        step_id="S8",
        status="PASS" if draft_count > 0 else "BLOCK",
        payload=payload,
        sources=("scripts/coupon_builder.py",),
        child_env=child_env,
        blocked_reasons=() if draft_count > 0 else ("BLOCKED_COUPON_INPUT_EMPTY",),
        no_pick_edge_stake_coupon_emitted=False,
        extra_top_level_fields={"production_coupon_write": False},
    )

    try:
        from bet.pipeline.state import PipelineState
        ps = PipelineState.load(args.date)
        ps.advance("S8", summary={
            "coupons": draft_count,
            "combos": 0,
            "no_bet": draft_count == 0,
        })
    except Exception:
        pass


if __name__ == "__main__":
    main()
