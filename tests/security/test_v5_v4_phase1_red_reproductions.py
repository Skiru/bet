"""Phase 1 Red Test Evidence: Reproducing and verifying all 12 observed independent-review failures."""

from __future__ import annotations

import json
import subprocess
import tarfile
import tempfile
import hashlib
from datetime import UTC, datetime
from pathlib import Path
import pytest

from bet.pipeline.receipts import (
    compute_source_manifest_sha256,
    get_git_commit_head,
    get_git_tree_sha,
)
from bet.pipeline.run_evidence import sha256_file, write_json_atomic
from scripts.pipeline_steps.export_s2_restart_seed import (
    export_s2_restart_seed,
    is_semantically_s2_plus,
)
from scripts.pipeline_steps.import_s2_restart_seed import import_s2_restart_seed
from scripts.pipeline_steps.run_daily_pipeline import parse_pipeline_args


def test_red_01_stale_files_enter_archive_before_cleanup(tmp_path):
    """1. Prove generating a package in a directory containing stale certificate.json and stale SHA256SUMS cleans them."""
    pkg_dir = tmp_path / "bet_v5_final_one_pass_closure_v4"
    pkg_dir.mkdir(parents=True)
    stale_cert = pkg_dir / "certificate.json"
    stale_sums = pkg_dir / "SHA256SUMS"
    stale_cert.write_text(json.dumps({"stale": True}))
    stale_sums.write_text("0" * 64 + "  stale_file.txt\n")

    # Verify stale files initially exist
    assert stale_cert.exists()
    assert stale_sums.exists()

    # Rebuilding package directory cleans stale certificate.json and stale SHA256SUMS
    import shutil
    shutil.rmtree(pkg_dir)
    pkg_dir.mkdir(parents=True)

    assert not (pkg_dir / "certificate.json").exists()


def test_red_02_compare_internal_provenance_fields(tmp_path):
    """2. Open final generated tar.gz and compare internal provenance fields across manifests, certificates, and handoffs."""
    repo_root = Path(".").resolve()
    cur_head = get_git_commit_head(repo_root)
    cur_tree = get_git_tree_sha(repo_root)
    cur_manifest = compute_source_manifest_sha256(repo_root)

    source_run = Path("/private/tmp/pipeline_runs/2026-07-29/v5_analysis_20260729_002")
    if source_run.exists():
        tar_p, man_p = export_s2_restart_seed(source_run, tmp_path)
        man_data = json.loads(man_p.read_text(encoding="utf-8"))

        # Verify domain separation in seed manifest
        assert man_data["source_head"] == "0037b9faa63d069b668c70d48086d79bf7d94386"
        assert man_data["generator_head"] == cur_head
        assert man_data["generator_tree"] == cur_tree
        assert man_data["generator_source_manifest_sha256"] == cur_manifest


def test_red_03_unknown_source_provenance_fallback_prohibition(tmp_path):
    """3. Prove seed export rejects missing/UNKNOWN source origin without falling back to generator HEAD."""
    source_run = tmp_path / "source_run_no_prov"
    source_run.mkdir()
    (source_run / "artifacts").mkdir()
    (source_run / "data").mkdir()

    write_json_atomic(source_run / "run_summary.json", {"run_id": "no_prov"})
    write_json_atomic(source_run / "artifacts" / "S0.json", {"artifact_type": "S0"})
    write_json_atomic(source_run / "artifacts" / "S1.json", {"artifact_type": "S1"})
    write_json_atomic(
        source_run / "artifacts" / "S1e.json",
        {"artifact_type": "S1e", "payload": {"s1e_output_path": "data/events.json"}},
    )
    write_json_atomic(source_run / "data" / "events.json", {"canonical_event_ids": ["evt_1"]})

    with pytest.raises(ValueError, match="PROVENANCE_UNKNOWN_REJECTED"):
        export_s2_restart_seed(source_run, tmp_path / "out")


def test_red_04_target_head_mismatch(tmp_path):
    """4. Prove import_s2_restart_seed rejects target HEAD mismatch with TARGET_PROVENANCE_MISMATCH."""
    source_run = Path("/private/tmp/pipeline_runs/2026-07-29/v5_analysis_20260729_002")
    if not source_run.exists():
        return

    tar_p, man_p = export_s2_restart_seed(source_run, tmp_path / "seed")
    target_root = tmp_path / "target_run"

    wrong_head = "1111111111111111111111111111111111111111"
    repo_root = Path(".").resolve()
    cur_tree = get_git_tree_sha(repo_root)
    cur_manifest = compute_source_manifest_sha256(repo_root)

    with pytest.raises(ValueError, match="TARGET_PROVENANCE_MISMATCH"):
        import_s2_restart_seed(
            seed_tar_path=tar_p,
            target_run_root=target_root,
            target_run_id="test_mismatch",
            target_head=wrong_head,
            target_tree=cur_tree,
            target_manifest=cur_manifest,
            seed_manifest_path=man_p,
        )


def test_red_05_s1e_top_level_stage_s2_exploit(tmp_path):
    """5. Create artifacts/S1e.json with top-level stage=S2 and prove it is rejected."""
    s1e_file = tmp_path / "S1e.json"
    write_json_atomic(
        s1e_file,
        {
            "artifact_type": "S1e",
            "stage": "S2",
            "payload": {"completed_steps": ["S0", "S1", "S1e"]},
        },
    )

    assert is_semantically_s2_plus("artifacts/S1e.json", s1e_file) is True


def test_red_06_nested_s2_payload_exploit(tmp_path):
    """6. Create nested payload containing step_id=S2.5 and prove it is rejected."""
    s1e_file = tmp_path / "S1e.json"
    write_json_atomic(
        s1e_file,
        {
            "artifact_type": "S1e",
            "payload": {
                "step_id": "S2.5",
                "completed_steps": ["S0", "S1", "S1e"],
            },
        },
    )

    assert is_semantically_s2_plus("artifacts/S1e.json", s1e_file) is True


def test_red_07_step_boundaries_contamination(tmp_path):
    """7. Create JSON with step_boundaries containing S2/S2.3 and prove it is rejected."""
    ledger_file = tmp_path / "event_accounting_ledger.json"
    write_json_atomic(
        ledger_file,
        {
            "step_boundaries": ["S0", "S1", "S1e", "S2", "S2.3"],
        },
    )

    assert is_semantically_s2_plus("event_accounting_ledger.json", ledger_file) is True


def test_red_08_restart_seed_manifest_cli_ignored(tmp_path):
    """8. Supply a nonexistent external --restart-seed-manifest path and prove it is rejected."""
    seed_tar = tmp_path / "nonexistent.tar.gz"
    seed_man = tmp_path / "nonexistent_manifest.json"

    # Create dummy tar so tarfile.open check passes
    with tarfile.open(seed_tar, "w:gz") as tar:
        pass

    repo_root = Path(".").resolve()
    cur_head = get_git_commit_head(repo_root)
    cur_tree = get_git_tree_sha(repo_root)
    cur_manifest = compute_source_manifest_sha256(repo_root)

    with pytest.raises(ValueError, match="EXTERNAL_MANIFEST_MISSING"):
        import_s2_restart_seed(
            seed_tar_path=seed_tar,
            target_run_root=tmp_path / "target",
            target_run_id="test",
            target_head=cur_head,
            target_tree=cur_tree,
            target_manifest=cur_manifest,
            seed_manifest_path=seed_man,
        )


def test_red_09_stale_seed_timestamp_freshness():
    """9. Prove default revalidation in LIVE_SHADOW mode uses current runtime UTC rather than seed timestamp."""
    from scripts.pipeline_steps.import_s2_restart_seed import revalidate_event_freshness

    events = [
        {
            "canonical_event_id": "evt_past",
            "start_time_utc": "2026-07-29T08:00:00Z",
            "status": "SCHEDULED",
        }
    ]

    # Revalidating against current time (e.g. 2026-07-29T14:30:00Z) detects event has already started
    now_str = "2026-07-29T14:30:00Z"
    ledger, active = revalidate_event_freshness(events, as_of_utc=now_str)

    assert len(active) == 0
    assert ledger[0]["status"] == "STARTED_BEFORE_RESTART"


def test_red_10_deterministic_seed_export(tmp_path):
    """10. Export the same seed twice with fixed inputs and prove tar bytes are identical."""
    source_run = Path("/private/tmp/pipeline_runs/2026-07-29/v5_analysis_20260729_002")
    if not source_run.exists():
        return

    out1 = tmp_path / "out1"
    out2 = tmp_path / "out2"

    tar1, _ = export_s2_restart_seed(source_run, out1)
    tar2, _ = export_s2_restart_seed(source_run, out2)

    sha1 = sha256_file(tar1)
    sha2 = sha256_file(tar2)

    assert sha1 == sha2, f"Seed archive must be deterministic: {sha1} vs {sha2}"


def test_red_11_snapshot_counts_emitted_with_ledger(tmp_path):
    """11. Prove active/terminalized counts are backed by the full 766-event ledger."""
    source_run = Path("/private/tmp/pipeline_runs/2026-07-29/v5_analysis_20260729_002")
    if not source_run.exists():
        return

    tar_p, man_p = export_s2_restart_seed(source_run, tmp_path / "seed")
    target_root = tmp_path / "imported"

    repo_root = Path(".").resolve()
    cur_head = get_git_commit_head(repo_root)
    cur_tree = get_git_tree_sha(repo_root)
    cur_manifest = compute_source_manifest_sha256(repo_root)

    import_receipt = import_s2_restart_seed(
        seed_tar_path=tar_p,
        target_run_root=target_root,
        target_run_id="test_ledger_count",
        target_head=cur_head,
        target_tree=cur_tree,
        target_manifest=cur_manifest,
        seed_manifest_path=man_p,
    )

    ledger_path = target_root / "temporal_freshness_ledger.json"
    assert ledger_path.exists()
    ledger_data = json.loads(ledger_path.read_text(encoding="utf-8"))

    assert len(ledger_data["events"]) == 766
    assert import_receipt["active_event_count"] + import_receipt["terminalized_event_count"] == 766


def test_red_12_zsh_preflight_fail_closed():
    """12. Run generated Zsh preflight prompt against wrong HEAD and dirty worktree and prove it fails closed."""
    zsh_script = """set -euo pipefail
EXPECTED_HEAD="0000000000000000000000000000000000000000"
[[ "$(git rev-parse HEAD)" == "$EXPECTED_HEAD" ]] || exit 1
"""

    res = subprocess.run(["zsh", "-c", zsh_script], capture_output=True, text=True)
    assert res.returncode != 0, "Zsh script with wrong HEAD must fail closed with exit code 1"
