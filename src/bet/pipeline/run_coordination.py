"""Bounded process execution, lease locking, and hash-chained resume state."""
from __future__ import annotations

import hashlib
import json
import os
import signal
import socket
import subprocess
import tempfile
import threading
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
        pass

    # Some container runtimes expose namespace-local PIDs to ``getpid`` and
    # host PIDs in the mounted /proc.  Resolve NSpid explicitly so a live lock
    # cannot be mistaken for a dead owner merely because psutil cannot bridge
    # those namespaces.
    proc = Path("/proc")
    try:
        boot_id = (proc / "sys/kernel/random/boot_id").read_text(encoding="ascii").strip()
        for status_path in proc.glob("[0-9]*/status"):
            status = status_path.read_text(encoding="utf-8", errors="replace")
            namespace_line = next(
                (line for line in status.splitlines() if line.startswith("NSpid:")),
                "",
            )
            namespace_pids = namespace_line.partition(":")[2].split()
            if not namespace_pids or int(namespace_pids[-1]) != pid:
                continue
            stat = (status_path.parent / "stat").read_text(encoding="ascii")
            fields_from_state = stat.rsplit(") ", 1)[1].split()
            start_ticks = fields_from_state[19]  # proc(5) field 22
            return f"linux:{boot_id}:{status_path.parent.name}:{start_ticks}"
    except (OSError, StopIteration, ValueError, IndexError):
        return None
    return None


@dataclass(frozen=True)
class BoundedProcessResult:
    returncode: int
    timed_out: bool
    stdout: str
    stderr: str


def redact_sensitive_text(text: str, env: dict[str, str], *, max_chars: int = 1_000_000) -> str:
    """Redact credential-shaped environment values and bound captured output."""
    redacted = str(text or "")
    secret_tokens = ("key", "secret", "token", "password", "credential", "authorization", "auth")
    for name, value in env.items():
        if value and len(value) >= 4 and any(token in name.casefold() for token in secret_tokens):
            redacted = redacted.replace(value, "[REDACTED]")
    if len(redacted) > max_chars:
        redacted = redacted[:max_chars] + "\n[OUTPUT_TRUNCATED]\n"
    return redacted


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
        self._heartbeat_stop: threading.Event | None = None
        self._heartbeat_thread: threading.Thread | None = None
        self._heartbeat_error: BaseException | None = None

    def _owner_alive(self, owner: dict[str, Any]) -> bool:
        pid = owner.get("pid")
        if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
            return False
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            # EPERM proves that a process occupies the PID; identity matching
            # below still protects against PID reuse.
            pass
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
        process_identity = _process_start_identity(os.getpid())
        if not process_identity:
            raise RunLockError("RUN_LOCK_IDENTITY_UNAVAILABLE")
        owner = {
            "schema_version": 1,
            "token": token,
            "hostname": socket.gethostname(),
            "pid": os.getpid(),
            "process_start_identity": process_identity,
            "acquired_at": _utc_now(),
            "heartbeat_at": _utc_now(),
            "heartbeat_epoch": time.time(),
            "lease_seconds": self.lease_seconds,
            "run_id": self.run_id,
        }
        for _attempt in range(8):
            try:
                fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                try:
                    current = json.loads(self.path.read_text(encoding="utf-8"))
                except (OSError, ValueError, TypeError, json.JSONDecodeError):
                    current = {}
                if self._owner_alive(current):
                    raise RunLockError("RUN_LOCK_CONFLICT")
                reason = "LEASE_EXPIRED" if self._expired(current) else "OWNER_IDENTITY_STALE"
                try:
                    latest = json.loads(self.path.read_text(encoding="utf-8"))
                except (OSError, ValueError, TypeError, json.JSONDecodeError):
                    latest = {}
                if latest.get("token") != current.get("token"):
                    continue
                self._audit_recovery(current, reason)
                try:
                    self.path.unlink()
                except FileNotFoundError:
                    continue
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

    def check_health(self) -> None:
        """Check lock heartbeat health."""
        if self._heartbeat_error is not None:
            raise RunLockError(f"RUN_LOCK_HEARTBEAT_FAILED: {self._heartbeat_error}") from self._heartbeat_error

    def release(self) -> None:
        self._stop_heartbeat()
        hb_error = self._heartbeat_error
        self._heartbeat_error = None

        if self.token is None:
            if hb_error:
                raise RunLockError(f"RUN_LOCK_HEARTBEAT_FAILED: {hb_error}") from hb_error
            return
        try:
            owner = json.loads(self.path.read_text(encoding="utf-8"))
            if owner.get("token") != self.token:
                raise RunLockError("RUN_LOCK_TOKEN_MISMATCH")
            self.path.unlink()
        finally:
            self.token = None

        if hb_error:
            raise RunLockError(f"RUN_LOCK_HEARTBEAT_FAILED: {hb_error}") from hb_error

    def __enter__(self) -> "LeaseRunLock":
        self.acquire()
        self._start_heartbeat()
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc_val: BaseException | None, tb: object) -> None:
        try:
            self.release()
        except BaseException as lock_exc:
            if exc_val is not None:
                if hasattr(exc_val, "add_note"):
                    exc_val.add_note(f"Lock release failed: {lock_exc}")
                else:
                    exc_val.__context__ = lock_exc
            else:
                raise

    def _start_heartbeat(self) -> None:
        if self._heartbeat_thread is not None:
            return
        self._heartbeat_stop = threading.Event()
        interval = max(0.1, min(self.lease_seconds / 3.0, 10.0))

        def renew() -> None:
            assert self._heartbeat_stop is not None
            while not self._heartbeat_stop.wait(interval):
                try:
                    self.heartbeat()
                except BaseException as exc:  # retained and surfaced on release
                    self._heartbeat_error = exc
                    return

        self._heartbeat_thread = threading.Thread(
            target=renew,
            name=f"pipeline-lock-heartbeat-{self.run_id}",
            daemon=True,
        )
        self._heartbeat_thread.start()

    def _stop_heartbeat(self) -> None:
        if self._heartbeat_stop is not None:
            self._heartbeat_stop.set()
        if self._heartbeat_thread is not None:
            self._heartbeat_thread.join(timeout=max(1.0, min(self.lease_seconds, 5.0)))
        self._heartbeat_stop = None
        self._heartbeat_thread = None


class ResumeLedgerError(RuntimeError):
    pass


class ResumeLedger:
    def __init__(self, run_root: Path, *, run_id: str, betting_day: str, main_sha: str, manifest_sha: str, run_as_of_utc: str | None = None):
        self.run_root = Path(run_root)
        self.path = self.run_root / "resume_ledger.json"

        # Determine the canonical run_as_of_utc as of REQ-V6-CLOCK-001
        env_val = os.environ.get("BET_PIPELINE_RUN_AS_OF_UTC")
        file_val = None
        if self.path.exists():
            try:
                ledger_data = json.loads(self.path.read_text(encoding="utf-8"))
                file_val = ledger_data.get("run_as_of_utc")
            except Exception:
                pass

        resolved_as_of = run_as_of_utc or env_val or file_val

        if not resolved_as_of:
            if not self.path.exists():
                from datetime import datetime, timezone
                resolved_as_of = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
            else:
                raise ResumeLedgerError("BLOCKED_RUN_AS_OF_BINDING_MISMATCH")

        if file_val and file_val != resolved_as_of:
            raise ResumeLedgerError("BLOCKED_RUN_AS_OF_BINDING_MISMATCH")

        if env_val and env_val != resolved_as_of:
            raise ResumeLedgerError("BLOCKED_RUN_AS_OF_BINDING_MISMATCH")

        self.binding = {
            "run_id": run_id,
            "betting_day": betting_day,
            "main_sha": main_sha,
            "manifest_sha": manifest_sha,
            "run_as_of_utc": resolved_as_of,
        }

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            ledger = {
                "schema_version": 1,
                "artifact_type": "RUN_RESUME_LEDGER",
                **self.binding,
                "entries": [],
                "ledger_hash_chain_valid": True,
            }
            self.run_root.mkdir(parents=True, exist_ok=True)
            publish_run_artifact(
                run_root=self.run_root,
                target=self.path,
                payload=ledger,
                betting_day=self.binding["betting_day"],
                run_id=self.binding["run_id"],
                artifact_type="RUN_RESUME_LEDGER",
                immutable=False,
            )
            return ledger
        ledger = json.loads(self.path.read_text(encoding="utf-8"))
        mismatched = [
            key for key, value in self.binding.items()
            if ledger.get(key) != value
        ]
        if mismatched:
            raise ResumeLedgerError(
                "RESUME_LEDGER_BINDING_CONFLICT:" + ",".join(sorted(mismatched))
            )
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
        normalized_inputs = dict(sorted(input_hashes.items()))
        normalized_outputs = dict(sorted(output_hashes.items()))
        signature = (step_id, request_hash, normalized_inputs)
        LEGAL_TRANSITIONS = {
            "WAITING_FOR_AGENT_ARTIFACT": {"PASS", "AGENT_ARTIFACT_BLOCK", "COMMAND_REQUEST_PENDING", "NO_ACTION_TERMINAL"},
            "COMMAND_REQUEST_PENDING": {"PASS", "COMMAND_REQUEST_UNRESOLVED", "NO_ACTION_TERMINAL"},
            "COMMAND_REQUEST_UNRESOLVED": {"PASS", "AGENT_ARTIFACT_BLOCK", "COMMAND_REQUEST_PENDING", "NO_ACTION_TERMINAL"},
            "AGENT_ARTIFACT_BLOCK": {"PASS", "COMMAND_REQUEST_PENDING", "NO_ACTION_TERMINAL"},
        }

        existing_entry = None
        for entry in reversed(entries):
            if entry.get("step_id") == step_id:
                existing_entry = entry
                break

        resolution_of_attempt_id: str | None = None
        if existing_entry:
            old_status = existing_entry.get("status")
            if old_status == status:
                if (
                    existing_entry.get("command_request_hash") == request_hash
                    and existing_entry.get("input_hashes") == normalized_inputs
                ):
                    if existing_entry.get("output_hashes") == normalized_outputs:
                        return existing_entry
                    else:
                        raise ResumeLedgerError("RESUME_LEDGER_CONFLICTING_RERUN")
            else:
                allowed = LEGAL_TRANSITIONS.get(old_status, set())
                if old_status == "BLOCK":
                    allowed = {"PASS", "NO_ACTION_TERMINAL", "BLOCK"}

                if status not in allowed:
                    raise ResumeLedgerError("RESUME_LEDGER_CONFLICTING_RERUN")

                resolution_of_attempt_id = str(existing_entry["attempt_id"])

        entry = {
            "attempt_id": uuid.uuid4().hex,
            "step_id": step_id,
            "status": status,
            "recorded_at": _utc_now(),
            "input_hashes": normalized_inputs,
            "output_hashes": normalized_outputs,
            "command_request_hash": request_hash,
            "previous_hash": previous,
        }
        if resolution_of_attempt_id:
            entry["resolution_of_attempt_id"] = resolution_of_attempt_id
        entry["entry_hash"] = _canonical_hash(entry)
        entries.append(entry)
        resolved_attempts = {
            str(item.get("resolution_of_attempt_id"))
            for item in entries
            if item.get("resolution_of_attempt_id")
        }
        ledger["unresolved_command_request"] = any(
            item.get("status") in {"COMMAND_REQUEST_UNRESOLVED", "COMMAND_REQUEST_PENDING"}
            and str(item.get("attempt_id")) not in resolved_attempts
            for item in entries
        )
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

    def assert_resumable(self, start_step: str | None = None) -> None:
        # An unresolved request is a recorded non-terminal attempt, not a
        # permanent run tombstone. The same step may resume and must append a
        # hash-linked resolution; downstream steps remain blocked by normal
        # step ordering until that happens.
        ledger = self._load()
        if ledger.get("unresolved_command_request") is True:
            entries = ledger.get("entries", [])
            resolved_attempts = {
                str(item.get("resolution_of_attempt_id"))
                for item in entries
                if item.get("resolution_of_attempt_id")
            }
            unresolved_step = None
            for item in entries:
                if (
                    item.get("status") in {"COMMAND_REQUEST_UNRESOLVED", "COMMAND_REQUEST_PENDING"}
                    and str(item.get("attempt_id")) not in resolved_attempts
                ):
                    unresolved_step = item.get("step_id")
                    break

            if unresolved_step:
                if start_step == unresolved_step:
                    return
                raise ResumeLedgerError("BLOCKED_UNRESOLVED_COMMAND_REQUEST")
