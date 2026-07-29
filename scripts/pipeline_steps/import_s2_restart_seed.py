#!/usr/bin/env python3
"""Importer for lineage-preserving S2 restart seed into a new target run root with fail-closed safety."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
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
from bet.pipeline.run_evidence import sha256_file, write_json_atomic

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
    return val_str.lower()


def has_s2_plus_markers(obj: Any) -> bool:
    """Recursively check JSON structures for S2+ contamination markers."""
    if isinstance(obj, dict):
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


def is_semantically_s2_plus(rel_path: str, full_path: Path) -> bool:
    """Return True if rel_path or file content semantically belongs to S2+."""
    rel_lower = rel_path.lower()
    file_name = full_path.name.lower()

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

    if full_path.suffix == ".json" and full_path.is_file():
        try:
            content = json.loads(full_path.read_text(encoding="utf-8"))
            if has_s2_plus_markers(content):
                return True
        except Exception as exc:
            raise ValueError(
                f"MALFORMED_JSON_BLOCKED: Failed to parse JSON at {rel_path}: {exc}"
            ) from exc

    return False


def parse_utc_timestamp(ts_str: str) -> datetime:
    """Parse an ISO format UTC timestamp string into a datetime object."""
    ts_clean = ts_str.replace("Z", "+00:00")
    dt = datetime.fromisoformat(ts_clean)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def revalidate_event_freshness(
    events: list[dict[str, Any]],
    as_of_utc: str,
    min_lead_seconds: int = 900,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Revalidate event freshness against point-in-time as_of_utc and minimum lead time.

    Classifies every event into explicit statuses:
    - ACTIVE_FOR_S2_RESTART
    - STARTED_BEFORE_RESTART
    - INSUFFICIENT_LEAD_TIME
    - CANCELLED
    - POSTPONED_OR_UNCONFIRMED
    - INVALID_START_TIME
    - MISSING_REQUIRED_EVENT_DATA
    """
    t_asof = parse_utc_timestamp(as_of_utc)
    ledger: list[dict[str, Any]] = []
    active_events: list[dict[str, Any]] = []

    for evt in events:
        eid = str(evt.get("canonical_event_id") or evt.get("event_id") or "")
        start_time_str = (
            evt.get("start_time_utc")
            or evt.get("kickoff_utc")
            or evt.get("event_time")
            or evt.get("kickoff")
            or evt.get("event_start_time")
            or ""
        )
        raw_status = str(
            evt.get("status") or evt.get("event_status") or "SCHEDULED"
        ).upper()

        if not eid or not start_time_str:
            status = "MISSING_REQUIRED_EVENT_DATA"
            reason = "Missing canonical_event_id or start_time_utc"
        elif raw_status in ("CANCELLED", "CANCELED"):
            status = "CANCELLED"
            reason = f"Event status is {raw_status}"
        elif raw_status in ("POSTPONED", "UNCONFIRMED", "SUSPENDED"):
            status = "POSTPONED_OR_UNCONFIRMED"
            reason = f"Event status is {raw_status}"
        else:
            try:
                t_start = parse_utc_timestamp(start_time_str)
                lead_seconds = (t_start - t_asof).total_seconds()
                if t_start <= t_asof:
                    status = "STARTED_BEFORE_RESTART"
                    reason = f"Event started at {start_time_str} <= as_of {as_of_utc}"
                elif lead_seconds < min_lead_seconds:
                    status = "INSUFFICIENT_LEAD_TIME"
                    reason = (
                        f"Lead time {lead_seconds:.1f}s < required {min_lead_seconds}s"
                    )
                else:
                    status = "ACTIVE_FOR_S2_RESTART"
                    reason = f"Active with lead time {lead_seconds:.1f}s"
            except Exception as exc:
                status = "INVALID_START_TIME"
                reason = f"Failed to parse start_time_utc '{start_time_str}': {exc}"

        record = {
            "canonical_event_id": eid,
            "status": status,
            "reason": reason,
            "start_time_utc": start_time_str,
            "as_of_utc": as_of_utc,
            "raw_status": raw_status,
        }
        ledger.append(record)

        if status == "ACTIVE_FOR_S2_RESTART":
            active_events.append(evt)

    return ledger, active_events


def import_s2_restart_seed(
    seed_tar_path: Path,
    target_run_root: Path,
    target_run_id: str,
    target_head: str,
    target_tree: str,
    target_manifest: str,
    seed_manifest_path: Path | str | None = None,
    expected_seed_tar_sha256: str | None = None,
    expected_seed_manifest_sha256: str | None = None,
    as_of_utc: str | None = None,
    min_lead_seconds: int = 900,
    runtime_mode: str = "LIVE_SHADOW",
) -> dict[str, Any]:
    """Import and verify S2 restart seed into target_run_root using staged extraction."""
    seed_tar_path = Path(seed_tar_path).resolve(strict=True)
    target_run_root = Path(target_run_root).resolve()

    # 1. Reject target directory collisions first
    if target_run_root.exists() and any(target_run_root.iterdir()):
        raise ValueError(f"TARGET_RUN_ROOT_EXISTS_NON_EMPTY: {target_run_root}")

    # 2. Inspect tar member safety before extraction
    with tarfile.open(seed_tar_path, "r:gz") as tar:
        members = tar.getmembers()
        if len(members) > 1000:
            raise ValueError(
                f"SAFE_TAR_IMPORT_LIMIT_EXCEEDED: member count {len(members)} > 1000"
            )

        seen_names: set[str] = set()
        total_uncompressed_bytes = 0

        for m in members:
            m_path = Path(m.name)
            if (
                m_path.is_absolute()
                or ".." in m_path.parts
                or m.name.startswith("/")
                or m.name.startswith("\\")
            ):
                raise ValueError(
                    f"SAFE_TAR_IMPORT_TRAVERSAL_DETECTED: Unsafe member path {m.name}"
                )

            if not (m.isfile() or m.isdir()):
                raise ValueError(
                    f"SAFE_TAR_IMPORT_UNSAFE_TYPE: Member {m.name} type is unsafe (symlink/hardlink/device)"
                )

            norm_name = str(m_path).lower()
            if norm_name in seen_names:
                raise ValueError(
                    f"SAFE_TAR_IMPORT_DUPLICATE_MEMBER: Member {m.name} duplicate or case collision"
                )
            seen_names.add(norm_name)

            if m.size > 100 * 1024 * 1024:
                raise ValueError(
                    f"SAFE_TAR_IMPORT_OVERSIZED_MEMBER: Member {m.name} size {m.size} > 100MB"
                )
            total_uncompressed_bytes += m.size

        if total_uncompressed_bytes > 500 * 1024 * 1024:
            raise ValueError(
                f"SAFE_TAR_IMPORT_OVERSIZED_TOTAL: Total uncompressed size {total_uncompressed_bytes} > 500MB"
            )

    # 3. Resolve external manifest path or sibling manifest file
    if not seed_manifest_path:
        cand1 = seed_tar_path.parent / (seed_tar_path.name.replace(".tar.gz", "") + "_manifest.json")
        cand2 = seed_tar_path.parent / "restart_seed_manifest.json"
        if cand1.exists():
            seed_manifest_path = cand1
        elif cand2.exists():
            seed_manifest_path = cand2
        else:
            raise ValueError(
                "EXTERNAL_MANIFEST_MISSING: External seed manifest path required (--restart-seed-manifest)"
            )

    try:
        seed_man_p = Path(seed_manifest_path).resolve(strict=True)
    except FileNotFoundError as exc:
        raise ValueError(f"EXTERNAL_MANIFEST_MISSING: External manifest file not found at {seed_manifest_path}") from exc

    if not seed_man_p.exists():
        raise ValueError(f"EXTERNAL_MANIFEST_MISSING: External manifest file not found at {seed_man_p}")

    external_manifest_bytes = seed_man_p.read_bytes()

    # 4. Verify target execution provenance against current repository state
    target_head = validate_provenance_field(target_head, "target_head")
    target_tree = validate_provenance_field(target_tree, "target_tree")
    target_manifest = validate_provenance_field(
        target_manifest, "target_manifest", is_64=True
    )

    repo_root = Path(__file__).resolve().parents[2]
    cur_head = get_git_commit_head(repo_root)
    cur_tree = get_git_tree_sha(repo_root)
    cur_manifest = compute_source_manifest_sha256(repo_root)

    if (
        target_head.lower() != cur_head.lower()
        or target_tree.lower() != cur_tree.lower()
        or target_manifest.lower() != cur_manifest.lower()
    ):
        raise ValueError(
            f"TARGET_PROVENANCE_MISMATCH: Target execution params ({target_head[:8]}/{target_tree[:8]}/{target_manifest[:8]}) do not match repo state ({cur_head[:8]}/{cur_tree[:8]}/{cur_manifest[:8]})"
        )

    if expected_seed_tar_sha256:
        actual_tar_sha = sha256_file(seed_tar_path)
        if actual_tar_sha.lower() != expected_seed_tar_sha256.lower():
            raise ValueError(
                f"SEED_TAR_SHA_MISMATCH: {actual_tar_sha} vs expected {expected_seed_tar_sha256}"
            )

    if expected_seed_manifest_sha256:
        actual_man_sha = sha256_file(seed_man_p)
        if actual_man_sha.lower() != expected_seed_manifest_sha256.lower():
            raise ValueError(
                f"SEED_MANIFEST_SHA_MISMATCH: {actual_man_sha} vs expected {expected_seed_manifest_sha256}"
            )

    parent_dir = target_run_root.parent
    parent_dir.mkdir(parents=True, exist_ok=True)

    staging_dir = Path(
        tempfile.mkdtemp(prefix=f".staging_{target_run_root.name}_", dir=parent_dir)
    )

    try:
        # Extract safely
        with tarfile.open(seed_tar_path, "r:gz") as tar:
            if hasattr(tarfile, "data_filter"):
                tar.extractall(path=staging_dir, filter="data")
            else:
                tar.extractall(path=staging_dir)

        # Verify internal vs external manifest byte-identity
        internal_manifest_p = staging_dir / "restart_seed_manifest.json"
        if not internal_manifest_p.exists():
            raise ValueError(
                f"Imported seed archive missing restart_seed_manifest.json in staging {staging_dir}"
            )

        internal_manifest_bytes = internal_manifest_p.read_bytes()
        if external_manifest_bytes != internal_manifest_bytes:
            raise ValueError(
                "EXTERNAL_INTERNAL_MANIFEST_MISMATCH: External seed manifest is not byte-identical to internal manifest"
            )

        seed_manifest = json.loads(internal_manifest_bytes.decode("utf-8"))

        # Verify source origin provenance fields in seed manifest
        validate_provenance_field(seed_manifest.get("source_head"), "source_head")
        validate_provenance_field(seed_manifest.get("source_tree"), "source_tree")
        validate_provenance_field(
            seed_manifest.get("source_manifest_sha256"),
            "source_manifest_sha256",
            is_64=True,
        )

        # Verify generator provenance fields in seed manifest
        validate_provenance_field(seed_manifest.get("generator_head"), "generator_head")
        validate_provenance_field(seed_manifest.get("generator_tree"), "generator_tree")
        validate_provenance_field(
            seed_manifest.get("generator_source_manifest_sha256"),
            "generator_source_manifest_sha256",
            is_64=True,
        )

        # Verify all manifested files exist and hashes match
        included = seed_manifest.get("included_files", [])
        included_rel_paths = set()
        for fref in included:
            rel = fref["relative_path"]
            included_rel_paths.add(rel)
            expected_sha = fref["sha256"]
            target_p = staging_dir / rel
            if not target_p.exists():
                raise ValueError(
                    f"SEED_TAMPERED: Missing manifested file in seed: {rel}"
                )
            actual_sha = sha256_file(target_p)
            if actual_sha.lower() != expected_sha.lower():
                raise ValueError(
                    f"SEED_TAMPERED: SHA256 mismatch for {rel}: actual={actual_sha} vs expected={expected_sha}"
                )

        # Verify exact member set matching: no extra unmanifested files
        extracted_files = set()
        for r, _, files in os.walk(staging_dir):
            for f in files:
                p = Path(r) / f
                rel_p = str(p.relative_to(staging_dir))
                if rel_p != "restart_seed_manifest.json":
                    extracted_files.add(rel_p)

        if extracted_files != included_rel_paths:
            missing = included_rel_paths - extracted_files
            extra = extracted_files - included_rel_paths
            raise ValueError(f"SEED_MEMBER_MISMATCH: missing={missing}, extra={extra}")

        # Ensure NO S2+ artifacts exist in staging semantically and parse all JSON
        for r, _, files in os.walk(staging_dir):
            for f in files:
                p = Path(r) / f
                rel_p = str(p.relative_to(staging_dir))
                if is_semantically_s2_plus(rel_p, p):
                    raise ValueError(
                        f"S2_PLUS_SEED_CONTAMINATION: S2+ file {rel_p} found in seed!"
                    )

        artifacts_dir = staging_dir / "artifacts"
        s1e_file = artifacts_dir / "S1e.json"
        if not s1e_file.exists():
            raise ValueError("Required S1e.json artifact missing in imported seed")

        s1e_data = json.loads(s1e_file.read_text(encoding="utf-8"))
        payload = (
            s1e_data.get("payload")
            if isinstance(s1e_data.get("payload"), dict)
            else s1e_data
        )

        raw_events: list[dict[str, Any]] = []
        if payload.get("s1e_output_path"):
            s1e_out_p = staging_dir / payload["s1e_output_path"]
            if not s1e_out_p.exists():
                s1e_out_p = staging_dir / "data" / Path(payload["s1e_output_path"]).name
            if s1e_out_p.exists():
                univ_data = json.loads(s1e_out_p.read_text(encoding="utf-8"))
                raw_events = (
                    univ_data.get("events") or univ_data.get("event_records") or []
                )

        if not raw_events:
            raw_recs = (
                payload.get("deduplicated_events") or payload.get("event_records") or []
            )
            for r in raw_recs:
                if isinstance(r, dict):
                    raw_events.append(r)

        source_s1e_count = seed_manifest.get("event_counts", {}).get(
            "s1e_canonical_universe", len(raw_events)
        )

        # Temporal import filter and runtime freshness timestamp selection
        if runtime_mode == "LIVE_SHADOW" or as_of_utc is None:
            point_in_time = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        else:
            point_in_time = as_of_utc

        ledger, active_events = revalidate_event_freshness(
            events=raw_events,
            as_of_utc=point_in_time,
            min_lead_seconds=min_lead_seconds,
        )

        active_count = len(active_events)
        terminalized_count = len(ledger) - active_count

        if active_count + terminalized_count != len(ledger) or len(ledger) != source_s1e_count:
            raise ValueError(
                f"EVENT_ACCOUNTING_MISMATCH: active ({active_count}) + terminalized ({terminalized_count}) = {len(ledger)} != required universe ({source_s1e_count})"
            )

        # Persist temporal_freshness_ledger.json with all event records
        freshness_ledger_path = staging_dir / "temporal_freshness_ledger.json"
        write_json_atomic(
            freshness_ledger_path,
            {
                "schema_version": 1,
                "artifact_type": "TEMPORAL_FRESHNESS_LEDGER_V1",
                "source_s1e_count": source_s1e_count,
                "revalidated_total_count": len(ledger),
                "active_for_s2_restart_count": active_count,
                "terminalized_count": terminalized_count,
                "as_of_utc": point_in_time,
                "events": ledger,
            },
        )

        # Write event_accounting_ledger.json for backward compatibility
        ledger_path = staging_dir / "event_accounting_ledger.json"
        write_json_atomic(
            ledger_path,
            {
                "source_s1e_count": source_s1e_count,
                "revalidated_total_count": len(ledger),
                "active_for_s2_restart_count": active_count,
                "terminalized_count": terminalized_count,
                "as_of_utc": point_in_time,
                "ledger": ledger,
            },
        )

        # Persist live event revalidation ledger
        reval_ledger_path = staging_dir / "live_event_revalidation_ledger.json"
        write_json_atomic(
            reval_ledger_path,
            {
                "schema_version": 1,
                "artifact_type": "LIVE_EVENT_REVALIDATION_LEDGER_V1",
                "revalidation_timestamp_utc": point_in_time,
                "total_revalidated": len(ledger),
                "active_count": active_count,
                "terminalized_count": terminalized_count,
                "revalidation_policy": "FAIL_CLOSED_LEAD_TIME",
                "revalidated_events": ledger,
            },
        )

        # Persist filtered active event universe
        active_eids = sorted(
            [
                str(e.get("canonical_event_id") or e.get("event_id"))
                for e in active_events
            ]
        )
        active_universe_path = staging_dir / "data" / "s1e_active_events.json"
        active_universe_path.parent.mkdir(parents=True, exist_ok=True)
        write_json_atomic(
            active_universe_path,
            {
                "source_s1e_count": source_s1e_count,
                "active_event_count": active_count,
                "canonical_event_ids": active_eids,
                "events": active_events,
            },
        )

        now_utc = datetime.now(UTC).isoformat().replace("+00:00", "Z")

        import_receipt = {
            "import_id": f"IMP-{target_run_id}",
            "imported_at_utc": now_utc,
            "source_lineage": {
                "source_run_id": seed_manifest.get("source_run_id"),
                "source_run_root": seed_manifest.get("source_run_root"),
                "source_head": seed_manifest.get("source_head"),
                "source_tree": seed_manifest.get("source_tree"),
                "source_manifest_sha256": seed_manifest.get("source_manifest_sha256"),
                "source_s1e_event_ids_sha256": seed_manifest.get(
                    "s1e_event_ids_sha256"
                ),
            },
            "target_lineage": {
                "target_run_id": target_run_id,
                "target_head": target_head,
                "target_tree": target_tree,
                "target_manifest": target_manifest,
            },
            "imported_event_count": source_s1e_count,
            "active_event_count": active_count,
            "terminalized_event_count": terminalized_count,
            "reused_s2_plus": False,
            "freshness_revalidation": {
                "total_revalidated": len(ledger),
                "fresh_active_count": active_count,
                "terminalized_stale_count": terminalized_count,
                "revalidation_policy": "FAIL_CLOSED_LEAD_TIME",
                "as_of_utc": point_in_time,
            },
            "status": "PASS",
        }

        import_receipt_json = json.dumps(import_receipt, sort_keys=True)
        import_receipt_hash = hashlib.sha256(
            import_receipt_json.encode("utf-8")
        ).hexdigest()
        import_receipt["import_receipt_hash"] = import_receipt_hash

        receipt_path = staging_dir / "import_s2_seed_receipt.json"
        write_json_atomic(receipt_path, import_receipt)

        # Atomic promotion of staging directory to target_run_root
        if target_run_root.exists():
            target_run_root.rmdir()
        staging_dir.rename(target_run_root)

        print(
            f"Successfully imported S2 restart seed into {target_run_root} (active {active_count}/{source_s1e_count} events)"
        )
        return import_receipt

    except Exception:
        if staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)
        raise


def main():
    p = argparse.ArgumentParser(
        description="Import S2 restart seed into target run root."
    )
    p.add_argument("--seed-tar", required=True, help="Path to seed tar archive")
    p.add_argument("--restart-seed-manifest", required=True, help="Path to external restart seed manifest")
    p.add_argument("--target-run-root", required=True, help="Path to target run root")
    p.add_argument("--target-run-id", required=True, help="Target run ID")
    p.add_argument("--target-head", required=True, help="Target HEAD SHA")
    p.add_argument("--target-tree", required=True, help="Target Tree SHA")
    p.add_argument(
        "--target-manifest", required=True, help="Target Source Manifest SHA256"
    )
    p.add_argument("--expected-seed-tar-sha256", help="Expected SHA256 of seed tar")
    p.add_argument(
        "--expected-seed-manifest-sha256", help="Expected SHA256 of seed manifest"
    )
    args = p.parse_args()

    import_s2_restart_seed(
        seed_tar_path=Path(args.seed_tar),
        target_run_root=Path(args.target_run_root),
        target_run_id=args.target_run_id,
        target_head=args.target_head,
        target_tree=args.target_tree,
        target_manifest=args.target_manifest,
        seed_manifest_path=Path(args.restart_seed_manifest),
        expected_seed_tar_sha256=args.expected_seed_tar_sha256,
        expected_seed_manifest_sha256=args.expected_seed_manifest_sha256,
    )


if __name__ == "__main__":
    main()
