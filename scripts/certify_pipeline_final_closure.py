#!/usr/bin/env python3
"""Inventory-driven final pipeline certifier and release gate."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_NODES = (
    "tests/test_canonical_continuity_reference.py",
    "tests/test_failed_run_replay.py",
    "tests/test_pipeline_certifier.py::test_certifier_child_fixture",
    "tests/test_canonical_continuity_v4_owner_regressions.py",
    "tests/test_canonical_continuity_v4_offline_chain_proof.py",
    "tests/test_agent_work_order_owner_alignment.py",
)

class CertificationError(RuntimeError):
    """Stable fail-closed certification exception."""
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git(*args: str, root: Path = ROOT, check: bool = True) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if check and completed.returncode != 0:
        raise CertificationError(
            f"CERT_GIT_STATE_UNAVAILABLE:{' '.join(args)}:{completed.stderr.strip()}"
        )
    return completed.stdout.strip()


def source_manifest(root: Path) -> tuple[list[dict[str, Any]], str]:
    """Hash every tracked or non-ignored source path, including deletions."""
    raw = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root,
        check=False,
        capture_output=True,
        timeout=30,
    )
    if raw.returncode != 0:
        raise CertificationError("CERT_SOURCE_MANIFEST_UNAVAILABLE")
    entries: list[dict[str, Any]] = []
    for encoded in sorted(filter(None, raw.stdout.split(b"\0"))):
        relative = os.fsdecode(encoded)
        path = root / relative
        if path.is_symlink():
            entries.append(
                {
                    "path": relative,
                    "kind": "symlink",
                    "target": os.readlink(path),
                }
            )
        elif path.is_file():
            entries.append(
                {
                    "path": relative,
                    "kind": "file",
                    "size": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
        else:
            entries.append({"path": relative, "kind": "deleted"})
    canonical = json.dumps(entries, sort_keys=True, separators=(",", ":"))
    return entries, hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def parse_junit(path: Path, allowed_skips: list[dict[str, str]] | None = None, inventory_mandatory: list[str] | None = None) -> dict[str, Any]:
    if allowed_skips is None:
        allowed_skips = []
    if inventory_mandatory is None:
        inventory_mandatory = []
    if not path.is_file():
        raise CertificationError("CERT_JUNIT_MISSING")
    try:
        root_node = ET.parse(path).getroot()
    except (ET.ParseError, OSError) as exc:
        raise CertificationError("CERT_JUNIT_MALFORMED") from exc

    suites = [root_node] if root_node.tag == "testsuite" else list(root_node.findall("testsuite"))
    if not suites:
        raise CertificationError("CERT_JUNIT_EMPTY")

    total_tests = 0
    total_failures = 0
    total_errors = 0
    total_skipped = 0
    executed_nodes = []

    # Validate each testcase
    for tc in root_node.findall(".//testcase"):
        total_tests += 1
        name = tc.attrib.get("name", "")
        classname = tc.attrib.get("classname", "")
        tc_file = tc.attrib.get("file", "")
        if tc_file:
            node_id = f"{tc_file}::{name}"
        else:
            # Normalize classname.name to path/to/file.py::name format for comparison
            parts = classname.rsplit(".", 1)
            if parts and len(parts) == 2:
                class_part, test_name = parts
                # If there's a dot in classname, convert to path format
                path_str = classname.replace(".", "/") + ".py"
                node_id = f"{path_str}::{name}"
            else:
                path_str = classname.replace(".", "/") + ".py"
                node_id = f"{path_str}::{name}"
        executed_nodes.append(node_id)

        is_mandatory = any(m in node_id or m in classname for m in inventory_mandatory)

        # Check failures and errors
        if tc.find("failure") is not None:
            total_failures += 1
            if is_mandatory:
                raise CertificationError(f"CERT_MANDATORY_TEST_FAILED:{node_id}")
        if tc.find("error") is not None:
            total_errors += 1
            if is_mandatory:
                raise CertificationError(f"CERT_MANDATORY_TEST_ERROR:{node_id}")

        # Check skips
        skipped_node = tc.find("skipped")
        if skipped_node is not None:
            total_skipped += 1
            if is_mandatory:
                raise CertificationError(f"CERT_MANDATORY_TEST_SKIPPED:{node_id}")

            # Check skip against allowlist
            skip_msg = skipped_node.attrib.get("message", "") or skipped_node.text or ""
            allowed = False
            for allowed_skip in allowed_skips:
                if allowed_skip["node_id"] in node_id or allowed_skip["node_id"] in classname:
                    import re
                    if re.search(allowed_skip["reason_regex"], skip_msg, re.IGNORECASE):
                        allowed = True
                        break
            if not allowed:
                raise CertificationError(f"CERT_UNAPPROVED_SKIP:{node_id}:{skip_msg}")

    if total_tests <= 0:
        raise CertificationError("CERT_ZERO_TESTS_EXECUTED")

    return {
        "tests": total_tests,
        "failures": total_failures,
        "errors": total_errors,
        "skipped": total_skipped,
        "junit_sha256": sha256_file(path),
        "executed_nodes": executed_nodes,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Inventory-driven certifier")
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--pytest-node", action="append", dest="nodes")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--junit", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--expected-head")
    parser.add_argument("--expected-source-tree-sha256")
    args = parser.parse_args()

    try:
        # Check for pre-existing output
        if Path(args.output).exists():
            raise CertificationError("CERT_OUTPUT_ALREADY_EXISTS")

        # Load and validate inventory
        inv_path = ROOT / "config" / "pipeline_certification_inventory.json"
        if not inv_path.is_file():
            raise CertificationError("CERT_INVENTORY_MISSING")
        inventory = json.loads(inv_path.read_text(encoding="utf-8"))

        root_path = Path(args.repo_root).resolve(strict=True)
        head = _git("rev-parse", "HEAD", root=root_path)
        branch = _git("symbolic-ref", "--short", "-q", "HEAD", root=root_path, check=False) or "DETACHED"

        if args.expected_head and head != args.expected_head:
            raise CertificationError(f"CERT_HEAD_MISMATCH:{head}")

        entries_before, tree_before = source_manifest(root_path)
        if args.expected_source_tree_sha256 and tree_before != args.expected_source_tree_sha256:
            raise CertificationError(f"CERT_SOURCE_TREE_MISMATCH:{tree_before}")

        entries_before, tree_before = source_manifest(root_path)
        if args.expected_source_tree_sha256 and tree_before != args.expected_source_tree_sha256:
            raise CertificationError(f"CERT_SOURCE_TREE_MISMATCH:{tree_before}")

        # Load mandatory nodes and counts
        inventory_mandatory = inventory.get("mandatory_nodes", [])
        expected_minimum_counts = inventory.get("expected_minimum_counts", {})

        cli_nodes = args.nodes or []
        if cli_nodes and len(cli_nodes) == 1 and "::" in cli_nodes[0]:
            raise CertificationError("CERT_ONLY_ONE_CLI_TEST_SUPPLIED")

        # effective_nodes = mandatory_nodes UNION additional_nodes
        effective_nodes = list(sorted(set(inventory_mandatory) | set(cli_nodes)))

        # Ensure mandatory files exist on disk
        for f in inventory_mandatory:
            f_path = root_path / f
            if not f_path.is_file():
                raise CertificationError(f"CERT_MANDATORY_FILE_MISSING:{f}")

        # Pytest collection and substance check on effective_nodes
        collect_cmd = [sys.executable, "-m", "pytest", "--collect-only", "-q"] + effective_nodes
        collect_res = subprocess.run(collect_cmd, cwd=root_path, capture_output=True, text=True, timeout=60)
        if collect_res.returncode == 5:
            raise CertificationError("CERT_PYTEST_COLLECTION_EMPTY")
        elif collect_res.returncode != 0:
            raise CertificationError(f"CERT_PYTEST_COLLECTION_FAILED: {collect_res.stderr}")

        collected_nodes = []
        for line in collect_res.stdout.splitlines():
            line = line.strip()
            if "::" in line and " " not in line and not line.startswith("no-tests-ran"):
                collected_nodes.append(line)

        # Count collection per mandatory file
        collected_by_file = {}
        for node in collected_nodes:
            for f in inventory_mandatory:
                if node.startswith(f):
                    collected_by_file.setdefault(f, []).append(node)

        for f in inventory_mandatory:
            col_count = len(collected_by_file.get(f, []))
            expected_min = expected_minimum_counts.get(f, 0)
            if col_count < expected_min:
                raise CertificationError(f"CERT_COLLECTION_BELOW_MINIMUM:{f}:got={col_count}:expected={expected_min}")

        # Execute test suite on effective_nodes
        junit_path = Path(args.junit).resolve()
        junit_path.parent.mkdir(parents=True, exist_ok=True)
        junit_path.unlink(missing_ok=True)

        test_cmd = [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            f"--junitxml={junit_path}",
        ] + effective_nodes

        # Inject environment safety markers
        env = dict(os.environ)
        env["BET_PIPELINE_CERTIFIER_ACTIVE"] = "1"
        env["BET_MOCK_ODDS"] = "1"
        env["BET_PIPELINE_SKIP_FETCH"] = "1"

        t_start = datetime.now(timezone.utc)
        completed = subprocess.run(
            test_cmd,
            cwd=root_path,
            env=env,
            capture_output=True,
            text=True,
            timeout=args.timeout_seconds,
        )
        t_end = datetime.now(timezone.utc)

        summary = parse_junit(junit_path, inventory.get("allowed_skips", []), inventory_mandatory)
        executed_nodes = summary.get("executed_nodes", [])

        # Ensure no collected mandatory node was deselected or renamed
        executed_nodes_set = set(executed_nodes)
        for f in inventory_mandatory:
            for node in collected_by_file.get(f, []):
                # Pytest JUnit report outputs absolute or relative class paths, let's normalize check:
                # E.g., tc_file can be matched by endswith or relative checks.
                # To be bulletproof, check that the node (or its stem/ending) was executed.
                found_exec = False
                for exec_node in executed_nodes:
                    # check if the relative parts match
                    if (
                        node == exec_node
                        or node in exec_node
                        or exec_node in node
                        or node.replace("/", ".").replace(".py", "") in exec_node.replace("/", ".").replace(".py", "")
                    ):
                        found_exec = True
                        break
                if not found_exec:
                    raise CertificationError(f"CERT_MANDATORY_NODE_DESELECTED_OR_RENAMED:{node}")
        if completed.returncode != 0 or summary["failures"] or summary["errors"]:
            raise CertificationError(
                f"CERT_TEST_FAILURE:rc={completed.returncode}:"
                f"failures={summary['failures']}:errors={summary['errors']}"
            )

        entries_after, tree_after = source_manifest(root_path)
        if entries_after != entries_before or tree_after != tree_before:
            raise CertificationError("CERT_SOURCE_MUTATED_DURING_TESTS")

        # Execute mandatory production validators as part of closure
        validators_run_records = []
        validators = [
            "validate_production_surface.py",
            "validate_power_agent_control_plane.py",
            "validate_manifest_power_agents.py",
            "validate_reachability_graph.py",
            "validate_provider_registry.py",
            "validate_database_access.py",
        ]
        for val_script in validators:
            val_cmd = [sys.executable, str(ROOT / "scripts" / val_script)]
            val_env = dict(os.environ)
            val_env["PYTHONPATH"] = f"src:{ROOT}"
            val_res = subprocess.run(val_cmd, cwd=root_path, env=val_env, capture_output=True, text=True, timeout=60)

            out_sha = hashlib.sha256(val_res.stdout.encode("utf-8")).hexdigest()
            validators_run_records.append({
                "script": val_script,
                "command": val_cmd,
                "exit_code": val_res.returncode,
                "output_sha256": out_sha,
            })

            if val_res.returncode != 0:
                raise CertificationError(f"CERT_VALIDATOR_FAILED:{val_script}:rc={val_res.returncode}:{val_res.stderr.strip()}")

            # Verify git status remains unchanged after every validator
            entries_curr, tree_curr = source_manifest(root_path)
            if entries_curr != entries_before or tree_curr != tree_before:
                raise CertificationError(f"CERT_SOURCE_MUTATED_DURING_VALIDATOR:{val_script}")

        # Record exact certification receipt
        certificate = {
            "schema_version": 1,
            "artifact_type": "PIPELINE_CANONICAL_CONTINUITY_CERTIFICATE_V1",
            "status": "PASS",
            "decision": "READY_FOR_BET_EXECUTOR_SESSION",
            "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "source": {
                "branch": branch,
                "head_sha": head,
                "source_tree_sha256": tree_before,
                "source_file_count": len(entries_before),
            },
            "validators": validators_run_records,
            "test_run": {
                "nodes": effective_nodes,
                "collected_node_ids": collected_nodes,
                "executed_node_ids": executed_nodes,
                "command_argv": test_cmd,
                "return_code": completed.returncode,
                "duration_seconds": (t_end - t_start).total_seconds(),
                "tests": summary.get("tests", 0),
                "failures": summary.get("failures", 0),
                "errors": summary.get("errors", 0),
                "skipped": summary.get("skipped", 0),
                "junit_sha256": summary.get("junit_sha256", ""),
            },
            "claims": {
                "live_pipeline_executed": False,
                "bookmaker_interaction_performed": False,
                "production_database_mutated": False,
                "merge_performed": False,
            },
        }

        # Write exclusive certificate file
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(certificate, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        print(json.dumps(certificate, sort_keys=True, indent=2))
        return 0

    except Exception as exc:
        print(f"BLOCK:{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
