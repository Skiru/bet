"""Typed LIVE_ANALYSIS_SHADOW runtime context, environment, and DB policy."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Iterable

from bet.pipeline.runtime_modes import (
    LIVE_ACK_KEY,
    LIVE_ACK_VALUE,
    RUNTIME_MODE_CONTRACT_VERSION,
    RuntimeMode,
    parse_runtime_mode,
    runtime_mode_capabilities,
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_RUNTIME_ENV_PREFIX = "BET_PIPELINE_"


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode()


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256(path.read_bytes())


def _resolved_within(path: Path, root: Path) -> Path:
    resolved = path.resolve(strict=False)
    try:
        resolved.relative_to(root.resolve(strict=False))
    except ValueError as exc:
        raise ValueError("CONTEXT_PATH_OUTSIDE_RUN_ROOT") from exc
    return resolved


@dataclass(frozen=True)
class RuntimeExecutionContext:
    runtime_mode: RuntimeMode
    runtime_mode_contract_version: str
    run_id: str
    run_root: Path
    plan_id: str
    plan_checkpoint_path: Path
    plan_checkpoint_sha256: str
    shadow_db_path: Path
    shadow_db_identity: str
    selection_run_id: str
    selection_ledger_path: Path
    selection_ledger_sha256: str
    runtime_s1e_path: Path
    runtime_s1e_sha256: str
    betting_date: str
    timezone_name: str = "Europe/Warsaw"

    def __post_init__(self) -> None:
        if self.runtime_mode is not RuntimeMode.LIVE_ANALYSIS_SHADOW:
            raise ValueError("RUNTIME_CONTEXT_MODE_NOT_LIVE_ANALYSIS_SHADOW")
        if not _ID_RE.fullmatch(self.run_id) or not _ID_RE.fullmatch(self.plan_id):
            raise ValueError("RUNTIME_CONTEXT_ID_INVALID")
        if self.selection_run_id != self.run_id:
            raise ValueError("RUNTIME_CONTEXT_SELECTION_RUN_MISMATCH")
        root = Path(self.run_root).resolve(strict=False)
        for path in (
            self.plan_checkpoint_path,
            self.shadow_db_path,
            self.selection_ledger_path,
            self.runtime_s1e_path,
        ):
            _resolved_within(Path(path), root)
        if Path(self.shadow_db_path).is_symlink():
            raise ValueError("SHADOW_PATH_SYMLINK_FORBIDDEN")
        if not all(
            _SHA256_RE.fullmatch(value)
            for value in (
                self.plan_checkpoint_sha256,
                self.shadow_db_identity,
                self.selection_ledger_sha256,
                self.runtime_s1e_sha256,
            )
        ):
            raise ValueError("RUNTIME_CONTEXT_SHA256_INVALID")

    @property
    def capabilities(self):
        return runtime_mode_capabilities(self.runtime_mode)

    def canonical_payload(self) -> dict[str, str]:
        payload = asdict(self)
        return {
            key: value.value if isinstance(value, RuntimeMode) else str(value)
            for key, value in payload.items()
        }

    @property
    def context_sha256(self) -> str:
        return _sha256(_canonical_bytes(self.canonical_payload()))

    def to_child_env(self) -> dict[str, str]:
        return {
            "BET_PIPELINE_RUNTIME_MODE": self.runtime_mode.value,
            "BET_PIPELINE_RUNTIME_MODE_CONTRACT_VERSION": self.runtime_mode_contract_version,
            "BET_PIPELINE_RUNTIME_CONTEXT_SHA256": self.context_sha256,
            "BET_PIPELINE_RUN_ID": self.run_id,
            "BET_PIPELINE_RUN_ROOT": str(self.run_root),
            "BET_PIPELINE_BETTING_DAY": self.betting_date,
            "BET_PIPELINE_PLAN_ID": self.plan_id,
            "BET_PIPELINE_PLAN_CHECKPOINT_PATH": str(self.plan_checkpoint_path),
            "BET_PIPELINE_PLAN_CHECKPOINT_SHA256": self.plan_checkpoint_sha256,
            "BET_DB_PATH": str(self.shadow_db_path),
            "DATABASE_URL": f"sqlite:///{self.shadow_db_path}",
            "BET_PIPELINE_SHADOW_DB_IDENTITY": self.shadow_db_identity,
            "BET_PIPELINE_SELECTION_RUN_ID": self.selection_run_id,
            "BET_PIPELINE_SELECTION_LEDGER_PATH": str(self.selection_ledger_path),
            "BET_PIPELINE_SELECTION_LEDGER_SHA256": self.selection_ledger_sha256,
            # Legacy name is retained only as an alias for the ledger digest.
            "BET_PIPELINE_SELECTION_HASH": self.selection_ledger_sha256,
            "BET_PIPELINE_RUNTIME_S1E_PATH": str(self.runtime_s1e_path),
            "BET_PIPELINE_RUNTIME_S1E_SHA256": self.runtime_s1e_sha256,
            "BET_PIPELINE_STORAGE_SCOPE": "SHADOW",
            "BET_PIPELINE_SHADOW_WRITE_ALLOWED": "1",
            "BET_PIPELINE_CANONICAL_WRITE_ALLOWED": "0",
            "BET_PIPELINE_S9_ALLOWED": "0",
            "BET_PIPELINE_BOOKMAKER_ALLOWED": "0",
            "BET_PIPELINE_AUTOMATED_BET_PLACEMENT_ALLOWED": "0",
        }

    def verify_filesystem_bindings(self) -> None:
        paths = (
            (self.plan_checkpoint_path, self.plan_checkpoint_sha256),
            (self.selection_ledger_path, self.selection_ledger_sha256),
            (self.runtime_s1e_path, self.runtime_s1e_sha256),
        )
        for path, expected_hash in paths:
            if not Path(path).is_file() or _sha256_file(Path(path)) != expected_hash:
                raise ValueError("RUNTIME_CONTEXT_FILE_BINDING_INVALID")
        if not Path(self.shadow_db_path).is_file():
            raise ValueError("SHADOW_DB_MISSING")

    @classmethod
    def from_child_env(cls, env: dict[str, str]) -> "RuntimeExecutionContext":
        required = (
            "BET_PIPELINE_RUNTIME_MODE",
            "BET_PIPELINE_RUN_ID",
            "BET_PIPELINE_RUN_ROOT",
            "BET_PIPELINE_PLAN_ID",
            "BET_PIPELINE_PLAN_CHECKPOINT_PATH",
            "BET_PIPELINE_PLAN_CHECKPOINT_SHA256",
            "BET_DB_PATH",
            "BET_PIPELINE_SHADOW_DB_IDENTITY",
            "BET_PIPELINE_SELECTION_RUN_ID",
            "BET_PIPELINE_SELECTION_LEDGER_PATH",
            "BET_PIPELINE_SELECTION_LEDGER_SHA256",
            "BET_PIPELINE_RUNTIME_S1E_PATH",
            "BET_PIPELINE_RUNTIME_S1E_SHA256",
        )
        missing = [key for key in required if not env.get(key)]
        if missing:
            raise ValueError("RUNTIME_CONTEXT_ENV_MISSING:" + ",".join(missing))
        ctx = cls(
            runtime_mode=parse_runtime_mode(env["BET_PIPELINE_RUNTIME_MODE"]),
            runtime_mode_contract_version=env.get(
                "BET_PIPELINE_RUNTIME_MODE_CONTRACT_VERSION", ""
            ),
            run_id=env["BET_PIPELINE_RUN_ID"],
            run_root=Path(env["BET_PIPELINE_RUN_ROOT"]),
            plan_id=env["BET_PIPELINE_PLAN_ID"],
            plan_checkpoint_path=Path(env["BET_PIPELINE_PLAN_CHECKPOINT_PATH"]),
            plan_checkpoint_sha256=env["BET_PIPELINE_PLAN_CHECKPOINT_SHA256"],
            shadow_db_path=Path(env["BET_DB_PATH"]),
            shadow_db_identity=env["BET_PIPELINE_SHADOW_DB_IDENTITY"],
            selection_run_id=env["BET_PIPELINE_SELECTION_RUN_ID"],
            selection_ledger_path=Path(env["BET_PIPELINE_SELECTION_LEDGER_PATH"]),
            selection_ledger_sha256=env["BET_PIPELINE_SELECTION_LEDGER_SHA256"],
            runtime_s1e_path=Path(env["BET_PIPELINE_RUNTIME_S1E_PATH"]),
            runtime_s1e_sha256=env["BET_PIPELINE_RUNTIME_S1E_SHA256"],
            betting_date=env.get("BET_PIPELINE_BETTING_DAY", "1970-01-01"),
        )
        if env.get("BET_PIPELINE_RUNTIME_CONTEXT_SHA256") != ctx.context_sha256:
            raise ValueError("RUNTIME_CONTEXT_DIGEST_MISMATCH")
        if env.get("DATABASE_URL") != f"sqlite:///{ctx.shadow_db_path}":
            raise ValueError("DATABASE_URL_CONTEXT_MISMATCH")
        return ctx

    @classmethod
    def from_runtime_plan(
        cls, conn: sqlite3.Connection, plan_id: str
    ) -> "RuntimeExecutionContext":
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM pipeline_runtime_plans WHERE plan_id = ?", (plan_id,)
        ).fetchone()
        if row is None:
            raise ValueError("PLAN_NOT_FOUND")
        if row["status"] != "READY":
            raise ValueError("PLAN_NOT_READY")
        return cls(
            runtime_mode=RuntimeMode.LIVE_ANALYSIS_SHADOW,
            runtime_mode_contract_version=RUNTIME_MODE_CONTRACT_VERSION,
            run_id=row["run_id"], run_root=Path(row["run_root_path"]),
            plan_id=row["plan_id"],
            plan_checkpoint_path=Path(row["plan_checkpoint_path"]),
            plan_checkpoint_sha256=row["plan_checkpoint_sha256"],
            shadow_db_path=Path(row["shadow_db_path"]),
            shadow_db_identity=row["shadow_db_identity"],
            selection_run_id=row["run_id"],
            selection_ledger_path=Path(row["selection_ledger_path"]),
            selection_ledger_sha256=row["selection_ledger_sha256"],
            runtime_s1e_path=Path(row["runtime_s1e_path"]),
            runtime_s1e_sha256=row["runtime_s1e_sha256"],
            betting_date=row["betting_date"],
        )

    @classmethod
    def for_test(
        cls,
        *,
        run_root: Path,
        run_id: str,
        plan_id: str,
        canonical_db_path: Path | None = None,
        shadow_db_path: Path | None = None,
    ) -> "RuntimeExecutionContext":
        root = Path(run_root).resolve()
        root.mkdir(parents=True, exist_ok=True)
        data = root / "data"
        artifacts = root / "artifacts"
        data.mkdir(exist_ok=True)
        artifacts.mkdir(exist_ok=True)
        shadow = (
            Path(shadow_db_path)
            if shadow_db_path
            else data / "runtime_analysis_shadow.db"
        )
        if not shadow.exists():
            sqlite3.connect(shadow).close()
        checkpoint = artifacts / "plan_checkpoint.json"
        ledger = artifacts / "selection_ledger.json"
        s1e = artifacts / "S1e.json"
        for path, data_value in (
            (checkpoint, {"plan_id": plan_id}),
            (ledger, {"run_id": run_id}),
            (s1e, {"run_id": run_id}),
        ):
            if not path.exists():
                path.write_bytes(_canonical_bytes(data_value))
        return cls(
            runtime_mode=RuntimeMode.LIVE_ANALYSIS_SHADOW,
            runtime_mode_contract_version=RUNTIME_MODE_CONTRACT_VERSION,
            run_id=run_id,
            run_root=root,
            plan_id=plan_id,
            plan_checkpoint_path=checkpoint,
            plan_checkpoint_sha256=_sha256_file(checkpoint),
            shadow_db_path=shadow,
            shadow_db_identity=_sha256(
                _canonical_bytes(
                    {
                        "path": str(shadow.resolve()),
                        "initial_sha256": _sha256_file(shadow),
                        "run_id": run_id,
                    }
                )
            ),
            selection_run_id=run_id,
            selection_ledger_path=ledger,
            selection_ledger_sha256=_sha256_file(ledger),
            runtime_s1e_path=s1e,
            runtime_s1e_sha256=_sha256_file(s1e),
            betting_date="2027-07-30",
        )


def build_runtime_child_environment(
    *,
    parent_environment: dict[str, str],
    runtime_context: RuntimeExecutionContext,
    provider_secret_allowlist: Iterable[str],
) -> dict[str, str]:
    runtime_context.verify_filesystem_bindings()
    env: dict[str, str] = {}
    for key, value in parent_environment.items():
        if key in {
            "PATH",
            "HOME",
            "TMPDIR",
            "VIRTUAL_ENV",
            "PYTHONPATH",
            "LANG",
        } or key.startswith("LC_"):
            env[key] = value
    for key in provider_secret_allowlist:
        if key in parent_environment:
            env[key] = parent_environment[key]
    env = {
        key: value
        for key, value in env.items()
        if not key.startswith(_RUNTIME_ENV_PREFIX)
    }
    env.pop("DRY_RUN", None)
    env.pop("FORCE_ALLOW_WRITE", None)
    env.pop("BET_PIPELINE_WRITE_ACK", None)
    for key in tuple(env):
        if "bookmaker" in key.lower() or "betclic" in key.lower():
            env.pop(key)
    env.update(runtime_context.to_child_env())
    env["DRY_RUN"] = "0"
    if parent_environment.get(LIVE_ACK_KEY) != LIVE_ACK_VALUE:
        raise ValueError("LIVE_ACK_REQUIRED")
    env[LIVE_ACK_KEY] = LIVE_ACK_VALUE
    return env


class RuntimeDbRole(StrEnum):
    CANONICAL_READ_ONLY = "CANONICAL_READ_ONLY"
    SHADOW_READ_WRITE = "SHADOW_READ_WRITE"
    SHADOW_READ_ONLY = "SHADOW_READ_ONLY"


class RuntimeDatabaseAccessPolicy:
    def __init__(
        self, context: RuntimeExecutionContext, canonical_db_path: Path | None = None
    ):
        self.context = context
        self.canonical_db_path = (
            Path(canonical_db_path).resolve() if canonical_db_path else None
        )

    def connect(self, role: RuntimeDbRole | str) -> sqlite3.Connection:
        try:
            parsed_role = RuntimeDbRole(role)
        except ValueError as exc:
            raise ValueError("UNKNOWN_RUNTIME_DB_ROLE") from exc
        self.context.verify_filesystem_bindings()
        shadow = Path(self.context.shadow_db_path).resolve()
        if self.canonical_db_path and shadow == self.canonical_db_path:
            raise ValueError("CANONICAL_SHADOW_SAME_FILE")
        if parsed_role is RuntimeDbRole.CANONICAL_READ_ONLY:
            if not self.canonical_db_path or not self.canonical_db_path.is_file():
                raise ValueError("CANONICAL_DB_CONTEXT_MISSING")
            conn = sqlite3.connect(f"file:{self.canonical_db_path}?mode=ro", uri=True)
            conn.execute("PRAGMA query_only=ON")
            conn.execute("PRAGMA foreign_keys=ON")
            return conn
        readonly = parsed_role is RuntimeDbRole.SHADOW_READ_ONLY
        if readonly:
            conn = sqlite3.connect(f"file:{shadow}?mode=ro", uri=True)
            conn.execute("PRAGMA query_only=ON")
        else:
            conn = sqlite3.connect(shadow)
            conn.execute("PRAGMA foreign_keys=ON")
        return conn


def require_stage_capability(context: RuntimeExecutionContext, stage_id: str) -> None:
    normalized = stage_id.upper()
    if normalized == "S9":
        raise PermissionError("BLOCKED_S9_HUMAN_ONLY")
    if (
        "BOOKMAKER" in normalized
        or "PLACEMENT" in normalized
        or "BET" in normalized
        and normalized != "S8"
    ):
        raise PermissionError("BLOCKED_BOOKMAKER_INTERACTION")
    if normalized not in {
        "S0",
        "S1",
        "S1E",
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
        "S7B",
        "S8",
    }:
        raise PermissionError("BLOCKED_STAGE_NOT_ALLOWED")


def write_runtime_identity_receipt(
    context: RuntimeExecutionContext, stage_id: str
) -> Path:
    require_stage_capability(context, stage_id)
    receipts = Path(context.run_root) / "receipts"
    receipts.mkdir(parents=True, exist_ok=True)
    path = receipts / f"runtime_identity_{stage_id}.json"
    if path.exists():
        raise FileExistsError("RUNTIME_IDENTITY_RECEIPT_COLLISION")
    payload = {
        "schema_version": 1,
        "stage_id": stage_id,
        "producer": "runtime_execution",
        "pid": os.getpid(),
        "started_at_utc": datetime.now(UTC).isoformat(),
        "runtime_context_sha256": context.context_sha256,
        "runtime_mode": context.runtime_mode.value,
        "run_id": context.run_id,
        "plan_id": context.plan_id,
        "shadow_db_identity": context.shadow_db_identity,
        "selection_run_id": context.selection_run_id,
        "selection_ledger_sha256": context.selection_ledger_sha256,
        "runtime_s1e_sha256": context.runtime_s1e_sha256,
        "live_ack_present": True,
        "canonical_write_allowed": False,
        "shadow_write_allowed": True,
        "s9_allowed": False,
        "bookmaker_allowed": False,
        "automated_bet_placement_allowed": False,
    }
    temp = Path(tempfile.mkstemp(prefix=".runtime_identity_", dir=receipts)[1])
    try:
        temp.write_bytes(_canonical_bytes(payload))
        os.replace(temp, path)
    except Exception:
        temp.unlink(missing_ok=True)
        raise
    return path
