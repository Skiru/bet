"""Bounded execution, lease lock, and resume ledger contracts."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest

from bet.pipeline.run_coordination import (
    LeaseRunLock,
    ResumeLedger,
    ResumeLedgerError,
    RunLockError,
    run_bounded_process,
)


def test_bounded_process_times_out_and_kills_process_group(tmp_path: Path):
    child_pid_path = tmp_path / "child.pid"
    script = (
        "import pathlib,subprocess,sys,time;"
        "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']);"
        f"pathlib.Path({str(child_pid_path)!r}).write_text(str(p.pid));"
        "time.sleep(30)"
    )
    result = run_bounded_process([sys.executable, "-c", script], timeout_seconds=0.2)
    assert result.returncode == -124
    assert result.timed_out is True
    child_pid = int(child_pid_path.read_text())
    for _ in range(20):
        try:
            os.kill(child_pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.05)
    else:
        pytest.fail("timed-out child process remained alive")


def test_run_lock_conflict_and_token_safe_release(tmp_path: Path):
    first = LeaseRunLock(tmp_path, "run", lease_seconds=30)
    second = LeaseRunLock(tmp_path, "run", lease_seconds=30)
    first.acquire()
    with pytest.raises(RunLockError, match="RUN_LOCK_CONFLICT"):
        second.acquire()
    first.release()
    assert not first.path.exists()


def test_stale_lease_and_pid_identity_mismatch_are_recovered(tmp_path: Path):
    lock = LeaseRunLock(tmp_path, "run", lease_seconds=0.01)
    lock.acquire()
    owner = json.loads(lock.path.read_text())
    owner["heartbeat_epoch"] = time.time() - 10
    lock.path.write_text(json.dumps(owner), encoding="utf-8")
    lock.token = None
    recovered = LeaseRunLock(tmp_path, "run", lease_seconds=30)
    recovered.acquire()
    recovered.release()

    owner["heartbeat_epoch"] = time.time()
    owner["lease_seconds"] = 30
    owner["process_start_identity"] = "not-the-current-process"
    lock.path.write_text(json.dumps(owner), encoding="utf-8")
    recovered = LeaseRunLock(tmp_path, "run", lease_seconds=30)
    recovered.acquire()
    recovered.release()
    lines = [json.loads(line) for line in lock.audit_path.read_text().splitlines()]
    assert {line["reason"] for line in lines} == {"LEASE_EXPIRED", "OWNER_IDENTITY_STALE"}


def _ledger(tmp_path: Path) -> ResumeLedger:
    tmp_path.mkdir(parents=True, exist_ok=True)
    return ResumeLedger(
        tmp_path,
        run_id="run",
        betting_day="2026-07-13",
        main_sha="main-sha",
        manifest_sha="manifest-sha",
    )


def test_resume_ledger_is_hash_chained_and_idempotent(tmp_path: Path):
    ledger = _ledger(tmp_path)
    first = ledger.append(
        step_id="S1",
        status="PASS",
        command_request={"argv": ["discover"]},
        input_hashes={"input": "a"},
        output_hashes={"output": "b"},
    )
    repeated = ledger.append(
        step_id="S1",
        status="PASS",
        command_request={"argv": ["discover"]},
        input_hashes={"input": "a"},
        output_hashes={"output": "b"},
    )
    assert repeated == first
    payload = json.loads(ledger.path.read_text())
    assert len(payload["entries"]) == 1
    ResumeLedger.verify(payload)


def test_resume_ledger_blocks_conflict_invalid_predecessor_and_unresolved_request(tmp_path: Path):
    ledger = _ledger(tmp_path)
    first = ledger.append(
        step_id="S1",
        status="PASS",
        command_request={"argv": ["discover"]},
        input_hashes={"input": "a"},
        output_hashes={"output": "b"},
    )
    with pytest.raises(ResumeLedgerError, match="CONFLICTING_RERUN"):
        ledger.append(
            step_id="S1",
            status="BLOCK",
            command_request={"argv": ["discover"]},
            input_hashes={"input": "a"},
            output_hashes={},
        )
    with pytest.raises(ResumeLedgerError, match="INVALID_PREDECESSOR"):
        ledger.append(
            step_id="S2",
            status="PASS",
            command_request=None,
            input_hashes={},
            output_hashes={},
            expected_previous_hash="wrong",
        )
    ledger.append(
        step_id="S2.3",
        status="COMMAND_REQUEST_UNRESOLVED",
        command_request={"argv": ["python", "tool.py"]},
        input_hashes={"previous": first["entry_hash"]},
        output_hashes={},
    )
    with pytest.raises(ResumeLedgerError, match="UNRESOLVED_COMMAND_REQUEST"):
        ledger.assert_resumable()


def test_resume_ledger_rejects_cross_main_binding(tmp_path: Path):
    ledger = _ledger(tmp_path)
    ledger.append(
        step_id="S1",
        status="PASS",
        command_request=None,
        input_hashes={},
        output_hashes={},
    )
    conflicting = ResumeLedger(
        tmp_path,
        run_id="run",
        betting_day="2026-07-13",
        main_sha="different-main",
        manifest_sha="manifest-sha",
    )
    with pytest.raises(ResumeLedgerError, match="BINDING_CONFLICT"):
        conflicting.assert_resumable()
