#!/usr/bin/env python3
"""Certify the current source tree from a real, bounded pytest execution.

The certificate is deliberately boring: it is derived from the current Git
state, an exact source-file manifest, and pytest's JUnit XML.  It is never
created for a failing, empty, timed-out, or source-mutating test run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_NODES = (
    "tests/test_canonical_continuity_reference.py",
    "tests/test_failed_run_replay.py",
    "tests/test_pipeline_certifier.py::test_certifier_child_fixture",
    "tests/test_canonical_continuity_v4_owner_regressions.py",
    "tests/test_canonical_continuity_v4_offline_chain_proof.py",
)


class CertificationError(RuntimeError):
    """A stable, fail-closed certification failure."""


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
            # A tracked deletion is part of the exact working-tree state.
            entries.append({"path": relative, "kind": "deleted"})
    canonical = json.dumps(entries, sort_keys=True, separators=(",", ":"))
    return entries, hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def parse_junit(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise CertificationError("CERT_JUNIT_MISSING")
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError) as exc:
        raise CertificationError("CERT_JUNIT_MALFORMED") from exc
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    if not suites:
        raise CertificationError("CERT_JUNIT_EMPTY")

    def total(field: str) -> int:
        try:
            return sum(int(suite.attrib.get(field, "0")) for suite in suites)
        except ValueError as exc:
            raise CertificationError(f"CERT_JUNIT_{field.upper()}_INVALID") from exc

    summary = {
        "tests": total("tests"),
        "failures": total("failures"),
        "errors": total("errors"),
        "skipped": total("skipped"),
        "junit_sha256": sha256_file(path),
    }
    if summary["tests"] <= 0:
        raise CertificationError("CERT_ZERO_TESTS_EXECUTED")
    return summary


def _validate_nodes(nodes: Iterable[str], root: Path) -> tuple[str, ...]:
    validated: list[str] = []
    for node in nodes:
        path_text = node.split("::", 1)[0]
        path = (root / path_text).resolve()
        try:
            path.relative_to(root.resolve())
        except ValueError as exc:
            raise CertificationError(f"CERT_TEST_OUTSIDE_REPOSITORY:{node}") from exc
        if not path.is_file() or path.suffix != ".py":
            raise CertificationError(f"CERT_TEST_NODE_MISSING:{node}")
        validated.append(node)
    if not validated:
        raise CertificationError("CERT_TEST_SET_EMPTY")
    return tuple(validated)


def _write_exclusive_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise CertificationError("CERT_OUTPUT_ALREADY_EXISTS") from exc
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise


def certify(
    *,
    root: Path,
    nodes: Iterable[str],
    output: Path,
    junit: Path,
    timeout_seconds: int,
    expected_head: str | None = None,
    expected_source_tree_sha256: str | None = None,
) -> dict[str, Any]:
    root = root.resolve(strict=True)
    nodes = _validate_nodes(nodes, root)
    if not 1 <= timeout_seconds <= 3600:
        raise CertificationError("CERT_TIMEOUT_OUT_OF_RANGE")
    if output.exists():
        raise CertificationError("CERT_OUTPUT_ALREADY_EXISTS")

    head = _git("rev-parse", "HEAD", root=root)
    branch = _git("symbolic-ref", "--short", "-q", "HEAD", root=root, check=False) or "DETACHED"
    if expected_head and head != expected_head:
        raise CertificationError(f"CERT_HEAD_MISMATCH:{head}")
    entries_before, tree_before = source_manifest(root)
    if expected_source_tree_sha256 and tree_before != expected_source_tree_sha256:
        raise CertificationError(f"CERT_SOURCE_TREE_MISMATCH:{tree_before}")

    junit.parent.mkdir(parents=True, exist_ok=True)
    junit.unlink(missing_ok=True)
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        f"--junitxml={junit}",
        *nodes,
    ]
    environment = dict(os.environ)
    environment["BET_PIPELINE_CERTIFIER_ACTIVE"] = "1"
    try:
        completed = subprocess.run(
            command,
            cwd=root,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise CertificationError("CERT_TEST_TIMEOUT") from exc

    summary = parse_junit(junit)
    if completed.returncode != 0 or summary["failures"] or summary["errors"]:
        raise CertificationError(
            f"CERT_TEST_FAILURE:rc={completed.returncode}:"
            f"failures={summary['failures']}:errors={summary['errors']}"
        )
    entries_after, tree_after = source_manifest(root)
    if entries_after != entries_before or tree_after != tree_before:
        raise CertificationError("CERT_SOURCE_MUTATED_DURING_TESTS")

    certificate = {
        "schema_version": 1,
        "artifact_type": "PIPELINE_CANONICAL_CONTINUITY_CERTIFICATE_V1",
        "status": "PASS",
        "decision": "READY_FOR_BET_EXECUTOR_SESSION",
        "generated_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "source": {
            "branch": branch,
            "head_sha": head,
            "source_tree_sha256": tree_before,
            "source_file_count": len(entries_before),
        },
        "test_run": {
            "nodes": list(nodes),
            "command_argv": command,
            "return_code": completed.returncode,
            **summary,
        },
        "claims": {
            "live_pipeline_executed": False,
            "bookmaker_interaction_performed": False,
            "production_database_mutated": False,
            "merge_performed": False,
        },
    }
    _write_exclusive_json(output, certificate)
    return certificate


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--pytest-node", action="append", dest="nodes")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--junit", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--expected-head")
    parser.add_argument("--expected-source-tree-sha256")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        certificate = certify(
            root=args.repo_root,
            nodes=args.nodes or DEFAULT_NODES,
            output=args.output,
            junit=args.junit,
            timeout_seconds=args.timeout_seconds,
            expected_head=args.expected_head,
            expected_source_tree_sha256=args.expected_source_tree_sha256,
        )
    except (CertificationError, OSError) as exc:
        print(f"BLOCK:{exc}", file=sys.stderr)
        return 1
    print(json.dumps(certificate, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
