"""Bounded process execution, lease locking, and hash-chained resume state."""
from __future__ import annotations

import hashlib
import json
import os
import signal
import socket
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, IO

import psutil

from bet.pipeline.artifact_io import publish_run_artifact


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_hash(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _process_start_identity(pid: int) -> str | None:
    try:
        return f"{psutil.Process(pid).create_time():.6f}"
    except (psutil.NoSuchProcess, psutil.AccessDenied, ValueError):
        return None


@dataclass(frozen=True)
class BoundedProcessResult:
    returncode: int
    timed_out: bool
    stdout: str
    stderr: str


def run_bounded_process(
    argv: list[str],
    *,
    timeout_seconds: float,
    cwd: str | Path | None = None,
    env: dict[str, str] | None = None,
    stdout: IO[str] | int | None = subprocess.PIPE,
    stderr: IO[str] | int | None = subprocess.PIPE,
) -> BoundedProcessResult:
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    process = subprocess.Popen(
        argv,
        cwd=str(cwd) if cwd is not None else None,
        env=env,
        stdout=stdout,
        stderr=stderr,
        text=True,
        start_new_session=True,
    )
    try:
        captured_stdout, captured_stderr = process.communicate(timeout=timeout_seconds)
        return BoundedProcessResult(process.returncode, False, captured_stdout or "", captured_stderr or "")
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            captured_stdout, captured_stderr = process.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            captured_stdout, captured_stderr = process.communicate(timeout=2)
        return BoundedProcessResult(-124, True, captured_stdout or "", captured_stderr or "")


class RunLockError(RuntimeError):
    pass


class LeaseRunLock:
    def __init__(self, run_root: Path, run_id: str, *, lease_seconds: float = 60.0):
        self.run_root = Path(run_root)
        self.run_id = run_id
        self.lease_seconds = lease_seconds
        self.path = self.run_root / ".pipeline-run.lock"
        self.audit_path = self.run_root / "lock_recovery_audit.jsonl"
        self.token: str | None = None

    def _owner_alive(self, owner: dict[str, Any]) -> bool:
        pid = owner.get("pid")
        if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
            return False
        try:
            os.kill(pid, 0)
        except (ProcessLookupError, PermissionError):
            return False
        expected = owner.get("process_start_identity")
        return bool(expected and _process_start_identity(pid) == expected)

    def _expired(self, owner: dict[str, Any]) -> bool:
        heartbeat = owner.get("heartbeat_epoch")
        lease = owner.get("lease_seconds")
        if not isinstance(heartbeat, (int, float)) or not isinstance(lease, (int, float)):
            return True
        return time.time() - float(heartbeat) > float(lease)

    def _audit_recovery(self, owner: dict[str, Any], reason: str) -> None:
        record = {"recovered_at": _utc_now(), "reason": reason, "previous_owner": owner}
        with self.audit_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def acquire(self) -> dict[str, Any]:
        self.run_root.mkdir(parents=True, exist_ok=True)
        token = uuid.uuid4().hex
        owner = {
            "schema_version": 1,
            "token": token,
            "hostname": socket.gethostname(),
            "pid": os.getpid(),
            "process_start_identity": _process_start_identity(os.getpid()),
            "acquired_at": _utc_now(),
            "heartbeat_at": _utc_now(),
            "heartbeat_epoch": time.time(),
            "lease_seconds": self.lease_seconds,
            "run_id": self.run_id,
        }
        for _attempt in range(2):
            try:
                fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                try:
                    current = json.loads(self.path.read_text(encoding="utf-8"))
                except (OSError, ValueError, TypeError, json.JSONDecodeError):
                    current = {}
                if not self._expired(current) and self._owner_alive(current):
                    raise RunLockError("RUN_LOCK_CONFLICT")
                reason = "LEASE_EXPIRED" if self._expired(current) else "OWNER_IDENTITY_STALE"
                self._audit_recovery(current, reason)
                self.path.unlink(missing_ok=True)
                continue
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(owner, handle, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            self.token = token
            return owner
        raise RunLockError("RUN_LOCK_ACQUIRE_FAILED")

    def heartbeat(self) -> None:
        if self.token is None:
            raise RunLockError("RUN_LOCK_NOT_HELD")
        owner = json.loads(self.path.read_text(encoding="utf-8"))
        if owner.get("token") != self.token:
            raise RunLockError("RUN_LOCK_TOKEN_MISMATCH")
        owner["heartbeat_at"] = _utc_now()
        owner["heartbeat_epoch"] = time.time()
        self._replace_json(owner)

    def _replace_json(self, value: dict[str, Any]) -> None:
        fd, name = tempfile.mkstemp(dir=self.run_root, prefix=".lock.", suffix=".tmp")
        temporary = Path(name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(value, handle, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)

    def release(self) -> None:
        if self.token is None:
            return
        try:
            owner = json.loads(self.path.read_text(encoding="utf-8"))
            if owner.get("token") != self.token:
                raise RunLockError("RUN_LOCK_TOKEN_MISMATCH")
            self.path.unlink()
        finally:
            self.token = None

    def __enter__(self) -> "LeaseRunLock":
        self.acquire()
        return self

    def __exit__(self, _exc_type: object, _exc: object, _tb: object) -> None:
        self.release()


class ResumeLedgerError(RuntimeError):
    pass


class ResumeLedger:
    def __init__(self, run_root: Path, *, run_id: str, betting_day: str, main_sha: str, manifest_sha: str):
        self.run_root = Path(run_root)
        self.path = self.run_root / "resume_ledger.json"
        self.binding = {
            "run_id": run_id,
            "betting_day": betting_day,
            "main_sha": main_sha,
            "manifest_sha": manifest_sha,
        }

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {
                "schema_version": 1,
                "artifact_type": "RUN_RESUME_LEDGER",
                **self.binding,
                "entries": [],
                "ledger_hash_chain_valid": True,
            }
        ledger = json.loads(self.path.read_text(encoding="utf-8"))
        if any(ledger.get(key) != value for key, value in self.binding.items()):
            raise ResumeLedgerError("RESUME_LEDGER_BINDING_CONFLICT")
        self.verify(ledger)
        return ledger

    @staticmethod
    def verify(ledger: dict[str, Any]) -> None:
        previous: str | None = None
        for entry in ledger.get("entries", []):
            if entry.get("previous_hash") != previous:
                raise ResumeLedgerError("RESUME_LEDGER_INVALID_PREDECESSOR")
            candidate = dict(entry)
            actual = candidate.pop("entry_hash", None)
            if actual != _canonical_hash(candidate):
                raise ResumeLedgerError("RESUME_LEDGER_HASH_INVALID")
            previous = actual

    def append(
        self,
        *,
        step_id: str,
        status: str,
        command_request: object,
        input_hashes: dict[str, str],
        output_hashes: dict[str, str],
        expected_previous_hash: str | None = None,
    ) -> dict[str, Any]:
        ledger = self._load()
        entries = ledger["entries"]
        previous = entries[-1]["entry_hash"] if entries else None
        if expected_previous_hash is not None and expected_previous_hash != previous:
            raise ResumeLedgerError("RESUME_LEDGER_INVALID_PREDECESSOR")
        request_hash = _canonical_hash(command_request)
        signature = (step_id, request_hash, input_hashes)
        for existing in entries:
            if (existing["step_id"], existing["command_request_hash"], existing["input_hashes"]) == signature:
                if existing["status"] == status and existing["output_hashes"] == output_hashes:
                    return existing
                raise ResumeLedgerError("RESUME_LEDGER_CONFLICTING_RERUN")
        entry = {
            "attempt_id": uuid.uuid4().hex,
            "step_id": step_id,
            "status": status,
            "recorded_at": _utc_now(),
            "input_hashes": dict(sorted(input_hashes.items())),
            "output_hashes": dict(sorted(output_hashes.items())),
            "command_request_hash": request_hash,
            "previous_hash": previous,
        }
        entry["entry_hash"] = _canonical_hash(entry)
        entries.append(entry)
        ledger["unresolved_command_request"] = status == "COMMAND_REQUEST_UNRESOLVED"
        publish_run_artifact(
            run_root=self.run_root,
            target=self.path,
            payload=ledger,
            betting_day=self.binding["betting_day"],
            run_id=self.binding["run_id"],
            artifact_type="RUN_RESUME_LEDGER",
            immutable=False,
        )
        return entry

    def assert_resumable(self) -> None:
        if self._load().get("unresolved_command_request") is True:
            raise ResumeLedgerError("RESUME_BLOCKED_UNRESOLVED_COMMAND_REQUEST")
