"""Immutable runtime plan creation and fresh continuation validation (C6)."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

from bet.db.repositories import ProviderObservationAttemptRepository
from bet.pipeline.event_runtime_contract import (
    CanonicalEventStatus,
    ProviderRequestStatus,
    parse_utc_timestamp,
)
from bet.pipeline.provider_observation_evidence import (
    persist_provider_observation_with_evidence,
    validate_persisted_provider_observation,
)
from bet.pipeline.runtime_event_classification import resolve_current_plan_observations
from bet.providers.revalidation import (
    ProviderEventRevalidationService,
    ProviderRevalidationResult,
)

DEFAULT_PLAN_MAX_AGE = timedelta(minutes=5)


class RuntimePlanStatus(StrEnum):
    CREATING = "CREATING"
    PLANNED = "PLANNED"
    VALIDATING = "VALIDATING"
    READY = "READY"
    INVALIDATED = "INVALIDATED"
    EXECUTING = "EXECUTING"
    CONSUMED = "CONSUMED"
    FAILED = "FAILED"


class ContinuationStatus(StrEnum):
    READY = "READY"
    PLAN_REFRESH_REQUIRED = "PLAN_REFRESH_REQUIRED"
    PLAN_EXPIRED = "PLAN_EXPIRED"
    PLAN_NOT_FOUND = "PLAN_NOT_FOUND"
    PLAN_ALREADY_CONSUMED = "PLAN_ALREADY_CONSUMED"
    PLAN_STATE_INVALID = "PLAN_STATE_INVALID"
    PLAN_INTEGRITY_FAILED = "PLAN_INTEGRITY_FAILED"
    SHADOW_DB_MISMATCH = "SHADOW_DB_MISMATCH"
    PROVIDER_REVALIDATION_FAILED = "PROVIDER_REVALIDATION_FAILED"
    CONCURRENT_VALIDATION = "CONCURRENT_VALIDATION"


@dataclass(frozen=True)
class MaterialProviderState:
    provider: str
    provider_event_id: str
    canonical_status: str
    observed_kickoff_utc: str
    participant_identity_sha256: str
    competition_identity_sha256: str | None
    request_status: str
    identity_state: str
    provider_evidence_sha256: str

    def material_payload(self) -> dict[str, Any]:
        kickoff = (
            parse_utc_timestamp(self.observed_kickoff_utc).isoformat()
            if self.observed_kickoff_utc
            else ""
        )
        return {
            "provider": self.provider,
            "provider_event_id": self.provider_event_id,
            "canonical_status": self.canonical_status,
            "observed_kickoff_utc": kickoff,
            "participant_identity_sha256": self.participant_identity_sha256,
            "competition_identity_sha256": self.competition_identity_sha256,
            "request_status": self.request_status,
            "identity_state": self.identity_state,
        }

    def plan_binding_payload(self) -> dict[str, Any]:
        return {
            **self.material_payload(),
            "provider_evidence_sha256": self.provider_evidence_sha256,
        }

    @property
    def fingerprint(self) -> str:
        return _digest_json(self.material_payload())


@dataclass(frozen=True)
class FrozenSelectedEvent:
    canonical_event_id: str
    fixture_id: int | None
    decision: str
    input_fingerprint: str
    required_event_chain_digest: str
    provider_states: tuple[MaterialProviderState, ...]
    resume_metadata: dict[str, Any]

    def digest_payload(self) -> dict[str, Any]:
        return {
            "canonical_event_id": self.canonical_event_id,
            "fixture_id": self.fixture_id,
            "decision": self.decision,
            "input_fingerprint": self.input_fingerprint,
            "required_event_chain_digest": self.required_event_chain_digest,
            "provider_states": [
                state.plan_binding_payload()
                for state in sorted(
                    self.provider_states, key=lambda item: item.provider
                )
            ],
            "resume_metadata": self.resume_metadata,
        }


@dataclass(frozen=True)
class RuntimePlanSnapshot:
    schema_version: int
    plan_id: str
    run_id: str
    betting_date: str
    created_at_utc: str
    expires_at_utc: str
    shadow_db_identity: str
    minimum_lead_minutes: int
    classification_policy_sha256: str
    selected_events: tuple[FrozenSelectedEvent, ...]
    selected_event_set_sha256: str
    provider_observation_set_sha256: str
    exact_event_accounting: dict[str, int]

    def canonical_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["selected_events"] = [
            event.digest_payload()
            for event in sorted(
                self.selected_events, key=lambda item: item.canonical_event_id
            )
        ]
        return payload


@dataclass(frozen=True)
class ContinuationValidationResult:
    status: ContinuationStatus
    plan_id: str
    run_id: str
    changed_event_ids: tuple[str, ...] = ()
    reason_codes: dict[str, tuple[str, ...]] | None = None
    old_material_fingerprints: dict[str, str] | None = None
    new_material_fingerprints: dict[str, str] | None = None
    continuation_attempt_ids: tuple[int, ...] = ()
    validated_at_utc: str | None = None


class ExactProviderAdapter(Protocol):
    def fetch_exact_event(
        self,
        *,
        provider_event_id: str,
        observed_at_utc: datetime,
    ) -> dict[str, Any] | ProviderRevalidationResult: ...


def _canonical_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _digest_json(payload: Any) -> str:
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def sha256_path(path: Path | str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _artifact_event_ids(
    path: Path, *, selected_only: bool
) -> tuple[set[str], dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("events"), list):
        raise ValueError(f"PLAN_ARTIFACT_INVALID: {path}")
    event_ids: list[str] = []
    for event in payload["events"]:
        if isinstance(event, dict):
            if selected_only and event.get("decision") not in (None, "ANALYZE_FROM_S2"):
                continue
            event_id = event.get("canonical_event_id")
        else:
            event_id = event
        if event_id is None:
            raise ValueError(f"PLAN_ARTIFACT_EVENT_ID_MISSING: {path}")
        event_ids.append(str(event_id))
    if len(event_ids) != len(set(event_ids)):
        raise ValueError(f"PLAN_ARTIFACT_DUPLICATE_EVENT_ID: {path}")
    return set(event_ids), payload


def _atomic_write_new(path: Path, payload: Any) -> str:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        raise FileExistsError(f"PLAN_ARTIFACT_COLLISION: {path}")
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(_canonical_bytes(payload))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise
    return sha256_path(path)


def selected_event_set_sha256(events: list[FrozenSelectedEvent]) -> str:
    return _digest_json(
        [
            event.digest_payload()
            for event in sorted(events, key=lambda item: item.canonical_event_id)
        ]
    )


def provider_observation_set_sha256(attempts: list[dict[str, Any]]) -> str:
    material = [
        {
            "id": attempt.get("id"),
            "run_id": attempt.get("run_id"),
            "phase": attempt.get("phase"),
            "attempt_number": attempt.get("attempt_number"),
            "canonical_event_id": attempt.get("canonical_event_id"),
            "provider": attempt.get("provider"),
            "provider_event_id": attempt.get("provider_event_id"),
            "request_status": attempt.get("request_status"),
            "canonical_event_status": attempt.get("canonical_event_status"),
            "observed_kickoff_utc": attempt.get("observed_kickoff_utc"),
            "participant_identity_sha256": attempt.get("participant_identity_sha256"),
            "competition_identity_sha256": attempt.get("competition_identity_sha256"),
            "observation_envelope_sha256": attempt.get("observation_envelope_sha256"),
        }
        for attempt in attempts
    ]
    return _digest_json(
        sorted(
            material,
            key=lambda item: (
                str(item["canonical_event_id"]),
                str(item["provider"]),
                int(item["attempt_number"] or 0),
                int(item["id"] or 0),
            ),
        )
    )


def material_state_from_attempt(attempt: dict[str, Any]) -> MaterialProviderState:
    request_status = str(attempt.get("request_status") or "")
    return MaterialProviderState(
        provider=str(attempt.get("provider") or ""),
        provider_event_id=str(attempt.get("provider_event_id") or ""),
        canonical_status=str(attempt.get("canonical_event_status") or "UNKNOWN"),
        observed_kickoff_utc=str(attempt.get("observed_kickoff_utc") or ""),
        participant_identity_sha256=str(
            attempt.get("participant_identity_sha256") or ""
        ),
        competition_identity_sha256=attempt.get("competition_identity_sha256"),
        request_status=request_status,
        identity_state=(
            "SUCCESS"
            if request_status == ProviderRequestStatus.SUCCESS.value
            else request_status or "UNKNOWN"
        ),
        provider_evidence_sha256=str(attempt.get("observation_envelope_sha256") or ""),
    )


class RuntimePlanRepository:
    _TRANSITIONS = {
        RuntimePlanStatus.CREATING: {
            RuntimePlanStatus.PLANNED,
            RuntimePlanStatus.FAILED,
        },
        RuntimePlanStatus.PLANNED: {
            RuntimePlanStatus.VALIDATING,
            RuntimePlanStatus.INVALIDATED,
        },
        RuntimePlanStatus.VALIDATING: {
            RuntimePlanStatus.READY,
            RuntimePlanStatus.INVALIDATED,
            RuntimePlanStatus.FAILED,
        },
        RuntimePlanStatus.READY: {
            RuntimePlanStatus.EXECUTING,
            RuntimePlanStatus.INVALIDATED,
        },
        RuntimePlanStatus.EXECUTING: {
            RuntimePlanStatus.CONSUMED,
            RuntimePlanStatus.FAILED,
        },
    }

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def insert_creating(self, values: dict[str, Any]) -> None:
        columns = ", ".join(values)
        placeholders = ", ".join("?" for _ in values)
        self.conn.execute(
            f"INSERT INTO pipeline_runtime_plans ({columns}) VALUES ({placeholders})",
            tuple(values.values()),
        )
        self.conn.commit()

    def get(self, plan_id: str) -> dict[str, Any] | None:
        self.conn.row_factory = sqlite3.Row
        row = self.conn.execute(
            "SELECT * FROM pipeline_runtime_plans WHERE plan_id = ?", (plan_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_by_run_id(self, run_id: str) -> dict[str, Any] | None:
        self.conn.row_factory = sqlite3.Row
        row = self.conn.execute(
            "SELECT * FROM pipeline_runtime_plans WHERE run_id = ?", (run_id,)
        ).fetchone()
        return dict(row) if row else None

    def update_creating(self, plan_id: str, values: dict[str, Any]) -> bool:
        assignments = ", ".join(f"{column} = ?" for column in values)
        cursor = self.conn.execute(
            f"UPDATE pipeline_runtime_plans SET {assignments} "
            "WHERE plan_id = ? AND status = 'CREATING'",
            (*values.values(), plan_id),
        )
        self.conn.commit()
        return cursor.rowcount == 1

    def transition(
        self,
        plan_id: str,
        expected: RuntimePlanStatus,
        target: RuntimePlanStatus,
        **updates: Any,
    ) -> bool:
        if target not in self._TRANSITIONS.get(expected, set()):
            raise ValueError(
                f"ILLEGAL_PLAN_STATE_TRANSITION: {expected.value}->{target.value}"
            )
        assignments = ["status = ?", *[f"{column} = ?" for column in updates]]
        params = [target.value, *updates.values(), plan_id, expected.value]
        cursor = self.conn.execute(
            f"UPDATE pipeline_runtime_plans SET {', '.join(assignments)} "
            "WHERE plan_id = ? AND status = ?",
            params,
        )
        self.conn.commit()
        return cursor.rowcount == 1

    def acquire_validation(self, plan_id: str, started_at: str) -> bool:
        cursor = self.conn.execute(
            """UPDATE pipeline_runtime_plans
               SET status = 'VALIDATING', continuation_started_at_utc = ?
               WHERE plan_id = ? AND status = 'PLANNED'""",
            (started_at, plan_id),
        )
        self.conn.commit()
        return cursor.rowcount == 1


class RuntimePlanService:
    def begin_plan(
        self,
        *,
        conn: sqlite3.Connection,
        plan_id: str,
        run_id: str,
        betting_date: str,
        canonical_db_path: Path,
        canonical_db_sha256: str,
        shadow_db_path: Path,
        shadow_db_initial_sha256: str,
        run_root: Path,
        created_at_utc: datetime,
        maximum_age: timedelta = DEFAULT_PLAN_MAX_AGE,
        minimum_lead_minutes: int = 15,
        classification_policy_sha256: str,
        created_by: str = "bet.pipeline.runtime_plan",
    ) -> None:
        created = parse_utc_timestamp(created_at_utc)
        if maximum_age <= timedelta(0):
            raise ValueError("PLAN_EXPIRY_INVALID")
        expires = created + maximum_age
        run_root = Path(run_root).resolve()
        shadow = Path(shadow_db_path).resolve()
        shadow.relative_to(run_root)
        shadow_identity = _digest_json(
            {
                "path": str(shadow),
                "initial_sha256": shadow_db_initial_sha256,
                "run_id": run_id,
            }
        )
        artifacts = run_root / "artifacts"
        RuntimePlanRepository(conn).insert_creating(
            {
                "plan_id": plan_id,
                "run_id": run_id,
                "betting_date": betting_date,
                "status": RuntimePlanStatus.CREATING.value,
                "created_at_utc": created.isoformat(),
                "expires_at_utc": expires.isoformat(),
                "canonical_db_path": str(Path(canonical_db_path).resolve()),
                "canonical_db_sha256_at_snapshot": canonical_db_sha256,
                "run_root_path": str(run_root),
                "shadow_db_path": str(shadow),
                "shadow_db_initial_sha256": shadow_db_initial_sha256,
                "shadow_db_identity": shadow_identity,
                "selection_ledger_path": str(artifacts / "selection_ledger.json"),
                "selection_ledger_sha256": "",
                "provider_observation_set_sha256": "",
                "runtime_s1e_path": "",
                "runtime_s1e_sha256": "",
                "plan_checkpoint_path": str(artifacts / "plan_checkpoint.json"),
                "plan_checkpoint_sha256": "",
                "plan_snapshot_path": str(artifacts / "runtime_plan_snapshot.json"),
                "plan_snapshot_sha256": "",
                "selected_event_set_sha256": "",
                "selected_event_count": 0,
                "minimum_lead_minutes": minimum_lead_minutes,
                "classification_policy_sha256": classification_policy_sha256,
                "created_by": created_by,
            }
        )

    def mark_failed(self, conn: sqlite3.Connection, plan_id: str, reason: str) -> None:
        RuntimePlanRepository(conn).transition(
            plan_id,
            RuntimePlanStatus.CREATING,
            RuntimePlanStatus.FAILED,
            invalidated_at_utc=datetime.now(UTC).isoformat(),
            invalidated_reason=reason,
        )

    def freeze_existing_plan(
        self,
        *,
        conn: sqlite3.Connection,
        plan_id: str,
        run_id: str,
        betting_date: str,
        canonical_db_path: Path,
        canonical_db_sha256: str,
        shadow_db_path: Path,
        shadow_db_initial_sha256: str,
        selection_ledger_path: Path,
        runtime_s1e_path: Path,
        plan_checkpoint_path: Path,
        created_at_utc: datetime,
        maximum_age: timedelta = DEFAULT_PLAN_MAX_AGE,
        minimum_lead_minutes: int = 15,
        classification_policy_sha256: str = "",
        code_head: str | None = None,
        code_tree: str | None = None,
        source_manifest_sha256: str | None = None,
        created_by: str = "bet.pipeline.runtime_plan",
    ) -> RuntimePlanSnapshot:
        created_at = parse_utc_timestamp(created_at_utc)
        if not plan_id or not run_id or not classification_policy_sha256:
            raise ValueError("PLAN_IDENTITY_INVALID")
        if minimum_lead_minutes < 0:
            raise ValueError("PLAN_MINIMUM_LEAD_INVALID")
        if maximum_age <= timedelta(0):
            raise ValueError("PLAN_EXPIRY_INVALID")
        expires_at = created_at + maximum_age
        repository = RuntimePlanRepository(conn)
        existing = repository.get(plan_id)
        existing_run = repository.get_by_run_id(run_id)
        if existing and (
            existing["run_id"] != run_id
            or existing["status"] != RuntimePlanStatus.CREATING.value
        ):
            raise FileExistsError(f"PLAN_RUN_COLLISION: {run_id}")
        if existing_run and existing_run["plan_id"] != plan_id:
            raise FileExistsError(f"PLAN_RUN_COLLISION: {run_id}")
        for path in (
            selection_ledger_path,
            runtime_s1e_path,
            plan_checkpoint_path,
            shadow_db_path,
        ):
            if not Path(path).is_file():
                raise FileNotFoundError(f"PLAN_ARTIFACT_MISSING: {path}")

        conn.row_factory = sqlite3.Row
        selection_rows = [
            dict(row)
            for row in conn.execute(
                """SELECT * FROM pipeline_runtime_event_selection
                   WHERE run_id = ? AND decision = 'ANALYZE_FROM_S2'
                   ORDER BY canonical_event_id""",
                (run_id,),
            ).fetchall()
        ]
        event_ids = [str(row["canonical_event_id"]) for row in selection_rows]
        if len(event_ids) != len(set(event_ids)):
            raise ValueError("DUPLICATE_CANONICAL_EVENT_ID")
        selected_id_set = set(event_ids)
        ledger_ids, ledger_payload = _artifact_event_ids(
            Path(selection_ledger_path), selected_only=True
        )
        runtime_ids, runtime_payload = _artifact_event_ids(
            Path(runtime_s1e_path), selected_only=False
        )
        if (
            ledger_payload.get("run_id") != run_id
            or runtime_payload.get("run_id") != run_id
        ):
            raise ValueError("PLAN_ARTIFACT_RUN_ID_MISMATCH")
        if ledger_payload.get("accounting_exact") is False:
            raise ValueError("PLAN_EVENT_ACCOUNTING_NOT_EXACT")
        if ledger_ids != selected_id_set or runtime_ids != selected_id_set:
            raise ValueError("RUNTIME_S1E_SELECTION_MISMATCH")
        all_plan_attempts = [
            dict(row)
            for row in conn.execute(
                """SELECT * FROM pipeline_provider_observation_attempts
                   WHERE run_id = ? AND phase = 'PLAN'
                   ORDER BY canonical_event_id, provider, attempt_number, id""",
                (run_id,),
            ).fetchall()
        ]
        plan_attempts: list[dict[str, Any]] = []
        for event_id in event_ids:
            current = resolve_current_plan_observations(
                [
                    attempt
                    for attempt in all_plan_attempts
                    if str(attempt["canonical_event_id"]) == event_id
                ],
                run_id,
            )
            plan_attempts.extend(current.values())
        attempts_by_event: dict[str, list[dict[str, Any]]] = {}
        for attempt in plan_attempts:
            event_id = str(attempt["canonical_event_id"])
            if event_id not in event_ids:
                continue
            valid, reason = validate_persisted_provider_observation(attempt)
            if attempt["request_status"] != "SUCCESS" or not valid:
                raise ValueError(
                    f"SELECTED_EVENT_PROVIDER_EVIDENCE_INVALID: {event_id}: {reason}"
                )
            attempts_by_event.setdefault(event_id, []).append(attempt)
        selected_events: list[FrozenSelectedEvent] = []
        for row in selection_rows:
            event_id = str(row["canonical_event_id"])
            attempts = attempts_by_event.get(event_id, [])
            if not attempts:
                raise ValueError(
                    f"SELECTED_EVENT_PROVIDER_EVIDENCE_MISSING: {event_id}"
                )
            selected_events.append(
                FrozenSelectedEvent(
                    canonical_event_id=event_id,
                    fixture_id=row.get("fixture_id"),
                    decision=row["decision"],
                    input_fingerprint=row["input_fingerprint"],
                    required_event_chain_digest=row.get("previous_analysis_sha256")
                    or "",
                    provider_states=tuple(
                        material_state_from_attempt(attempt) for attempt in attempts
                    ),
                    resume_metadata={
                        "resume_action": row.get("resume_action"),
                        "previous_analysis_status": row.get("previous_analysis_status"),
                    },
                )
            )
        selected_digest = selected_event_set_sha256(selected_events)
        observation_digest = provider_observation_set_sha256(
            [
                attempt
                for attempt in plan_attempts
                if str(attempt["canonical_event_id"]) in event_ids
            ]
        )
        shadow_identity = _digest_json(
            {
                "path": str(Path(shadow_db_path).resolve()),
                "initial_sha256": shadow_db_initial_sha256,
                "run_id": run_id,
            }
        )
        snapshot = RuntimePlanSnapshot(
            schema_version=1,
            plan_id=plan_id,
            run_id=run_id,
            betting_date=betting_date,
            created_at_utc=created_at.isoformat(),
            expires_at_utc=expires_at.isoformat(),
            shadow_db_identity=shadow_identity,
            minimum_lead_minutes=minimum_lead_minutes,
            classification_policy_sha256=classification_policy_sha256,
            selected_events=tuple(selected_events),
            selected_event_set_sha256=selected_digest,
            provider_observation_set_sha256=observation_digest,
            exact_event_accounting={"selected": len(selected_events)},
        )
        snapshot_path = (
            Path(plan_checkpoint_path).resolve().parent / "runtime_plan_snapshot.json"
        )
        snapshot_sha = _atomic_write_new(snapshot_path, snapshot.canonical_payload())
        values = {
            "plan_id": plan_id,
            "run_id": run_id,
            "betting_date": betting_date,
            "status": RuntimePlanStatus.CREATING.value,
            "created_at_utc": created_at.isoformat(),
            "expires_at_utc": expires_at.isoformat(),
            "canonical_db_path": str(Path(canonical_db_path).resolve()),
            "canonical_db_sha256_at_snapshot": canonical_db_sha256,
            "run_root_path": str(Path(shadow_db_path).resolve().parents[1]),
            "shadow_db_path": str(Path(shadow_db_path).resolve()),
            "shadow_db_initial_sha256": shadow_db_initial_sha256,
            "shadow_db_identity": shadow_identity,
            "selection_ledger_path": str(Path(selection_ledger_path).resolve()),
            "selection_ledger_sha256": sha256_path(selection_ledger_path),
            "provider_observation_set_sha256": observation_digest,
            "runtime_s1e_path": str(Path(runtime_s1e_path).resolve()),
            "runtime_s1e_sha256": sha256_path(runtime_s1e_path),
            "plan_checkpoint_path": str(Path(plan_checkpoint_path).resolve()),
            "plan_checkpoint_sha256": sha256_path(plan_checkpoint_path),
            "plan_snapshot_path": str(snapshot_path),
            "plan_snapshot_sha256": snapshot_sha,
            "selected_event_set_sha256": selected_digest,
            "selected_event_count": len(selected_events),
            "minimum_lead_minutes": minimum_lead_minutes,
            "classification_policy_sha256": classification_policy_sha256,
            "code_head": code_head,
            "code_tree": code_tree,
            "source_manifest_sha256": source_manifest_sha256,
            "created_by": created_by,
        }
        try:
            if existing:
                values.pop("plan_id")
                values.pop("run_id")
                values.pop("status")
                if not repository.update_creating(plan_id, values):
                    raise RuntimeError("PLAN_STATE_TRANSITION_FAILED")
            else:
                repository.insert_creating(values)
        except Exception:
            snapshot_path.unlink(missing_ok=True)
            raise
        if not repository.transition(
            plan_id, RuntimePlanStatus.CREATING, RuntimePlanStatus.PLANNED
        ):
            raise RuntimeError("PLAN_STATE_TRANSITION_FAILED")
        return snapshot


def _load_snapshot(plan: dict[str, Any]) -> RuntimePlanSnapshot:
    payload = json.loads(Path(plan["plan_snapshot_path"]).read_text(encoding="utf-8"))
    events = []
    for event in payload["selected_events"]:
        events.append(
            FrozenSelectedEvent(
                canonical_event_id=event["canonical_event_id"],
                fixture_id=event.get("fixture_id"),
                decision=event["decision"],
                input_fingerprint=event["input_fingerprint"],
                required_event_chain_digest=event.get(
                    "required_event_chain_digest", ""
                ),
                provider_states=tuple(
                    MaterialProviderState(**state)
                    for state in event.get("provider_states", [])
                ),
                resume_metadata=event.get("resume_metadata", {}),
            )
        )
    return RuntimePlanSnapshot(
        schema_version=payload["schema_version"],
        plan_id=payload["plan_id"],
        run_id=payload["run_id"],
        betting_date=payload["betting_date"],
        created_at_utc=payload["created_at_utc"],
        expires_at_utc=payload["expires_at_utc"],
        shadow_db_identity=payload["shadow_db_identity"],
        minimum_lead_minutes=payload["minimum_lead_minutes"],
        classification_policy_sha256=payload["classification_policy_sha256"],
        selected_events=tuple(events),
        selected_event_set_sha256=payload["selected_event_set_sha256"],
        provider_observation_set_sha256=payload["provider_observation_set_sha256"],
        exact_event_accounting=payload["exact_event_accounting"],
    )


class RuntimePlanContinuationService:
    def validate_for_execution(
        self,
        *,
        conn: sqlite3.Connection,
        plan_id: str,
        runtime_now_utc: datetime,
        adapters: dict[str, ExactProviderAdapter],
        evidence_root: Path,
        maximum_age: timedelta = DEFAULT_PLAN_MAX_AGE,
    ) -> ContinuationValidationResult:
        now = parse_utc_timestamp(runtime_now_utc)
        repository = RuntimePlanRepository(conn)
        plan = repository.get(plan_id)
        if not plan:
            return ContinuationValidationResult(
                ContinuationStatus.PLAN_NOT_FOUND, plan_id, ""
            )
        run_id = plan["run_id"]
        if plan["status"] == RuntimePlanStatus.CONSUMED.value:
            return ContinuationValidationResult(
                ContinuationStatus.PLAN_ALREADY_CONSUMED, plan_id, run_id
            )
        if plan["status"] == RuntimePlanStatus.VALIDATING.value:
            return ContinuationValidationResult(
                ContinuationStatus.CONCURRENT_VALIDATION, plan_id, run_id
            )
        if plan["status"] == RuntimePlanStatus.READY.value:
            cached = json.loads(plan.get("validation_result_json") or "{}")
            return ContinuationValidationResult(
                ContinuationStatus.READY,
                plan_id,
                run_id,
                continuation_attempt_ids=tuple(
                    cached.get("continuation_attempt_ids", [])
                ),
                validated_at_utc=plan.get("continuation_completed_at_utc"),
            )
        if plan["status"] != RuntimePlanStatus.PLANNED.value:
            return ContinuationValidationResult(
                ContinuationStatus.PLAN_STATE_INVALID, plan_id, run_id
            )
        created = parse_utc_timestamp(plan["created_at_utc"])
        expires = parse_utc_timestamp(plan["expires_at_utc"])
        if (
            expires <= created
            or expires - created > maximum_age
            or created > now + timedelta(seconds=30)
            or now >= expires
        ):
            repository.transition(
                plan_id,
                RuntimePlanStatus.PLANNED,
                RuntimePlanStatus.INVALIDATED,
                invalidated_at_utc=now.isoformat(),
                invalidated_reason="PLAN_EXPIRED",
            )
            return ContinuationValidationResult(
                ContinuationStatus.PLAN_EXPIRED, plan_id, run_id
            )
        if not repository.acquire_validation(plan_id, now.isoformat()):
            return ContinuationValidationResult(
                ContinuationStatus.CONCURRENT_VALIDATION, plan_id, run_id
            )

        integrity_paths = {
            "selection": (
                plan["selection_ledger_path"],
                plan["selection_ledger_sha256"],
            ),
            "runtime_s1e": (plan["runtime_s1e_path"], plan["runtime_s1e_sha256"]),
            "checkpoint": (
                plan["plan_checkpoint_path"],
                plan["plan_checkpoint_sha256"],
            ),
            "snapshot": (plan["plan_snapshot_path"], plan["plan_snapshot_sha256"]),
        }
        for _, (path_value, expected_sha) in integrity_paths.items():
            path = Path(path_value)
            if not path.is_file() or sha256_path(path) != expected_sha:
                repository.transition(
                    plan_id,
                    RuntimePlanStatus.VALIDATING,
                    RuntimePlanStatus.FAILED,
                    validation_result_json=json.dumps(
                        {"status": "PLAN_INTEGRITY_FAILED"}
                    ),
                )
                return ContinuationValidationResult(
                    ContinuationStatus.PLAN_INTEGRITY_FAILED, plan_id, run_id
                )
        if not Path(plan["shadow_db_path"]).is_file():
            repository.transition(
                plan_id,
                RuntimePlanStatus.VALIDATING,
                RuntimePlanStatus.FAILED,
            )
            return ContinuationValidationResult(
                ContinuationStatus.SHADOW_DB_MISMATCH, plan_id, run_id
            )
        expected_shadow_identity = _digest_json(
            {
                "path": str(Path(plan["shadow_db_path"]).resolve()),
                "initial_sha256": plan["shadow_db_initial_sha256"],
                "run_id": run_id,
            }
        )
        if expected_shadow_identity != plan["shadow_db_identity"]:
            repository.transition(
                plan_id,
                RuntimePlanStatus.VALIDATING,
                RuntimePlanStatus.FAILED,
            )
            return ContinuationValidationResult(
                ContinuationStatus.SHADOW_DB_MISMATCH, plan_id, run_id
            )
        snapshot = _load_snapshot(plan)
        run_root = Path(plan["run_root_path"]).resolve()
        try:
            for path_column in (
                "shadow_db_path",
                "selection_ledger_path",
                "runtime_s1e_path",
                "plan_checkpoint_path",
                "plan_snapshot_path",
            ):
                Path(plan[path_column]).resolve().relative_to(run_root)
        except ValueError:
            repository.transition(
                plan_id,
                RuntimePlanStatus.VALIDATING,
                RuntimePlanStatus.FAILED,
            )
            return ContinuationValidationResult(
                ContinuationStatus.PLAN_INTEGRITY_FAILED, plan_id, run_id
            )
        if (
            snapshot.plan_id != plan_id
            or snapshot.run_id != run_id
            or snapshot.betting_date != plan["betting_date"]
            or parse_utc_timestamp(snapshot.created_at_utc) != created
            or parse_utc_timestamp(snapshot.expires_at_utc) != expires
            or snapshot.shadow_db_identity != plan["shadow_db_identity"]
            or snapshot.minimum_lead_minutes != plan["minimum_lead_minutes"]
            or snapshot.classification_policy_sha256
            != plan["classification_policy_sha256"]
            or snapshot.provider_observation_set_sha256
            != plan["provider_observation_set_sha256"]
        ):
            repository.transition(
                plan_id,
                RuntimePlanStatus.VALIDATING,
                RuntimePlanStatus.FAILED,
            )
            return ContinuationValidationResult(
                ContinuationStatus.PLAN_INTEGRITY_FAILED, plan_id, run_id
            )
        if (
            selected_event_set_sha256(list(snapshot.selected_events))
            != plan["selected_event_set_sha256"]
        ):
            repository.transition(
                plan_id,
                RuntimePlanStatus.VALIDATING,
                RuntimePlanStatus.FAILED,
            )
            return ContinuationValidationResult(
                ContinuationStatus.PLAN_INTEGRITY_FAILED, plan_id, run_id
            )

        frozen_ids = {event.canonical_event_id for event in snapshot.selected_events}
        conn.row_factory = sqlite3.Row
        current_selection = [
            dict(row)
            for row in conn.execute(
                """SELECT canonical_event_id, input_fingerprint
                   FROM pipeline_runtime_event_selection
                   WHERE run_id = ? AND decision = 'ANALYZE_FROM_S2'
                   ORDER BY canonical_event_id""",
                (run_id,),
            ).fetchall()
        ]
        current_ids = {str(row["canonical_event_id"]) for row in current_selection}
        frozen_fingerprints = {
            event.canonical_event_id: event.input_fingerprint
            for event in snapshot.selected_events
        }
        fingerprint_changed_ids = {
            str(row["canonical_event_id"])
            for row in current_selection
            if frozen_fingerprints.get(str(row["canonical_event_id"]))
            != row["input_fingerprint"]
        }
        if current_ids != frozen_ids or fingerprint_changed_ids:
            repository.transition(
                plan_id,
                RuntimePlanStatus.VALIDATING,
                RuntimePlanStatus.INVALIDATED,
                continuation_completed_at_utc=now.isoformat(),
                invalidated_at_utc=now.isoformat(),
                invalidated_reason="PLAN_REFRESH_REQUIRED",
            )
            changed_ids = tuple(
                sorted(
                    frozen_ids.symmetric_difference(current_ids)
                    | fingerprint_changed_ids
                )
            )
            return ContinuationValidationResult(
                ContinuationStatus.PLAN_REFRESH_REQUIRED,
                plan_id,
                run_id,
                changed_event_ids=changed_ids,
            )

        all_plan_attempts = [
            dict(row)
            for row in conn.execute(
                """SELECT * FROM pipeline_provider_observation_attempts
                   WHERE run_id = ? AND phase = 'PLAN'
                   ORDER BY canonical_event_id, provider, attempt_number, id""",
                (run_id,),
            ).fetchall()
            if str(row["canonical_event_id"]) in frozen_ids
        ]
        plan_attempts: list[dict[str, Any]] = []
        for event_id in frozen_ids:
            current = resolve_current_plan_observations(
                [
                    attempt
                    for attempt in all_plan_attempts
                    if str(attempt["canonical_event_id"]) == event_id
                ],
                run_id,
            )
            plan_attempts.extend(current.values())
        if provider_observation_set_sha256(plan_attempts) != plan[
            "provider_observation_set_sha256"
        ] or any(
            not validate_persisted_provider_observation(attempt)[0]
            for attempt in plan_attempts
        ):
            repository.transition(
                plan_id,
                RuntimePlanStatus.VALIDATING,
                RuntimePlanStatus.FAILED,
            )
            return ContinuationValidationResult(
                ContinuationStatus.PLAN_INTEGRITY_FAILED, plan_id, run_id
            )

        attempts_repo = ProviderObservationAttemptRepository(conn)
        attempt_ids: list[int] = []
        changed: dict[str, list[str]] = {}
        old_fingerprints: dict[str, str] = {}
        new_fingerprints: dict[str, str] = {}
        for event in snapshot.selected_events:
            event_reasons: list[str] = []
            for old_state in event.provider_states:
                adapter = adapters.get(old_state.provider)
                if adapter is None:
                    result = ProviderRevalidationResult(
                        provider=old_state.provider,
                        provider_event_id=old_state.provider_event_id,
                        request_status=ProviderRequestStatus.UNSUPPORTED,
                        error_code="ADAPTER_UNAVAILABLE",
                    )
                else:
                    try:
                        if hasattr(adapter, "fetch_exact_event"):
                            network_result = adapter.fetch_exact_event(
                                provider_event_id=old_state.provider_event_id,
                                observed_at_utc=now,
                            )
                            if isinstance(network_result, ProviderRevalidationResult):
                                result = network_result
                            else:
                                revalidator = ProviderEventRevalidationService()
                                result = revalidator.revalidate_exact_event(
                                    provider=old_state.provider,
                                    provider_event_id=old_state.provider_event_id,
                                    available_events=[network_result],
                                    allow_fallback=False,
                                )
                        else:
                            result = adapter.revalidate_event(
                                provider_event_id=old_state.provider_event_id,
                                expected_identity=old_state,
                                observed_at_utc=now,
                            )
                    except Exception as exc:
                        result = ProviderRevalidationResult(
                            provider=old_state.provider,
                            provider_event_id=old_state.provider_event_id,
                            request_status=ProviderRequestStatus.FAILED,
                            error_code="PROVIDER_CALL_FAILED",
                            error_detail=type(exc).__name__,
                        )
                attempt_number = conn.execute(
                    """SELECT COALESCE(MAX(attempt_number), 0) + 1
                       FROM pipeline_provider_observation_attempts
                       WHERE run_id = ? AND phase = 'CONTINUATION'
                         AND canonical_event_id = ? AND provider = ?""",
                    (run_id, event.canonical_event_id, old_state.provider),
                ).fetchone()[0]
                result_status = (
                    result.request_status.value
                    if hasattr(result.request_status, "value")
                    else str(result.request_status)
                )
                canonical_status = (
                    result.canonical_event_status.value
                    if hasattr(result.canonical_event_status, "value")
                    else str(result.canonical_event_status)
                )
                attempt_id = persist_provider_observation_with_evidence(
                    conn,
                    {
                        "run_id": run_id,
                        "phase": "CONTINUATION",
                        "attempt_number": attempt_number,
                        "canonical_event_id": event.canonical_event_id,
                        "fixture_id": event.fixture_id,
                        "provider": result.provider,
                        "provider_event_id": result.provider_event_id,
                        "attempted_at_utc": now.isoformat(),
                        "request_status": result_status,
                        "raw_provider_status": result.raw_provider_status,
                        "canonical_event_status": canonical_status,
                        "raw_observed_kickoff": result.raw_observed_kickoff,
                        "observed_kickoff_utc": result.observed_kickoff_utc,
                        "observed_home_name": result.observed_home_name,
                        "observed_away_name": result.observed_away_name,
                        "participant_identity_sha256": (
                            result.participant_identity_sha256
                        ),
                        "competition_identity_sha256": (
                            result.competition_identity_sha256
                        ),
                        "upstream_evidence_bundle_id": (
                            result.upstream_evidence_bundle_id
                        ),
                        "upstream_evidence_refs": result.upstream_evidence_refs,
                        "error_code": result.error_code,
                        "error_detail": result.error_detail,
                    },
                    evidence_root,
                )
                attempt_ids.append(attempt_id)
                persisted = attempts_repo.get_attempt_by_id(attempt_id)
                valid_evidence, _ = validate_persisted_provider_observation(persisted)
                new_state = material_state_from_attempt(persisted)
                old_fingerprints[f"{event.canonical_event_id}:{old_state.provider}"] = (
                    old_state.fingerprint
                )
                new_fingerprints[f"{event.canonical_event_id}:{old_state.provider}"] = (
                    new_state.fingerprint
                )
                if not valid_evidence:
                    event_reasons.append("CONTINUATION_EVIDENCE_INVALID")
                if result_status != ProviderRequestStatus.SUCCESS.value:
                    event_reasons.append(f"PROVIDER_{result_status}")
                if canonical_status != CanonicalEventStatus.SCHEDULED.value:
                    event_reasons.append(f"STATUS_{canonical_status}")
                try:
                    fresh_kickoff = parse_utc_timestamp(new_state.observed_kickoff_utc)
                except ValueError:
                    event_reasons.append("KICKOFF_INVALID")
                else:
                    if fresh_kickoff <= now + timedelta(
                        minutes=snapshot.minimum_lead_minutes
                    ):
                        event_reasons.append("INSUFFICIENT_LEAD")
                if old_state.fingerprint != new_state.fingerprint:
                    event_reasons.append("MATERIAL_PROVIDER_STATE_CHANGED")
            if event_reasons:
                changed[event.canonical_event_id] = sorted(set(event_reasons))

        if changed:
            result_payload = {
                "status": ContinuationStatus.PLAN_REFRESH_REQUIRED.value,
                "changed_event_ids": sorted(changed),
                "reason_codes": changed,
                "continuation_attempt_ids": attempt_ids,
                "validated_at_utc": now.isoformat(),
                "old_material_fingerprints": old_fingerprints,
                "new_material_fingerprints": new_fingerprints,
            }
            repository.transition(
                plan_id,
                RuntimePlanStatus.VALIDATING,
                RuntimePlanStatus.INVALIDATED,
                continuation_completed_at_utc=now.isoformat(),
                invalidated_at_utc=now.isoformat(),
                invalidated_reason="PLAN_REFRESH_REQUIRED",
                validation_result_json=json.dumps(result_payload, sort_keys=True),
            )
            return ContinuationValidationResult(
                ContinuationStatus.PLAN_REFRESH_REQUIRED,
                plan_id,
                run_id,
                changed_event_ids=tuple(sorted(changed)),
                reason_codes={key: tuple(value) for key, value in changed.items()},
                old_material_fingerprints=old_fingerprints,
                new_material_fingerprints=new_fingerprints,
                continuation_attempt_ids=tuple(attempt_ids),
                validated_at_utc=now.isoformat(),
            )
        repository.transition(
            plan_id,
            RuntimePlanStatus.VALIDATING,
            RuntimePlanStatus.READY,
            continuation_completed_at_utc=now.isoformat(),
            validation_result_json=json.dumps(
                {
                    "status": ContinuationStatus.READY.value,
                    "continuation_attempt_ids": attempt_ids,
                },
                sort_keys=True,
            ),
        )
        return ContinuationValidationResult(
            ContinuationStatus.READY,
            plan_id,
            run_id,
            continuation_attempt_ids=tuple(attempt_ids),
            validated_at_utc=now.isoformat(),
        )
