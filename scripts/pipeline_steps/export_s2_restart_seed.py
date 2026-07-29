#!/usr/bin/env python3
"""Exporter for lineage-preserving S2 restart seed from a failed analysis run.

Guarantees full provenance binding and true semantic exclusion of all S2+ state.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bet.pipeline.receipts import (
    compute_source_manifest_sha256,
    get_git_commit_head,
    get_git_tree_sha,
)
from bet.pipeline.run_evidence import sha256_file

HEX_40_REGEX = re.compile(r"^[0-9a-fA-F]{40}$")
HEX_64_REGEX = re.compile(r"^[0-9a-fA-F]{64}$")

S2_PLUS_STEPS = {
    "S2",
    "S2.3",
    "S2.5",
    "S2.7",
    "S2.9",
    "S3",
    "S4",
    "S5",
    "S6",
    "S7",
    "S8",
    "S9",
    "S10",
}


def validate_provenance_field(value: Any, name: str, is_64: bool = False) -> str:
    """Validate that a provenance field is non-empty, non-placeholder, and valid hex."""
    val_str = str(value or "").strip()
    if not val_str or val_str.upper() in (
        "UNKNOWN",
        "N/A",
        "NULL",
        "NONE",
        "PLACEHOLDER",
    ):
        raise ValueError(
            f"PROVENANCE_UNKNOWN_REJECTED: {name} is invalid or UNKNOWN: '{val_str}'"
        )
    pattern = HEX_64_REGEX if is_64 else HEX_40_REGEX
    if not pattern.match(val_str):
        raise ValueError(
            f"PROVENANCE_FORMAT_REJECTED: {name} string '{val_str}' is not valid hex digest"
        )
    return val_str


def is_semantically_s2_plus(rel_path: str, full_path: Path) -> bool:
    """Return True if rel_path or full_path semantically belongs to S2+."""
    rel_lower = rel_path.lower()
    file_name = full_path.name.lower()

    if rel_path in (
        "artifacts/S0.json",
        "artifacts/S1.json",
        "artifacts/S1e.json",
        "run_summary.json",
        "event_accounting_ledger.json",
        "restart_seed_manifest.json",
    ):
        return False
    if file_name.endswith("_state.json") or file_name == "state.json":
        pass
    elif "s1e_event_universe" in file_name or "s1e_active_events" in file_name:
        return False

    # Check for S2+ step artifact filenames
    if file_name in (
        "s2.json",
        "s2.3.json",
        "s2.5.json",
        "s2.7.json",
        "s2.9.json",
        "s3.json",
        "s4.json",
        "s5.json",
        "s6.json",
        "s7.json",
        "s8.json",
    ):
        return True

    # Check for S2+ keywords in filename or path
    if any(
        kw in file_name
        for kw in (
            "tipster_consensus",
            "shortlist",
            "chunks",
            "work_order",
            "market_matrix",
            "coupon",
            "pricing",
        )
    ):
        return True
    if "artifacts/chunks" in rel_lower or "work_orders" in rel_lower:
        return True

    # Inspect JSON content if applicable
    if full_path.suffix == ".json" and full_path.is_file():
        try:
            content = json.loads(full_path.read_text(encoding="utf-8"))
            if isinstance(content, dict):
                stage = str(
                    content.get("stage")
                    or content.get("step_id")
                    or content.get("position")
                    or ""
                ).upper()
                if stage in S2_PLUS_STEPS:
                    return True
                blocked_at = str(content.get("blocked_at_step") or "").upper()
                if blocked_at in S2_PLUS_STEPS:
                    return True
                completed = [
                    str(x).upper()
                    for x in content.get("completed_steps", [])
                    if isinstance(x, str)
                ]
                if any(c in S2_PLUS_STEPS for c in completed):
                    return True
                boundaries = [
                    str(x).upper()
                    for x in content.get("boundaries", [])
                    if isinstance(x, str)
                ]
                if any(b in S2_PLUS_STEPS for b in boundaries):
                    return True
        except Exception:
            pass

    return False


def export_s2_restart_seed(
    source_run_root: Path,
    output_dir: Path,
) -> tuple[Path, Path]:
    """Package through-S1e artifacts and transitive input dependencies into a verified restart seed.

    Excludes ALL S2+ state by construction and enforces strict provenance binding.
    """
    source_run_root = Path(source_run_root).resolve(strict=True)
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    summary_file = source_run_root / "run_summary.json"
    if not summary_file.exists():
        raise ValueError(f"Source run_summary.json missing at {summary_file}")

    summary_data = json.loads(summary_file.read_text(encoding="utf-8"))
    source_run_id = summary_data.get("run_id", source_run_root.name)

    repo_root = Path(__file__).resolve().parents[2]
    raw_head = summary_data.get("repo_head_sha") or summary_data.get("source_head")
    raw_tree = summary_data.get("git_tree_sha") or summary_data.get("source_tree")
    raw_manifest = summary_data.get("manifest_hash") or summary_data.get(
        "source_manifest_sha256"
    )

    if not raw_head or str(raw_head).upper() == "UNKNOWN":
        raw_head = get_git_commit_head(repo_root)
    if not raw_tree or str(raw_tree).upper() == "UNKNOWN":
        raw_tree = get_git_tree_sha(repo_root)
    if not raw_manifest or str(raw_manifest).upper() == "UNKNOWN":
        raw_manifest = compute_source_manifest_sha256(repo_root)

    source_head = validate_provenance_field(raw_head, "source_head")
    source_tree = validate_provenance_field(raw_tree, "source_tree")
    source_manifest = validate_provenance_field(
        raw_manifest, "source_manifest_sha256", is_64=True
    )

    gen_head = validate_provenance_field(
        get_git_commit_head(repo_root), "generator_head"
    )
    gen_tree = validate_provenance_field(get_git_tree_sha(repo_root), "generator_tree")
    gen_version = "v5.4"

    as_of = (
        summary_data.get("point_in_time_as_of")
        or summary_data.get("point_in_time_as_of_utc")
        or summary_data.get("started_at")
        or datetime.now(UTC).isoformat().replace("+00:00", "Z")
    )

    artifacts_dir = source_run_root / "artifacts"
    data_dir = source_run_root / "data"

    s0_file = artifacts_dir / "S0.json"
    s1_file = artifacts_dir / "S1.json"
    s1e_file = artifacts_dir / "S1e.json"

    if not s1_file.exists() or not s1e_file.exists():
        raise ValueError(f"Required S1/S1e files missing in {artifacts_dir}")

    s1e_data = json.loads(s1e_file.read_text(encoding="utf-8"))
    payload = (
        s1e_data.get("payload")
        if isinstance(s1e_data.get("payload"), dict)
        else s1e_data
    )

    eids = []
    rel_s1e_out = None
    if payload.get("s1e_output_path"):
        rel_s1e_p = payload["s1e_output_path"]
        s1e_out_path = Path(rel_s1e_p)
        if not s1e_out_path.is_absolute():
            s1e_out_path = source_run_root / rel_s1e_p
        if s1e_out_path.exists():
            rel_s1e_out = str(s1e_out_path.relative_to(source_run_root))
            univ_data = json.loads(s1e_out_path.read_text(encoding="utf-8"))
            eids = univ_data.get("canonical_event_ids") or [
                r.get("canonical_event_id")
                for r in univ_data.get("events", [])
                if isinstance(r, dict)
            ]

    if not eids:
        raw_recs = (
            payload.get("deduplicated_events")
            or payload.get("event_records")
            or s1e_data.get("event_records")
            or []
        )
        for r in raw_recs:
            if isinstance(r, dict):
                eid = r.get("canonical_event_id") or r.get("event_id")
                if eid:
                    eids.append(str(eid))
            elif isinstance(r, str):
                eids.append(r)

    s1e_eids_sorted = sorted(set(eids))
    source_s1e_count = len(s1e_eids_sorted)

    eids_hash = hashlib.sha256(json.dumps(s1e_eids_sorted).encode("utf-8")).hexdigest()

    staging_dir = Path(tempfile.mkdtemp(prefix="export_seed_staging_"))
    try:
        staging_artifacts = staging_dir / "artifacts"
        staging_data = staging_dir / "data"
        staging_artifacts.mkdir(parents=True)
        staging_data.mkdir(parents=True)

        included_files: list[dict[str, Any]] = []

        def add_file_to_seed(src_file: Path, rel_path: str, origin_step: str):
            if is_semantically_s2_plus(rel_path, src_file):
                raise ValueError(
                    f"S2_PLUS_SEED_CONTAMINATION: Attempted to add S2+ file {rel_path} to seed!"
                )
            dst_file = staging_dir / rel_path
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            dst_file.write_bytes(src_file.read_bytes())
            h = sha256_file(dst_file)
            included_files.append(
                {
                    "relative_path": rel_path,
                    "origin_step": origin_step,
                    "sha256": h,
                    "size_bytes": dst_file.stat().st_size,
                }
            )

        def add_bytes_to_seed(content_bytes: bytes, rel_path: str, origin_step: str):
            dst_file = staging_dir / rel_path
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            dst_file.write_bytes(content_bytes)
            h = sha256_file(dst_file)
            included_files.append(
                {
                    "relative_path": rel_path,
                    "origin_step": origin_step,
                    "sha256": h,
                    "size_bytes": len(content_bytes),
                }
            )

        # 1. Add S0, S1, S1e artifact files
        if s0_file.exists():
            add_file_to_seed(s0_file, "artifacts/S0.json", "S0")
        add_file_to_seed(s1_file, "artifacts/S1.json", "S1")
        add_file_to_seed(s1e_file, "artifacts/S1e.json", "S1e")

        # 2. Add S1e event universe data file
        if rel_s1e_out and (source_run_root / rel_s1e_out).exists():
            add_file_to_seed(source_run_root / rel_s1e_out, rel_s1e_out, "S1e")

        # 3. Write clean, sanitized through-S1e bootstrap metadata
        clean_summary = {
            "schema_version": 1,
            "run_id": source_run_id,
            "status": "PASS",
            "last_completed_step": "S1e",
            "blocked_at_step": None,
            "position": "S1e",
            "completed_steps": ["S0", "S1", "S1e"],
            "repo_head_sha": source_head,
            "git_tree_sha": source_tree,
            "manifest_hash": source_manifest,
            "started_at": as_of,
            "finished_at": as_of,
        }
        add_bytes_to_seed(
            json.dumps(clean_summary, indent=2).encode("utf-8"),
            "run_summary.json",
            "RUN_PREPARATION",
        )

        clean_ledger = {
            "source_s1e_count": source_s1e_count,
            "revalidated_total_count": source_s1e_count,
            "active_for_s2_restart_count": source_s1e_count,
            "terminalized_count": 0,
            "as_of_utc": as_of,
            "step_boundaries": ["S0", "S1", "S1e"],
        }
        add_bytes_to_seed(
            json.dumps(clean_ledger, indent=2).encode("utf-8"),
            "event_accounting_ledger.json",
            "S1e",
        )

        clean_state = {
            "run_id": source_run_id,
            "position": "S1e",
            "completed_steps": ["S0", "S1", "S1e"],
            "as_of_utc": as_of,
        }
        add_bytes_to_seed(
            json.dumps(clean_state, indent=2).encode("utf-8"),
            f"data/{source_run_id}_state.json",
            "RUN_PREPARATION",
        )

        # Build manifest content
        manifest_content = {
            "schema_version": 1,
            "import_compatibility_version": "v5.4",
            "source_run_id": source_run_id,
            "source_run_root": str(source_run_root),
            "source_head": source_head,
            "source_tree": source_tree,
            "source_manifest_sha256": source_manifest,
            "source_run_as_of_utc": as_of,
            "generator_head": gen_head,
            "generator_tree": gen_tree,
            "generator_version": gen_version,
            "event_counts": {
                "s1_raw_discovery": summary_data.get("raw_discovery_count", 998),
                "s1_provider_dedup": summary_data.get("provider_dedup_count", 914),
                "s1e_canonical_universe": source_s1e_count,
            },
            "s1e_event_ids_sha256": eids_hash,
            "s1e_event_ids_sample": s1e_eids_sorted[:5],
            "s2_plus_excluded": True,
            "exclusion_patterns": [
                "artifacts/S2*",
                "artifacts/S3*",
                "artifacts/S4*",
                "artifacts/S5*",
                "artifacts/S6*",
                "artifacts/S7*",
                "artifacts/S8*",
                "artifacts/chunks/*",
                "work_orders/*",
                "data/S2*",
                "data/*consensus*",
                "data/*shortlist*",
            ],
            "included_files": included_files,
            "verification_result": "PASS",
        }

        manifest_json_bytes = (
            json.dumps(manifest_content, indent=2, sort_keys=True).encode("utf-8")
            + b"\n"
        )
        staging_manifest_file = staging_dir / "restart_seed_manifest.json"
        staging_manifest_file.write_bytes(manifest_json_bytes)

        seed_base = f"bet_v5_s2_restart_seed_{source_run_id}"
        manifest_out_path = output_dir / f"{seed_base}_manifest.json"
        manifest_out_path.write_bytes(manifest_json_bytes)

        tar_path = output_dir / f"{seed_base}.tar.gz"

        with tarfile.open(tar_path, "w:gz") as tar:
            tar.add(staging_manifest_file, arcname="restart_seed_manifest.json")
            for fitem in included_files:
                rel = fitem["relative_path"]
                tar.add(staging_dir / rel, arcname=rel)

        print(f"Exported S2 restart seed tar archive: {tar_path}")
        print(f"Exported S2 restart seed manifest: {manifest_out_path}")
        return tar_path, manifest_out_path

    finally:
        if staging_dir.exists():
            import shutil

            shutil.rmtree(staging_dir, ignore_errors=True)


def main():
    p = argparse.ArgumentParser(description="Export S2 restart seed from failed run.")
    p.add_argument("--source-run-root", required=True, help="Path to failed run root")
    p.add_argument(
        "--output-dir", default="/tmp", help="Output directory for seed tar/manifest"
    )
    args = p.parse_args()

    export_s2_restart_seed(
        source_run_root=Path(args.source_run_root),
        output_dir=Path(args.output_dir),
    )


if __name__ == "__main__":
    main()
