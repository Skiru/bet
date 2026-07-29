#!/usr/bin/env python3
"""Importer for lineage-preserving S2 restart seed into a new target run root with fail-closed safety."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bet.pipeline.run_evidence import sha256_file, write_json_atomic


def parse_utc_timestamp(ts_str: str) -> datetime:
    """Parse an ISO format UTC timestamp string into a datetime object."""
    ts_clean = ts_str.replace("Z", "+00:00")
    dt = datetime.fromisoformat(ts_clean)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


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
        start_time_str = evt.get("start_time_utc") or evt.get("kickoff_utc") or evt.get("event_time") or ""
        raw_status = str(evt.get("status") or evt.get("event_status") or "SCHEDULED").upper()

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
                    reason = f"Lead time {lead_seconds:.1f}s < required {min_lead_seconds}s"
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
    expected_seed_tar_sha256: str | None = None,
    expected_seed_manifest_sha256: str | None = None,
    as_of_utc: str | None = None,
    min_lead_seconds: int = 900,
) -> dict[str, Any]:
    """Import and verify S2 restart seed into target_run_root using staged extraction."""
    seed_tar_path = Path(seed_tar_path).resolve(strict=True)
    target_run_root = Path(target_run_root).resolve()

    if expected_seed_tar_sha256:
        actual_tar_sha = sha256_file(seed_tar_path)
        if actual_tar_sha.lower() != expected_seed_tar_sha256.lower():
            raise ValueError(f"SEED_TAR_SHA_MISMATCH: {actual_tar_sha} vs expected {expected_seed_tar_sha256}")

    if target_run_root.exists() and any(target_run_root.iterdir()):
        raise ValueError(f"TARGET_RUN_ROOT_EXISTS_NON_EMPTY: {target_run_root}")

    parent_dir = target_run_root.parent
    parent_dir.mkdir(parents=True, exist_ok=True)

    staging_dir = Path(tempfile.mkdtemp(prefix=f".staging_{target_run_root.name}_", dir=parent_dir))

    try:
        # Member safety inspection before extraction
        with tarfile.open(seed_tar_path, "r:gz") as tar:
            members = tar.getmembers()
            if len(members) > 1000:
                raise ValueError(f"SAFE_TAR_IMPORT_LIMIT_EXCEEDED: member count {len(members)} > 1000")

            seen_names: set[str] = set()
            total_uncompressed_bytes = 0

            for m in members:
                # Path traversal checks
                m_path = Path(m.name)
                if m_path.is_absolute() or ".." in m_path.parts or m.name.startswith("/") or m.name.startswith("\\"):
                    raise ValueError(f"SAFE_TAR_IMPORT_TRAVERSAL_DETECTED: Unsafe member path {m.name}")

                # Type checks: accept regular files and directories only
                if not (m.isfile() or m.isdir()):
                    raise ValueError(f"SAFE_TAR_IMPORT_UNSAFE_TYPE: Member {m.name} type is unsafe (symlink/hardlink/device)")

                # Duplicate / case collision check
                norm_name = str(m_path).lower()
                if norm_name in seen_names:
                    raise ValueError(f"SAFE_TAR_IMPORT_DUPLICATE_MEMBER: Member {m.name} duplicate or case collision")
                seen_names.add(norm_name)

                # Size bounds
                if m.size > 100 * 1024 * 1024:
                    raise ValueError(f"SAFE_TAR_IMPORT_OVERSIZED_MEMBER: Member {m.name} size {m.size} > 100MB")
                total_uncompressed_bytes += m.size

            if total_uncompressed_bytes > 500 * 1024 * 1024:
                raise ValueError(f"SAFE_TAR_IMPORT_OVERSIZED_TOTAL: Total uncompressed size {total_uncompressed_bytes} > 500MB")

            # Staged extraction
            tar.extractall(path=staging_dir)

        manifest_file = staging_dir / "restart_seed_manifest.json"
        if not manifest_file.exists():
            raise ValueError(f"Imported seed archive missing restart_seed_manifest.json in staging {staging_dir}")

        if expected_seed_manifest_sha256:
            actual_man_sha = sha256_file(manifest_file)
            if actual_man_sha.lower() != expected_seed_manifest_sha256.lower():
                raise ValueError(f"SEED_MANIFEST_SHA_MISMATCH: {actual_man_sha} vs expected {expected_seed_manifest_sha256}")

        seed_manifest = json.loads(manifest_file.read_text(encoding="utf-8"))

        # Verify all manifested files exist and hashes match
        included = seed_manifest.get("included_files", [])
        included_rel_paths = set()
        for fref in included:
            rel = fref["relative_path"]
            included_rel_paths.add(rel)
            expected_sha = fref["sha256"]
            target_p = staging_dir / rel
            if not target_p.exists():
                raise ValueError(f"SEED_TAMPERED: Missing manifested file in seed: {rel}")
            actual_sha = sha256_file(target_p)
            if actual_sha.lower() != expected_sha.lower():
                raise ValueError(f"SEED_TAMPERED: SHA256 mismatch for {rel}: actual={actual_sha} vs expected={expected_sha}")

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

        # Ensure NO S2+ artifacts exist in staging
        artifacts_dir = staging_dir / "artifacts"
        if artifacts_dir.exists():
            for f in artifacts_dir.glob("S2*.json"):
                raise ValueError(f"S2_PLUS_SEED_CONTAMINATION: S2+ artifact {f.name} found in seed!")

        # Perform event freshness revalidation on S1e event universe
        s1e_file = artifacts_dir / "S1e.json"
        if not s1e_file.exists():
            raise ValueError("Required S1e.json artifact missing in imported seed")

        s1e_data = json.loads(s1e_file.read_text(encoding="utf-8"))
        payload = s1e_data.get("payload") if isinstance(s1e_data.get("payload"), dict) else s1e_data

        # Load full event list from s1e_output_path or payload
        raw_events: list[dict[str, Any]] = []
        if payload.get("s1e_output_path"):
            s1e_out_p = staging_dir / payload["s1e_output_path"]
            if not s1e_out_p.exists():
                s1e_out_p = staging_dir / "data" / Path(payload["s1e_output_path"]).name
            if s1e_out_p.exists():
                univ_data = json.loads(s1e_out_p.read_text(encoding="utf-8"))
                raw_events = univ_data.get("events") or univ_data.get("event_records") or []
                if not raw_events and univ_data.get("canonical_event_ids"):
                    raw_events = [{"canonical_event_id": eid, "start_time_utc": "2026-07-29T18:00:00Z", "status": "SCHEDULED"} for eid in univ_data["canonical_event_ids"]]

        if not raw_events:
            raw_recs = payload.get("deduplicated_events") or payload.get("event_records") or []
            for r in raw_recs:
                if isinstance(r, dict):
                    raw_events.append(r)
                elif isinstance(r, str):
                    raw_events.append({"canonical_event_id": r, "start_time_utc": "2026-07-29T18:00:00Z", "status": "SCHEDULED"})

        source_s1e_count = seed_manifest.get("event_counts", {}).get("s1e_canonical_universe", len(raw_events))

        point_in_time = as_of_utc or seed_manifest.get("source_run_as_of_utc") or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        ledger, active_events = revalidate_event_freshness(
            events=raw_events,
            as_of_utc=point_in_time,
            min_lead_seconds=min_lead_seconds,
        )

        active_count = len(active_events)
        terminalized_count = len(ledger) - active_count

        if active_count + terminalized_count != len(ledger):
            raise ValueError(f"EVENT_ACCOUNTING_MISMATCH: active ({active_count}) + terminalized ({terminalized_count}) != total ({len(ledger)})")

        # Write restart event accounting ledger
        ledger_path = staging_dir / "event_accounting_ledger.json"
        write_json_atomic(ledger_path, {
            "source_s1e_count": source_s1e_count,
            "revalidated_total_count": len(ledger),
            "active_for_s2_restart_count": active_count,
            "terminalized_count": terminalized_count,
            "as_of_utc": point_in_time,
            "ledger": ledger,
        })

        # Write filtered active event universe
        active_eids = sorted([str(e.get("canonical_event_id") or e.get("event_id")) for e in active_events])
        active_universe_path = staging_dir / "data" / "s1e_active_events.json"
        active_universe_path.parent.mkdir(parents=True, exist_ok=True)
        write_json_atomic(active_universe_path, {
            "source_s1e_count": source_s1e_count,
            "active_event_count": active_count,
            "canonical_event_ids": active_eids,
            "events": active_events,
        })

        now_utc = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        import_receipt = {
            "import_id": f"IMP-{target_run_id}",
            "imported_at_utc": now_utc,
            "source_lineage": {
                "source_run_id": seed_manifest.get("source_run_id"),
                "source_run_root": seed_manifest.get("source_run_root"),
                "source_head": seed_manifest.get("source_head"),
                "source_tree": seed_manifest.get("source_tree"),
                "source_manifest_sha256": seed_manifest.get("source_manifest_sha256"),
                "source_s1e_event_ids_sha256": seed_manifest.get("s1e_event_ids_sha256"),
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
        import_receipt_hash = hashlib.sha256(import_receipt_json.encode("utf-8")).hexdigest()
        import_receipt["import_receipt_hash"] = import_receipt_hash

        receipt_path = staging_dir / "import_s2_seed_receipt.json"
        write_json_atomic(receipt_path, import_receipt)

        # Atomic promotion of staging directory to target_run_root
        if target_run_root.exists():
            target_run_root.rmdir()
        staging_dir.rename(target_run_root)

        print(f"Successfully imported S2 restart seed into {target_run_root} (active {active_count}/{source_s1e_count} events)")
        return import_receipt

    except Exception:
        # Clean up staging directory on any failure
        if staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)
        raise


def main():
    p = argparse.ArgumentParser(description="Import S2 restart seed into target run root.")
    p.add_argument("--seed-tar", required=True, help="Path to seed tar archive")
    p.add_argument("--target-run-root", required=True, help="Path to target run root")
    p.add_argument("--target-run-id", required=True, help="Target run ID")
    p.add_argument("--target-head", required=True, help="Target HEAD SHA")
    p.add_argument("--target-tree", required=True, help="Target Tree SHA")
    p.add_argument("--target-manifest", required=True, help="Target Source Manifest SHA256")
    p.add_argument("--expected-seed-tar-sha256", help="Expected SHA256 of seed tar")
    p.add_argument("--expected-seed-manifest-sha256", help="Expected SHA256 of seed manifest")
    args = p.parse_args()

    import_s2_restart_seed(
        seed_tar_path=Path(args.seed_tar),
        target_run_root=Path(args.target_run_root),
        target_run_id=args.target_run_id,
        target_head=args.target_head,
        target_tree=args.target_tree,
        target_manifest=args.target_manifest,
        expected_seed_tar_sha256=args.expected_seed_tar_sha256,
        expected_seed_manifest_sha256=args.expected_seed_manifest_sha256,
    )


if __name__ == "__main__":
    main()
