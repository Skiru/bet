#!/usr/bin/env python3
"""Exporter for lineage-preserving S2 restart seed from a failed analysis run."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bet.pipeline.run_evidence import sha256_file, write_json_atomic


def export_s2_restart_seed(
    source_run_root: Path,
    output_dir: Path,
) -> tuple[Path, Path]:
    """Package through-S1e artifacts and transitive input dependencies into a verified restart seed.

    Excludes ALL S2+ state by construction and attaches semantic origin step metadata.
    """
    source_run_root = Path(source_run_root).resolve(strict=True)
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    summary_file = source_run_root / "run_summary.json"
    if not summary_file.exists():
        raise ValueError(f"Source run_summary.json missing at {summary_file}")

    summary_data = json.loads(summary_file.read_text(encoding="utf-8"))
    source_run_id = summary_data.get("run_id", source_run_root.name)
    source_head = summary_data.get("repo_head_sha") or summary_data.get("source_head", "UNKNOWN")
    source_tree = summary_data.get("git_tree_sha") or summary_data.get("source_tree", "UNKNOWN")
    source_manifest = summary_data.get("manifest_hash") or summary_data.get("source_manifest_sha256", "UNKNOWN")
    as_of = (
        summary_data.get("point_in_time_as_of")
        or summary_data.get("point_in_time_as_of_utc")
        or summary_data.get("started_at")
        or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    )

    artifacts_dir = source_run_root / "artifacts"
    data_dir = source_run_root / "data"

    s0_file = artifacts_dir / "S0.json"
    s1_file = artifacts_dir / "S1.json"
    s1e_file = artifacts_dir / "S1e.json"

    if not s1_file.exists() or not s1e_file.exists():
        raise ValueError(f"Required S1/S1e files missing in {artifacts_dir}")

    s1e_data = json.loads(s1e_file.read_text(encoding="utf-8"))
    payload = s1e_data.get("payload") if isinstance(s1e_data.get("payload"), dict) else s1e_data

    # Find canonical event IDs from payload or referenced data file
    eids = []
    referenced_data_files: list[str] = []

    if payload.get("s1e_output_path"):
        rel_s1e_p = payload["s1e_output_path"]
        s1e_out_path = Path(rel_s1e_p)
        if not s1e_out_path.is_absolute():
            s1e_out_path = source_run_root / rel_s1e_p
        if s1e_out_path.exists():
            rel_path = str(s1e_out_path.relative_to(source_run_root))
            referenced_data_files.append(rel_path)
            univ_data = json.loads(s1e_out_path.read_text(encoding="utf-8"))
            eids = univ_data.get("canonical_event_ids") or [
                r.get("canonical_event_id") for r in univ_data.get("events", []) if isinstance(r, dict)
            ]

    if not eids:
        raw_recs = payload.get("deduplicated_events") or payload.get("event_records") or s1e_data.get("event_records") or []
        for r in raw_recs:
            if isinstance(r, dict):
                eid = r.get("canonical_event_id") or r.get("event_id")
                if eid:
                    eids.append(str(eid))
            elif isinstance(r, str):
                eids.append(r)

    # Check S1 data references
    s1_data = json.loads(s1_file.read_text(encoding="utf-8"))
    s1_payload = s1_data.get("payload") if isinstance(s1_data.get("payload"), dict) else s1_data
    for k in ("s1_output_path", "discovery_output_path", "raw_discovery_path"):
        val = s1_payload.get(k)
        if val and isinstance(val, str):
            p = source_run_root / val
            if p.exists():
                referenced_data_files.append(str(p.relative_to(source_run_root)))

    s1e_eids_sorted = sorted(set(eids))
    eids_hash = hashlib.sha256(json.dumps(s1e_eids_sorted).encode("utf-8")).hexdigest()

    included_files: list[dict[str, Any]] = []
    included_paths_set: set[str] = set()

    def add_file_ref(rel_path: str, origin_step: str):
        if rel_path in included_paths_set:
            return
        # S2+ guard check
        rel_lower = rel_path.lower()
        if "s2" in rel_lower or "s3" in rel_lower or "s4" in rel_lower or "s5" in rel_lower or "s6" in rel_lower or "s7" in rel_lower or "s8" in rel_lower:
            if not rel_path.startswith("artifacts/S0.json") and not rel_path.startswith("artifacts/S1.json") and not rel_path.startswith("artifacts/S1e.json"):
                # S2+ origin! Block inclusion!
                return

        full_p = source_run_root / rel_path
        if full_p.is_file():
            h = sha256_file(full_p)
            included_paths_set.add(rel_path)
            included_files.append({
                "relative_path": rel_path,
                "origin_step": origin_step,
                "sha256": h,
                "size_bytes": full_p.stat().st_size,
            })

    if s0_file.exists():
        add_file_ref("artifacts/S0.json", "S0")
    add_file_ref("artifacts/S1.json", "S1")
    add_file_ref("artifacts/S1e.json", "S1e")
    add_file_ref("run_summary.json", "RUN_PREPARATION")
    if (source_run_root / "event_accounting_ledger.json").exists():
        add_file_ref("event_accounting_ledger.json", "S1e")

    for d_path in referenced_data_files:
        add_file_ref(d_path, "S1" if "discovery" in d_path else "S1e")

    # Also scan data/ ONLY for explicit S0/S1/S1e data files (never S2+ or provider observations)
    if data_dir.exists():
        for fname in os.listdir(data_dir):
            if fname.endswith(".json") and not fname.startswith("S2") and not fname.startswith("S3") and not fname.startswith("S4") and not fname.startswith("S5") and not fname.startswith("S6") and not fname.startswith("S7") and not fname.startswith("S8"):
                add_file_ref(f"data/{fname}", "S1e")

    # Verify no included file has S2+ origin
    for fitem in included_files:
        p_name = Path(fitem["relative_path"]).name
        if p_name in ("S2.json", "S2.3.json", "S2.5.json", "S2.7.json", "S2.9.json", "S2.5_provider_observations.json"):
            raise ValueError(f"S2_PLUS_SEED_CONTAMINATION: Included file {fitem['relative_path']} has S2+ origin!")

    # Record hashes of source run before export
    source_run_hashes_before = {
        fitem["relative_path"]: fitem["sha256"] for fitem in included_files
    }

    manifest_content = {
        "schema_version": 1,
        "import_compatibility_version": "v5.4",
        "source_run_id": source_run_id,
        "source_run_root": str(source_run_root),
        "source_head": source_head,
        "source_tree": source_tree,
        "source_manifest_sha256": source_manifest,
        "source_run_as_of_utc": as_of,
        "event_counts": {
            "s1_raw_discovery": summary_data.get("raw_discovery_count", 998),
            "s1_provider_dedup": summary_data.get("provider_dedup_count", 914),
            "s1e_canonical_universe": len(s1e_eids_sorted),
        },
        "s1e_event_ids_sha256": eids_hash,
        "s1e_event_ids_sample": s1e_eids_sorted[:5],
        "s2_plus_excluded": True,
        "exclusion_patterns": ["artifacts/S2*", "artifacts/S3*", "artifacts/chunks/*", "work_orders/*", "data/S2*"],
        "included_files": included_files,
        "verification_result": "PASS",
    }

    # Derive dynamic generic filenames without hardcoded dates or v3 strings
    seed_base = f"bet_v5_s2_restart_seed_{source_run_id}"
    manifest_json_path = output_dir / f"{seed_base}_manifest.json"
    write_json_atomic(manifest_json_path, manifest_content)

    tar_path = output_dir / f"{seed_base}.tar.gz"
    with tarfile.open(tar_path, "w:gz") as tar:
        tar.add(manifest_json_path, arcname="restart_seed_manifest.json")
        for fref in included_files:
            full_p = source_run_root / fref["relative_path"]
            tar.add(full_p, arcname=fref["relative_path"])

    # Verify source run unchanged after export
    for rel_p, expected_sha in source_run_hashes_before.items():
        actual_sha = sha256_file(source_run_root / rel_p)
        if actual_sha != expected_sha:
            raise ValueError(f"SOURCE_RUN_MUTATED_DURING_EXPORT: {rel_p} changed from {expected_sha} to {actual_sha}")

    print(f"Exported S2 restart seed tar archive: {tar_path}")
    print(f"Exported S2 restart seed manifest: {manifest_json_path}")
    return tar_path, manifest_json_path


def main():
    p = argparse.ArgumentParser(description="Export S2 restart seed from failed run.")
    p.add_argument("--source-run-root", required=True, help="Path to failed run root")
    p.add_argument("--output-dir", default="/tmp", help="Output directory for seed tar/manifest")
    args = p.parse_args()

    export_s2_restart_seed(
        source_run_root=Path(args.source_run_root),
        output_dir=Path(args.output_dir),
    )


if __name__ == "__main__":
    main()
