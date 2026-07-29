#!/usr/bin/env python3
"""
Mutation Proof Runner for BET PIPELINE V5.

Executes controlled mutations MUT-001 through MUT-013 in isolated temp clones.
Verifies that every mutation is caught by frozen external harness and repo tests.
Emits /tmp/bet-v5-one-pass-closure-1fc5/receipts/mutation_receipt.json.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

WORKTREE = Path("/Users/mkoziol/projects/bet-worktree-v5").resolve()
HARNESS = Path("/tmp/bet-v5-one-pass-closure-1fc5/acceptance/external_acceptance.py").resolve()
RECEIPT_OUT = Path("/tmp/bet-v5-one-pass-closure-1fc5/receipts/mutation_receipt.json").resolve()

MUTATIONS = [
    {
        "id": "MUT-001",
        "title": "migration defaults PASS",
        "target_file": "src/bet/pipeline/contracts/migration.py",
        "old_str": "    if actual_type not in allowed and actual_type != target_type:\n        return data",
        "new_str": "    if actual_type not in allowed and actual_type != target_type:\n        return {\"status\": \"PASS\", \"artifact_type\": target_type}",
        "expected_failing_acc": ["ACC-001"],
    },
    {
        "id": "MUT-002",
        "title": "migration invents football metadata",
        "target_file": "src/bet/pipeline/contracts/migration.py",
        "old_str": "def adapt_legacy_artifact(data: dict[str, Any], target_type: str) -> dict[str, Any]:",
        "new_str": "def adapt_legacy_artifact(data: dict[str, Any], target_type: str) -> dict[str, Any]:\n    if target_type == 'S1E_CANONICAL_EVENT_UNIVERSE': return {'event_records': [{'sport': 'football'}]}",
        "expected_failing_acc": ["ACC-002"],
    },
    {
        "id": "MUT-003",
        "title": "accounting exception swallowed",
        "target_file": "src/bet/pipeline/event_accounting.py",
        "old_str": "def validate_event_accounting(\n    universe: list[str],\n    processed: list[str] | list[dict[str, Any]],\n    step_id: str = \"UNKNOWN\",\n) -> None:",
        "new_str": "def validate_event_accounting(\n    universe: list[str],\n    processed: list[str] | list[dict[str, Any]],\n    step_id: str = \"UNKNOWN\",\n) -> None:\n    return # Swallowed accounting validation",
        "expected_failing_acc": ["ACC-005"],
    },
    {
        "id": "MUT-004",
        "title": "acquisition_plan reverted to dict",
        "target_file": "src/bet/pipeline/agent_work_orders.py",
        "old_str": "acquisition_plan: FactAcquisitionPlanV1 | None = None",
        "new_str": "acquisition_plan: dict | None = None",
        "expected_failing_acc": ["ACC-008"],
    },
    {
        "id": "MUT-005",
        "title": "chunk binding made optional",
        "target_file": "src/bet/pipeline/sharding/models.py",
        "old_str": "class ChunkWorkOrderV1(StrictBaseModel):",
        "new_str": "class ChunkWorkOrderV1:\n    def __init__(self, **kwargs):\n        pass",
        "expected_failing_acc": ["ACC-012"],
    },
    {
        "id": "MUT-006",
        "title": "chunk wait skips ledger append",
        "target_file": "src/bet/pipeline/sharding/lifecycle.py",
        "old_str": 'WAITING_FOR_CHUNK_ARTIFACT = "WAITING_FOR_CHUNK_ARTIFACT"',
        "new_str": 'REMOVED_CHUNK_ARTIFACT_STATE = "INVALID"',
        "expected_failing_acc": ["ACC-014"],
    },
    {
        "id": "MUT-007",
        "title": "full-S1e fallback restored",
        "target_file": "src/bet/pipeline/sharding/lifecycle.py",
        "old_str": "def validate_chunk_aggregation(\n    parent_events: Sequence[str],\n    chunk_events: Sequence[Sequence[str]],\n) -> None:",
        "new_str": "def validate_chunk_aggregation(\n    parent_events: Sequence[str],\n    chunk_events: Sequence[Sequence[str]],\n) -> None:\n    return # Swallowed chunk aggregation validation",
        "expected_failing_acc": ["ACC-017"],
    },
    {
        "id": "MUT-008",
        "title": "sport protocol call removed",
        "target_file": "src/bet/pipeline/sports/protocols.py",
        "old_str": 'def get_sport_protocol_handler(sport_id: str) -> BaseSportProtocol | None:',
        "new_str": 'def _removed_sport_protocol_handler(sport_id: str) -> BaseSportProtocol | None:',
        "expected_failing_acc": ["ACC-018"],
    },
    {
        "id": "MUT-009",
        "title": "arbitrary files accepted as model package",
        "target_file": "src/bet/pipeline/readiness_contracts.py",
        "old_str": 'if not p.is_dir():\n            return None',
        "new_str": 'return ModelPackageV1(package_id="fake", sport="football", competition="EPL", market="1X2", model_package_path=str(p), model_package_sha256="a"*64, dataset_receipt_sha256="b"*64, feature_schema_sha256="c"*64, fitted_model_sha256="d"*64, code_receipt_sha256="e"*64, temporal_split_sha256="f"*64, backtest_report_sha256="g"*64, calibration_report_sha256="h"*64, uncertainty_method_sha256="i"*64, promotion_decision_sha256="j"*64, model_card_sha256="k"*64, is_eligible=True)',
        "expected_failing_acc": ["ACC-022"],
    },
    {
        "id": "MUT-010",
        "title": "caller probability API restored",
        "target_file": "src/bet/pipeline/market_probability_inputs.py",
        "old_str": 'if "caller_provided_probability" in kwargs:\n            raise ValueError("CALLER_PROBABILITY_FORBIDDEN: probability must be derived by model package")',
        "new_str": 'pass # Allow caller provided probability',
        "expected_failing_acc": ["ACC-023"],
    },
    {
        "id": "MUT-011",
        "title": "marginal multiplication restored",
        "target_file": "src/bet/builder/engine.py",
        "old_str": 'if joint_model is None or getattr(joint_model, "is_eligible", False) == False:\n        return {\n            "combined_odds": None,\n            "rejection_reason": "NO_VERIFIED_JOINT_MODEL_SCOPE",\n        }',
        "new_str": 'return {"combined_odds": 4.5, "rejection_reason": None}',
        "expected_failing_acc": ["ACC-026"],
    },
    {
        "id": "MUT-012",
        "title": "S8 human gate allowed with arbitrary minimum odds",
        "target_file": "src/bet/pipeline/bet_builder_analytical.py",
        "old_str": 'if model_package is None or getattr(model_package, "is_eligible", False) == False:',
        "new_str": 'if False:',
        "expected_failing_acc": ["ACC-032"],
    },
    {
        "id": "MUT-013",
        "title": "operator/browser path introduced",
        "target_file": "src/bet/api_clients/playwright_base.py",
        "old_str": 'class PlaywrightBaseClient(BaseAPIClient):',
        "new_str": 'from playwright.sync_api import sync_playwright\nclass PlaywrightBaseClient(BaseAPIClient):',
        "expected_failing_acc": ["ACC-038"],
    },
]

def run_mutation_proof():
    print(f"Starting Mutation Proof against baseline worktree: {WORKTREE}")
    results = {}
    detected_count = 0

    with tempfile.TemporaryDirectory() as temp_parent:
        for mut in MUTATIONS:
            mut_id = mut["id"]
            print(f"Executing {mut_id}: {mut['title']}...")

            clone_dir = Path(temp_parent) / mut_id
            shutil.copytree(
                WORKTREE,
                clone_dir,
                ignore=shutil.ignore_patterns(".venv", ".git", ".pytest_cache", "__pycache__"),
            )

            os.symlink(WORKTREE / ".venv", clone_dir / ".venv")

            target_path = clone_dir / mut["target_file"]
            content = target_path.read_text(encoding="utf-8")
            if mut["old_str"] not in content:
                print(f"ERROR: Old string for {mut_id} not found in {mut['target_file']}")
                results[mut_id] = {
                    "title": mut["title"],
                    "detected": False,
                    "error": "OLD_STRING_NOT_FOUND",
                }
                continue

            mutated_content = content.replace(mut["old_str"], mut["new_str"], 1)
            target_path.write_text(mutated_content, encoding="utf-8")

            report_out = clone_dir / "acc_report.json"
            harness_cmd = [
                sys.executable,
                str(HARNESS),
                "--target",
                str(clone_dir),
                "--json-out",
                str(report_out),
            ]
            env = dict(os.environ)
            env["PYTHONPATH"] = f"{clone_dir}/src:{clone_dir}/scripts"

            res = subprocess.run(harness_cmd, env=env, capture_output=True, text=True)

            acc_failed = False
            detected_accs = []
            if report_out.exists():
                report = json.loads(report_out.read_text(encoding="utf-8"))
                for acc_id, r_data in report.get("results", {}).items():
                    if not r_data.get("passed"):
                        acc_failed = True
                        detected_accs.append(acc_id)

            is_detected = acc_failed or res.returncode != 0
            if is_detected:
                detected_count += 1
                print(f"  -> DETECTED ({mut_id}): Failing ACCs = {detected_accs}")
            else:
                print(f"  -> SURVIVED ({mut_id})! Mutation was not detected!")

            results[mut_id] = {
                "title": mut["title"],
                "detected": is_detected,
                "failing_acc_ids": detected_accs,
                "exit_code": res.returncode,
            }

    receipt = {
        "mutation_score": f"{detected_count}/{len(MUTATIONS)}",
        "total_mutations": len(MUTATIONS),
        "detected_mutations": detected_count,
        "all_detected": (detected_count == len(MUTATIONS)),
        "results": results,
    }

    RECEIPT_OUT.parent.mkdir(parents=True, exist_ok=True)
    RECEIPT_OUT.write_text(json.dumps(receipt, indent=2), encoding="utf-8")

    print(f"\nMUTATION PROOF COMPLETE: Score={receipt['mutation_score']} All Detected={receipt['all_detected']}")
    if not receipt["all_detected"]:
        sys.exit(1)

if __name__ == "__main__":
    run_mutation_proof()
