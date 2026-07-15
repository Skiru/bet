#!/usr/bin/env python3
"""Fail-closed validator for the canonical S6 -> S8 evidence chain."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bet.pipeline.integration_artifacts import resolve_manifest_step_output
from bet.pipeline.manifest import load_pipeline_manifest
from bet.pipeline.run_coordination import ResumeLedger, ResumeLedgerError
from bet.pipeline.run_evidence import repo_head_sha, sha256_file, write_json_atomic


STEP_TYPES = {
    "S6": "S6_PORTFOLIO_REPEAT_GUARD_V2",
    "S7": "S7_ANALYTICAL_APPROVAL_SET_V2",
    "S7b": "S7B_SUPERBET_MANUAL_MAPPING",
    "S8": "S8_SUPERBET_MANUAL_QUOTE_PACK",
}
SOURCE_FIELDS = {
    "S6": ("source_s5_path", "source_s5_sha256"),
    "S7": ("source_s6_path", "source_s6_sha256"),
    "S7b": ("source_s7_output_path", "source_s7_output_sha256"),
    "S8": ("source_s7b_output_path", "source_s7b_output_sha256"),
}


def _inside_run(path_value: object, run_root: Path) -> Path:
    if not isinstance(path_value, str) or not path_value:
        raise ValueError("CHAIN_SOURCE_PATH_MISSING")
    path = Path(path_value)
    if path.is_symlink():
        raise ValueError(f"CHAIN_SYMLINK_FORBIDDEN:{path}")
    resolved = path.resolve(strict=True)
    try:
        resolved.relative_to(run_root)
    except ValueError as exc:
        raise ValueError(f"CHAIN_PATH_OUTSIDE_RUN:{resolved}") from exc
    if not resolved.is_file():
        raise ValueError(f"CHAIN_SOURCE_NOT_FILE:{resolved}")
    return resolved


def _canonical_payload_sha(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_chain(
    *,
    run_root: Path,
    betting_day: str,
    run_id: str,
    steps: tuple[str, ...],
) -> dict[str, Any]:
    run_root = run_root.resolve(strict=True)
    if run_root.is_symlink() or not run_root.is_dir():
        raise ValueError("CHAIN_RUN_ROOT_INVALID")
    if not steps or len(set(steps)) != len(steps) or any(step not in STEP_TYPES for step in steps):
        raise ValueError("CHAIN_STEP_SET_INVALID")
    canonical_order = tuple(step for step in STEP_TYPES if step in steps)
    if steps != canonical_order:
        raise ValueError("CHAIN_STEP_ORDER_INVALID")

    manifest = load_pipeline_manifest(ROOT / "config" / "pipeline_manifest.json")
    issues: list[str] = []
    evidence_hashes: dict[str, str] = {}
    output_hashes: dict[str, str] = {}
    output_paths: dict[str, str] = {}

    ledger_path = run_root / "resume_ledger.json"
    ledger: dict[str, Any] = {}
    try:
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        ResumeLedger.verify(ledger)
        if ledger.get("betting_day") != betting_day or ledger.get("run_id") != run_id:
            issues.append("CHAIN_RESUME_BINDING_MISMATCH")
    except (OSError, json.JSONDecodeError, ResumeLedgerError, TypeError, ValueError) as exc:
        issues.append(f"CHAIN_RESUME_INVALID:{type(exc).__name__}")

    predecessor_path = run_root / "artifacts" / "S5.json"
    predecessor_sha = sha256_file(predecessor_path) if predecessor_path.is_file() else ""
    if not predecessor_sha:
        issues.append("CHAIN_S5_SOURCE_MISSING")

    for step in steps:
        evidence = run_root / "artifacts" / f"{step}.json"
        duplicates = sorted(
            candidate.resolve()
            for candidate in run_root.rglob(f"{step}.json")
            if candidate.parent.name == "artifacts"
        )
        if duplicates != [evidence.resolve()]:
            issues.append(f"CHAIN_CANONICAL_EVIDENCE_CARDINALITY:{step}:{len(duplicates)}")
            continue
        try:
            evidence_data = json.loads(evidence.read_text(encoding="utf-8"))
            if (
                evidence_data.get("artifact_type") != "SCRIPT_EVIDENCE"
                or evidence_data.get("step_id") != step
                or evidence_data.get("status") != "PASS"
                or evidence_data.get("betting_day") != betting_day
                or evidence_data.get("run_id") != run_id
            ):
                raise ValueError("CHAIN_EVIDENCE_CONTRACT_INVALID")
            evidence_sha = sha256_file(evidence)
            output_path, output_data = resolve_manifest_step_output(
                manifest=manifest,
                run_root=run_root,
                step_id=step,
                betting_day=betting_day,
                run_id=run_id,
                expected_artifact_type=STEP_TYPES[step],
            )
            output_sha = sha256_file(output_path)
            if (
                output_data.get("schema_version") != 2
                or output_data.get("artifact_type") != STEP_TYPES[step]
                or output_data.get("betting_day") != betting_day
                or output_data.get("run_id") != run_id
            ):
                raise ValueError("CHAIN_OUTPUT_CONTRACT_INVALID")

            source_path_field, source_sha_field = SOURCE_FIELDS[step]
            source_path = _inside_run(output_data.get(source_path_field), run_root)
            source_sha = output_data.get(source_sha_field)
            if source_path != predecessor_path.resolve() or source_sha != predecessor_sha:
                raise ValueError("CHAIN_PREDECESSOR_BINDING_MISMATCH")
            if sha256_file(source_path) != source_sha:
                raise ValueError("CHAIN_PREDECESSOR_HASH_MISMATCH")

            # S7b and S8 also bind the predecessor evidence, not just output.
            if step in {"S7b", "S8"}:
                lower = "s7" if step == "S7b" else "s7b"
                source_evidence = _inside_run(
                    output_data.get(f"source_{lower}_evidence_path"), run_root
                )
                recorded_evidence_sha = output_data.get(f"source_{lower}_evidence_sha256")
                if sha256_file(source_evidence) != recorded_evidence_sha:
                    raise ValueError("CHAIN_PREDECESSOR_EVIDENCE_HASH_MISMATCH")

            evidence_hashes[step] = evidence_sha
            output_hashes[step] = output_sha
            output_paths[step] = str(output_path)
            predecessor_path = output_path
            predecessor_sha = output_sha

            entries = [
                entry
                for entry in ledger.get("entries", [])
                if entry.get("step_id") == step and entry.get("status") == "PASS"
            ]
            if not any(
                evidence_sha in entry.get("output_hashes", {}).values()
                or output_sha in entry.get("output_hashes", {}).values()
                for entry in entries
            ):
                issues.append(f"CHAIN_RESUME_OUTPUT_UNBOUND:{step}")
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            issues.append(f"{step}:{exc}")

    conflicts = sorted((run_root / "validation" / "attempts" / "S6").glob("*.json"))
    if conflicts:
        issues.append(f"CHAIN_IMMUTABLE_CONFLICTS_PRESENT:{len(conflicts)}")

    return {
        "steps": list(steps),
        "evidence_sha256": evidence_hashes,
        "output_sha256": output_hashes,
        "output_paths": output_paths,
        "issues": issues,
        "unresolved_conflicts_count": len(conflicts),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--betting-day", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--steps", default="S6,S7,S7b,S8")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        payload = validate_chain(
            run_root=args.run_root,
            betting_day=args.betting_day,
            run_id=args.run_id,
            steps=tuple(step.strip() for step in args.steps.split(",") if step.strip()),
        )
    except (OSError, ValueError) as exc:
        payload = {
            "steps": [],
            "evidence_sha256": {},
            "output_sha256": {},
            "output_paths": {},
            "issues": [str(exc)],
            "unresolved_conflicts_count": 0,
        }
    status = "PASS" if not payload["issues"] else "BLOCK"
    report = {
        "schema_version": 1,
        "artifact_type": "PIPELINE_RUN_EVIDENCE_CHAIN_VALIDATION_V1",
        "status": status,
        "betting_day": args.betting_day,
        "run_id": args.run_id,
        "source_git_sha": repo_head_sha(ROOT),
        "generated_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "report_payload": payload,
        "report_payload_sha256": _canonical_payload_sha(payload),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(args.output, report)
    print(json.dumps(report, sort_keys=True))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
