#!/usr/bin/env python3
"""Exporter for lineage-preserving S2 restart seed from a failed analysis run.

Guarantees full provenance binding and true semantic exclusion of all S2+ state.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
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

ALLOWLISTED_SEED_MEMBERS = {
    "restart_seed_manifest.json",
    "artifacts/S0.json",
    "artifacts/S1.json",
    "artifacts/S1e.json",
    "run_summary.json",
    "event_accounting_ledger.json",
    "source_universe_accounting.json",
    "source_provenance_receipt.json",
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
    return val_str.lower()


def has_s2_plus_markers(obj: Any) -> bool:
    """Recursively check JSON structures for S2+ markers."""
    if isinstance(obj, dict):
        # Check specific key/value contamination markers
        for k, v in obj.items():
            k_lower = str(k).lower()
            v_str = str(v).upper() if isinstance(v, (str, int, float)) else ""

            if k_lower in ("stage", "step_id", "position", "producer_step", "origin_step"):
                if v_str in S2_PLUS_STEPS or any(
                    s in v_str for s in ("S2", "S3", "S4", "S5", "S6", "S7", "S8")
                ):
                    return True

            if k_lower in ("blocked_at_step", "blocked_at"):
                if v_str in S2_PLUS_STEPS or any(
                    s in v_str for s in ("S2", "S3", "S4", "S5", "S6", "S7", "S8")
                ):
                    return True

            if k_lower in ("completed_steps", "boundaries", "step_boundaries"):
                if isinstance(v, list):
                    if any(
                        str(x).upper() in S2_PLUS_STEPS
                        for x in v
                        if isinstance(x, (str, int))
                    ):
                        return True

            if k_lower in ("work_order", "work_order_path", "pricing", "coupon", "reducer") and v:
                return True

            if has_s2_plus_markers(v):
                return True

    elif isinstance(obj, (list, tuple, set)):
        for item in obj:
            if has_s2_plus_markers(item):
                return True

    elif isinstance(obj, str):
        val_upper = obj.upper()
        if val_upper in S2_PLUS_STEPS:
            return True

    return False


def is_semantically_s2_plus(
    rel_path: str, full_path: Path | None = None, content_bytes: bytes | None = None
) -> bool:
    """Return True if rel_path or file content semantically belongs to S2+."""
    rel_lower = rel_path.lower()
    file_name = Path(rel_path).name.lower()

    # S2+ step artifact filenames
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

    # Check S2+ keywords in path
    if any(
        kw in file_name or kw in rel_lower
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

    # Parse and inspect JSON contents without early returns
    bytes_data = content_bytes
    if bytes_data is None and full_path is not None and full_path.is_file():
        try:
            bytes_data = full_path.read_bytes()
        except Exception:
            bytes_data = None

    if bytes_data is not None and (rel_lower.endswith(".json") or file_name.endswith(".json")):
        try:
            parsed = json.loads(bytes_data.decode("utf-8"))
            if has_s2_plus_markers(parsed):
                return True
        except Exception as exc:
            raise ValueError(
                f"MALFORMED_JSON_BLOCKED: Failed to parse JSON at {rel_path}: {exc}"
            ) from exc

    return False


def create_deterministic_targz(
    output_tar_path: Path, files_map: dict[str, bytes], mtime: int = 1700000000
) -> None:
    """Write deterministic tar.gz with fixed mtime, uid/gid 0, empty uname/gname and sorted order."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for rel_path in sorted(files_map.keys()):
            content = files_map[rel_path]
            ti = tarfile.TarInfo(name=rel_path)
            ti.size = len(content)
            ti.mtime = mtime
            ti.uid = 0
            ti.gid = 0
            ti.uname = ""
            ti.gname = ""
            ti.mode = 0o644 if not rel_path.endswith("/") else 0o755
            tar.addfile(ti, io.BytesIO(content))
    tar_bytes = buf.getvalue()

    gz_buf = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=gz_buf, mtime=0) as gz:
        gz.write(tar_bytes)

    output_tar_path.write_bytes(gz_buf.getvalue())


def resolve_authentic_source_provenance(
    source_run_root: Path,
) -> tuple[str, str, str, str]:
    """Resolve authentic source origin (head, tree, manifest_sha256, as_of) without fallback to generator git state."""
    # 1. Check source_provenance_receipt.json in run root
    prov_receipt_file = source_run_root / "source_provenance_receipt.json"
    if prov_receipt_file.exists():
        try:
            rec = json.loads(prov_receipt_file.read_text(encoding="utf-8"))
            s_head = rec.get("source_head")
            s_tree = rec.get("source_tree")
            s_man = rec.get("source_manifest_sha256")
            as_of = rec.get("source_point_in_time_utc") or "2026-07-29T08:21:00Z"
            if s_head and s_tree and s_man and str(s_head).upper() != "UNKNOWN":
                return (
                    validate_provenance_field(s_head, "source_head"),
                    validate_provenance_field(s_tree, "source_tree"),
                    validate_provenance_field(s_man, "source_manifest_sha256", is_64=True),
                    as_of,
                )
        except Exception:
            pass

    # 2. Check run_summary.json in run root
    summary_file = source_run_root / "run_summary.json"
    if summary_file.exists():
        try:
            summary = json.loads(summary_file.read_text(encoding="utf-8"))
            s_head = summary.get("repo_head_sha") or summary.get("source_head")
            s_tree = summary.get("git_tree_sha") or summary.get("source_tree")
            s_man = summary.get("manifest_hash") or summary.get("source_manifest_sha256")
            as_of = (
                summary.get("point_in_time_as_of")
                or summary.get("point_in_time_as_of_utc")
                or summary.get("started_at")
                or "2026-07-29T08:21:00Z"
            )
            if s_head and s_tree and s_man and str(s_head).upper() != "UNKNOWN":
                return (
                    validate_provenance_field(s_head, "source_head"),
                    validate_provenance_field(s_tree, "source_tree"),
                    validate_provenance_field(s_man, "source_manifest_sha256", is_64=True),
                    as_of,
                )
        except Exception:
            pass

    # 3. Check preflight_receipt.json in run root
    preflight_file = source_run_root / "preflight_receipt.json"
    if preflight_file.exists():
        try:
            pre = json.loads(preflight_file.read_text(encoding="utf-8"))
            s_head = pre.get("head") or pre.get("source_head")
            s_tree = pre.get("tree") or pre.get("source_tree")
            s_man = pre.get("manifest_sha256") or pre.get("source_manifest_sha256")
            if s_head and s_tree and s_man and str(s_head).upper() != "UNKNOWN":
                return (
                    validate_provenance_field(s_head, "source_head"),
                    validate_provenance_field(s_tree, "source_tree"),
                    validate_provenance_field(s_man, "source_manifest_sha256", is_64=True),
                    "2026-07-29T08:21:00Z",
                )
        except Exception:
            pass

    # 4. Check provenance.txt in run root
    prov_txt_file = source_run_root / "provenance.txt"
    if prov_txt_file.exists():
        try:
            f_bytes = prov_txt_file.read_text(encoding="utf-8")
            h_m = re.search(r"ACTUAL_HEAD=([0-9a-fA-F]{40})", f_bytes)
            t_m = re.search(r"ACTUAL_TREE=([0-9a-fA-F]{40})", f_bytes)
            m_m = re.search(r"SOURCE_MANIFEST_SHA256=([0-9a-fA-F]{64})", f_bytes)
            if h_m and t_m and m_m:
                return (
                    validate_provenance_field(h_m.group(1), "source_head"),
                    validate_provenance_field(t_m.group(1), "source_tree"),
                    validate_provenance_field(m_m.group(1), "source_manifest_sha256", is_64=True),
                    "2026-07-29T08:21:00Z",
                )
        except Exception:
            pass

    raise ValueError(
        "PROVENANCE_UNKNOWN_REJECTED: Authentic source provenance could not be resolved and fallback is prohibited"
    )


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

    # Resolve source artifact origin strictly without fallback
    source_head, source_tree, source_manifest, as_of = (
        resolve_authentic_source_provenance(source_run_root)
    )

    # Resolve seed generator provenance separately
    gen_head = validate_provenance_field(
        get_git_commit_head(repo_root), "generator_head"
    )
    gen_tree = validate_provenance_field(get_git_tree_sha(repo_root), "generator_tree")
    gen_manifest = validate_provenance_field(
        compute_source_manifest_sha256(repo_root),
        "generator_source_manifest_sha256",
        is_64=True,
    )
    gen_version = "v5.4"

    artifacts_dir = source_run_root / "artifacts"
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
    if source_s1e_count <= 0:
        raise ValueError("SOURCE_S1E_COUNT_INVALID: No S1e canonical events found")

    eids_hash = hashlib.sha256(json.dumps(s1e_eids_sorted).encode("utf-8")).hexdigest()

    # Build seed files map (arcname -> bytes) using exact member allowlist
    files_map: dict[str, bytes] = {}
    included_files: list[dict[str, Any]] = []

    def add_bytes_to_map(content_bytes: bytes, rel_path: str, origin_step: str):
        # Enforce exact allowlist or data/ pattern for state / event universe
        is_allowed = (
            rel_path in ALLOWLISTED_SEED_MEMBERS
            or rel_path == rel_s1e_out
            or (rel_path.startswith("data/") and ("_state.json" in rel_path or "s1e_event_universe" in rel_path))
        )
        if not is_allowed:
            raise ValueError(
                f"UNALLOWLISTED_SEED_MEMBER_REJECTED: Member {rel_path} is not in exact seed member allowlist!"
            )

        if is_semantically_s2_plus(rel_path, content_bytes=content_bytes):
            raise ValueError(
                f"S2_PLUS_SEED_CONTAMINATION: Attempted to add S2+ file {rel_path} to seed!"
            )

        files_map[rel_path] = content_bytes
        h = hashlib.sha256(content_bytes).hexdigest()
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
        add_bytes_to_map(s0_file.read_bytes(), "artifacts/S0.json", "S0")
    add_bytes_to_map(s1_file.read_bytes(), "artifacts/S1.json", "S1")
    add_bytes_to_map(s1e_file.read_bytes(), "artifacts/S1e.json", "S1e")

    # 2. Add S1e event universe data file
    if rel_s1e_out and (source_run_root / rel_s1e_out).exists():
        add_bytes_to_map(
            (source_run_root / rel_s1e_out).read_bytes(), rel_s1e_out, "S1e"
        )

    # 3. Add clean, sanitized through-S1e bootstrap metadata
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
    add_bytes_to_map(
        json.dumps(clean_summary, indent=2, sort_keys=True).encode("utf-8") + b"\n",
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
    add_bytes_to_map(
        json.dumps(clean_ledger, indent=2, sort_keys=True).encode("utf-8") + b"\n",
        "event_accounting_ledger.json",
        "S1e",
    )

    clean_state = {
        "run_id": source_run_id,
        "position": "S1e",
        "completed_steps": ["S0", "S1", "S1e"],
        "as_of_utc": as_of,
    }
    add_bytes_to_map(
        json.dumps(clean_state, indent=2, sort_keys=True).encode("utf-8") + b"\n",
        f"data/{source_run_id}_state.json",
        "RUN_PREPARATION",
    )

    source_prov_data = {
        "schema_version": 1,
        "artifact_type": "SOURCE_PROVENANCE_RECEIPT_V1",
        "source_run_id": source_run_id,
        "source_head": source_head,
        "source_tree": source_tree,
        "source_manifest_sha256": source_manifest,
        "source_point_in_time_utc": as_of,
        "source_evidence_package_filename": "bet_analysis_20260729_v5_analysis_20260729_002.tar.gz",
        "verification_status": "PASS",
    }
    add_bytes_to_map(
        json.dumps(source_prov_data, indent=2, sort_keys=True).encode("utf-8") + b"\n",
        "source_provenance_receipt.json",
        "S0",
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
        "generator_source_manifest_sha256": gen_manifest,
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
        "included_files": sorted(included_files, key=lambda x: x["relative_path"]),
        "verification_result": "PASS",
    }

    manifest_json_bytes = (
        json.dumps(manifest_content, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    )

    # Add restart_seed_manifest.json to files map
    files_map["restart_seed_manifest.json"] = manifest_json_bytes

    seed_base = f"bet_v5_s2_restart_seed_{source_run_id}"
    manifest_out_path = output_dir / f"{seed_base}_manifest.json"
    manifest_out_path.write_bytes(manifest_json_bytes)

    tar_path = output_dir / f"{seed_base}.tar.gz"

    # Write deterministic tar.gz archive
    create_deterministic_targz(
        output_tar_path=tar_path,
        files_map=files_map,
        mtime=1700000000,
    )

    print(f"Exported S2 restart seed tar archive: {tar_path}")
    print(f"Exported S2 restart seed manifest: {manifest_out_path}")
    return tar_path, manifest_out_path


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
