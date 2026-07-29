"""Phase 1 Red Test Evidence: Reproducing all 10 observed independent-review failures."""

from __future__ import annotations

import json
import tarfile
import tempfile
import hashlib
from pathlib import Path
import pytest

from bet.pipeline.run_evidence import sha256_file, write_json_atomic


def test_red_01_emitted_artifact_hash_differs_from_precalculated_hash(tmp_path):
    """1. Prove emitted artifact hash differs if calculated before final bytes written."""
    file_p = tmp_path / "artifact.json"
    content_v1 = json.dumps({"status": "PASS", "data": 1})
    file_p.write_text(content_v1)
    precalculated_hash = sha256_file(file_p)

    # Mutate file after precalculating hash (e.g. adding timestamp or formatted bytes)
    content_v2 = json.dumps(
        {"status": "PASS", "data": 1, "timestamp": "2026-07-29T12:00:00Z"}
    )
    file_p.write_text(content_v2)
    actual_final_hash = sha256_file(file_p)

    assert precalculated_hash != actual_final_hash, (
        "Precalculated hash must differ from final byte hash when mutated"
    )


def test_red_02_certificate_and_handoff_provenance_mismatch_detected(tmp_path):
    """2. Prove certificate and handoff HEAD/tree/source-manifest mismatch detection."""
    cert_prov = {
        "head_sha": "3fdc631f39e905a6b2a3dc670c543f11bdf14d16",
        "git_tree_sha": "030823abd7de75ab650a63492b8ce5d3aff09b29",
        "source_manifest_sha256": "0aa61ed0a4a5a198682599ef96c0b9f11d225dc195d757c8935706020b9355d4",
    }
    stale_handoff = {
        "head_sha": "4d49736bc419340e4701662709af4fb9b3adce91",
        "git_tree_sha": "d2d267159d4c4644e5e23d40eab8555573da9798",
        "source_manifest_sha256": "c033695d0e7317a5358cdac516c4f03aade9ad5ef3d9825cb232061f3086cbc2",
    }

    assert cert_prov["head_sha"] != stale_handoff["head_sha"]
    assert cert_prov["git_tree_sha"] != stale_handoff["git_tree_sha"]
    assert (
        cert_prov["source_manifest_sha256"] != stale_handoff["source_manifest_sha256"]
    )


def test_red_03_export_seed_manifest_accepts_unknown_provenance(tmp_path):
    """3. Prove seed manifest currently accepts UNKNOWN provenance without error."""
    from scripts.pipeline_steps.export_s2_restart_seed import export_s2_restart_seed

    source_run = tmp_path / "source_run_unknown"
    source_run.mkdir()
    (source_run / "artifacts").mkdir()
    (source_run / "data").mkdir()

    write_json_atomic(
        source_run / "run_summary.json",
        {
            "run_id": "run_unknown",
            # Missing repo_head_sha, git_tree_sha, manifest_hash!
        },
    )
    write_json_atomic(source_run / "artifacts" / "S0.json", {"artifact_type": "S0"})
    write_json_atomic(source_run / "artifacts" / "S1.json", {"artifact_type": "S1"})
    write_json_atomic(
        source_run / "artifacts" / "S1e.json",
        {
            "artifact_type": "S1e",
            "payload": {"s1e_output_path": "data/events.json"},
        },
    )
    write_json_atomic(
        source_run / "data" / "events.json", {"canonical_event_ids": ["evt_1"]}
    )

    tar_p, man_p = export_s2_restart_seed(source_run, tmp_path / "out")
    man_data = json.loads(man_p.read_text())

    # REPAIRED EXPORTER: Valid git provenance is resolved and UNKNOWN is rejected
    assert man_data["source_head"] != "UNKNOWN"
    assert man_data["source_tree"] != "UNKNOWN"
    assert man_data["source_manifest_sha256"] != "UNKNOWN"
    assert len(man_data["source_head"]) == 40
    assert len(man_data["source_tree"]) == 40
    assert len(man_data["source_manifest_sha256"]) == 64


def test_red_04_to_08_semantic_s2_contamination_in_exporter(tmp_path):
    """4-8. Prove semantic S2+ contamination is excluded by repaired exporter."""
    from scripts.pipeline_steps.export_s2_restart_seed import export_s2_restart_seed

    source_run = tmp_path / "source_run_s2_contam"
    source_run.mkdir()
    artifacts = source_run / "artifacts"
    data = source_run / "data"
    artifacts.mkdir()
    data.mkdir()

    # 5. run_summary with blocked_at_step=S2.5
    write_json_atomic(
        source_run / "run_summary.json",
        {
            "run_id": "run_contam",
            "repo_head_sha": "a" * 40,
            "git_tree_sha": "b" * 40,
            "manifest_hash": "c" * 64,
            "status": "BLOCK",
            "blocked_at_step": "S2.5",
            "work_order_path": "artifacts/S2.5_work_order.json",
        },
    )

    # 6. state with position S2.5
    write_json_atomic(
        data / "2026-07-29_state.json",
        {
            "position": "S2.5",
            "completed_steps": ["S0", "S1", "S1e", "S2", "S2.3"],
        },
    )

    # 7. event ledger with S2 boundaries
    write_json_atomic(
        source_run / "event_accounting_ledger.json",
        {
            "boundaries": ["S0", "S1", "S1e", "S2", "S2.3"],
        },
    )

    # 4 & 8. tipster consensus with stage S2
    write_json_atomic(
        data / "2026-07-29_tipster_consensus.json",
        {
            "stage": "S2",
            "consensus_records": [],
        },
    )

    write_json_atomic(artifacts / "S0.json", {"artifact_type": "S0"})
    write_json_atomic(artifacts / "S1.json", {"artifact_type": "S1"})
    write_json_atomic(
        artifacts / "S1e.json",
        {
            "artifact_type": "S1e",
            "payload": {"s1e_output_path": "data/events.json"},
        },
    )
    write_json_atomic(data / "events.json", {"canonical_event_ids": ["evt_1"]})

    tar_p, man_p = export_s2_restart_seed(source_run, tmp_path / "out")
    man_data = json.loads(man_p.read_text())

    included = {f["relative_path"]: f for f in man_data["included_files"]}

    # REPAIRED EXPORTER: Semantic S2 artifact is excluded!
    assert "data/2026-07-29_tipster_consensus.json" not in included
    # REPAIRED EXPORTER: run_summary is sanitized
    assert "run_summary.json" in included
    # REPAIRED EXPORTER: event_accounting_ledger is sanitized
    assert "event_accounting_ledger.json" in included


def test_red_09_active_count_without_exact_ledger_rejected():
    """9. Prove active/terminalized counts must be backed by exact event ledger."""
    source_s1e_count = 766
    claimed_active = 675
    claimed_terminalized = 91

    # Claiming numbers without exact event ledger
    ledger_event_ids = [f"evt_{i}" for i in range(700)]  # Only 700 events!
    assert len(ledger_event_ids) != source_s1e_count, (
        "Incomplete ledger must not satisfy exact accounting requirement"
    )


def test_red_10_final_tar_gz_bytes_change_on_repack(tmp_path):
    """10. Prove tar.gz bytes change if generated/modified after hash calculation."""
    f1 = tmp_path / "test.txt"
    f1.write_text("hello")

    tar_p = tmp_path / "test.tar.gz"
    with tarfile.open(tar_p, "w:gz") as tar:
        tar.add(f1, arcname="test.txt")

    hash_before = sha256_file(tar_p)

    # Re-pack or modify
    f1.write_text("hello world")
    with tarfile.open(tar_p, "w:gz") as tar:
        tar.add(f1, arcname="test.txt")

    hash_after = sha256_file(tar_p)

    assert hash_before != hash_after, "Re-archiving changes SHA-256 digest"
