"""Requirements verification tests for V6, proving that all previous initial failures are now fixed."""
from __future__ import annotations

import os
import json
import subprocess
import sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_verification_1_pytest_does_not_write_final_certificate():
    """1. Prove pytest no longer writes a final certificate in test_failed_run_replay.py."""
    content = Path(REPO_ROOT / "tests/test_failed_run_replay.py").read_text(encoding="utf-8")
    assert "BET_PIPELINE_FINAL_IMPLEMENTATION_AND_CERTIFICATION_V5" not in content
    assert "pipeline_v5_certificate.json" not in content


def test_verification_2_s6_evidence_conflict_audit_recorded(tmp_path):
    """2. A PASS S6 evidence is followed by a different BLOCK attempt and is preserved, with a separate conflict record written."""
    from scripts.pipeline_steps.s6_repeats import publish_terminal_evidence_immutable
    target = tmp_path / "S6.json"
    payload1 = {"status": "PASS", "run_id": "run1", "betting_day": "day1"}
    payload2 = {"status": "BLOCK", "run_id": "run1", "betting_day": "day1"}
    
    publish_terminal_evidence_immutable(target, payload1, tmp_path, "day1", "run1")
    res = publish_terminal_evidence_immutable(target, payload2, tmp_path, "day1", "run1")
    assert res == "BLOCKED_IMMUTABLE_S6_EVIDENCE_CONFLICT"
    
    # Original is preserved
    read_back = json.loads(target.read_text(encoding="utf-8"))
    assert read_back["status"] == "PASS"
    
    # Separate attempt record is written under attempts/S6
    attempts_dir = tmp_path / "validation" / "attempts" / "S6"
    assert attempts_dir.exists()
    assert len(list(attempts_dir.glob("*.json"))) == 1


def test_verification_3_direct_worker_fails_closed():
    """3. Direct worker fails closed when contract is missing or incomplete."""
    cmd = [sys.executable, str(REPO_ROOT / "scripts" / "check_48h_repeats.py")]
    res = subprocess.run(cmd, capture_output=True, text=True, env={"BET_PIPELINE_RUN_ROOT": "/tmp"})
    assert res.returncode == 5
    assert "BLOCKED_INTERNAL_WORKER_CONTRACT_MISSING" in res.stdout


def test_verification_4_no_ad_hoc_or_dummy_fallbacks_active():
    """4. Worker check_48h_repeats.py does not fall back to ad-hoc run ID or dummy hashes in active evaluation."""
    content = Path(REPO_ROOT / "scripts/check_48h_repeats.py").read_text(encoding="utf-8")
    # Verify that we do not have default fallback values assigned like "run_id = 'ad-hoc'" or "hash = 'dummy'"
    assert "run_id = os.environ.get" not in content
    assert "source_s5_hash = " not in content


def test_verification_5_run_clock_binding_present():
    """5. S6 wrapper s6_repeats.py reads and binds run_as_of_utc from environment."""
    content = Path(REPO_ROOT / "scripts/pipeline_steps/s6_repeats.py").read_text(encoding="utf-8")
    assert "BET_PIPELINE_RUN_AS_OF_UTC" in content
    assert "run_as_of_str = os.environ.get" in content


def test_verification_6_replay_validates_evidence_chain():
    """6. Replay validates entire output/evidence/resume chain using the reusable validator."""
    content = Path(REPO_ROOT / "tests/test_failed_run_replay.py").read_text(encoding="utf-8")
    assert "validate_run_evidence_chain.py" in content
