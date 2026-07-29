"""Typed step reducers for sharded agent step aggregation in BET PIPELINE V5."""
from __future__ import annotations

from typing import Any, Callable, Sequence
from pydantic import Field
from bet.pipeline.contracts.base import StrictBaseModel
from bet.pipeline.sharding.models import ChunkArtifactV1
from bet.pipeline.sharding.lifecycle import ChunkLifecycleError


class ReducerError(ChunkLifecycleError):
    """Raised when step-specific chunk reduction fails business or contract rules."""
    pass


class ReducedParentResultV1(StrictBaseModel):
    """Typed complete result produced by a sharded step reducer."""
    status: str
    payload: dict[str, Any]
    event_records: tuple[dict[str, Any], ...] | list[dict[str, Any]]
    sources: tuple[str, ...] = ("sharded_chunk_aggregator",)
    source_bound: bool = True
    unknowns: tuple[str, ...] = ()
    blocked_reasons: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    predecessor_bindings: tuple[dict[str, Any], ...] = ()
    coverage_receipt: dict[str, Any] = Field(default_factory=dict)


def _collect_common_chunk_metadata(artifacts: Sequence[ChunkArtifactV1]) -> tuple[list[str], list[dict[str, Any]]]:
    """Extract unique evidence_refs and predecessor_bindings from chunk artifacts."""
    evidence_refs: list[str] = []
    predecessor_bindings: list[dict[str, Any]] = []

    for art in artifacts:
        if getattr(art, "expected_artifact_path", None):
            ref = getattr(art, "expected_artifact_path")
            if ref and ref not in evidence_refs:
                evidence_refs.append(ref)
        if getattr(art, "chunk_id", None):
            ref = f"artifacts/chunks/{art.chunk_id}.json"
            if ref not in evidence_refs:
                evidence_refs.append(ref)

        p_wo_id = getattr(art, "parent_work_order_id", "")
        p_wo_sha = getattr(art, "parent_work_order_sha256", "")
        if p_wo_id and p_wo_sha:
            binding = {"work_order_id": p_wo_id, "work_order_sha256": p_wo_sha}
            if binding not in predecessor_bindings:
                predecessor_bindings.append(binding)

    return evidence_refs, predecessor_bindings


def reduce_s2_3_chunks(artifacts: Sequence[ChunkArtifactV1]) -> ReducedParentResultV1:
    """Reducer for S2.3 enrichment gap detection."""
    all_gaps = []
    all_records = []
    for art in sorted(artifacts, key=lambda a: a.chunk_index):
        if art.status != "PASS":
            raise ReducerError(f"REDUCER_FAILED: S2.3 chunk {art.chunk_id} status is {art.status}")

        payload = art.payload or {}
        gaps = payload.get("gaps") or payload.get("enrichment_gaps") or []
        for g in gaps:
            if isinstance(g, dict):
                all_gaps.append(g)

        recs = art.event_records or payload.get("event_records") or []
        for r in recs:
            if isinstance(r, dict):
                all_records.append(r)

    ev_refs, pred_bindings = _collect_common_chunk_metadata(artifacts)

    # Fail-closed: no non-empty universe with zero evidence
    if len(artifacts) > 0 and len(all_gaps) == 0 and len(all_records) == 0:
        return ReducedParentResultV1(
            status="BLOCK",
            payload={"gaps": [], "total_gaps_identified": 0},
            event_records=all_records,
            blocked_reasons=("EMPTY_EVIDENCE_REDUCER_FAIL_CLOSED",),
            evidence_refs=tuple(ev_refs) if ev_refs else ("artifacts/chunks/",),
            predecessor_bindings=tuple(pred_bindings),
        )

    has_blocking_gaps = any(g.get("severity") == "HIGH" and g.get("status") == "OPEN" for g in all_gaps)
    status_val = "BLOCK" if has_blocking_gaps else "PASS"
    blocked_reasons = ("OPEN_HIGH_SEVERITY_GAP",) if has_blocking_gaps else ()

    payload_data = {
        "status": status_val,
        "total_gaps_identified": len(all_gaps),
        "gaps": all_gaps,
        "gaps_bounded": True,
    }

    return ReducedParentResultV1(
        status=status_val,
        payload=payload_data,
        event_records=all_records if all_records else [{"total_gaps": len(all_gaps)}],
        blocked_reasons=blocked_reasons,
        evidence_refs=tuple(ev_refs) if ev_refs else ("artifacts/chunks/",),
        predecessor_bindings=tuple(pred_bindings),
    )


def reduce_s2_5_chunks(artifacts: Sequence[ChunkArtifactV1]) -> ReducedParentResultV1:
    """Reducer for S2.5 provider observations."""
    all_observations = []
    all_records = []
    for art in sorted(artifacts, key=lambda a: a.chunk_index):
        if art.status != "PASS":
            raise ReducerError(f"REDUCER_FAILED: S2.5 chunk {art.chunk_id} status is {art.status}")

        payload = art.payload or {}
        obs = payload.get("observations") or payload.get("provider_observations") or []
        for item in obs:
            if isinstance(item, dict):
                all_observations.append(item)

        recs = art.event_records or payload.get("event_records") or []
        for r in recs:
            if isinstance(r, dict):
                all_records.append(r)

    ev_refs, pred_bindings = _collect_common_chunk_metadata(artifacts)

    if len(artifacts) > 0 and len(all_observations) == 0 and len(all_records) == 0:
        return ReducedParentResultV1(
            status="BLOCK",
            payload={"observations": [], "total_observations": 0},
            event_records=all_records,
            blocked_reasons=("EMPTY_EVIDENCE_REDUCER_FAIL_CLOSED",),
            evidence_refs=tuple(ev_refs) if ev_refs else ("artifacts/chunks/",),
            predecessor_bindings=tuple(pred_bindings),
        )

    payload_data = {
        "status": "PASS",
        "total_observations": len(all_observations),
        "observations": all_observations,
        "provider_observations": all_observations,
    }

    return ReducedParentResultV1(
        status="PASS",
        payload=payload_data,
        event_records=all_records if all_records else [{"total_obs": len(all_observations)}],
        evidence_refs=tuple(ev_refs) if ev_refs else ("artifacts/chunks/",),
        predecessor_bindings=tuple(pred_bindings),
    )


def reduce_s2_7_chunks(artifacts: Sequence[ChunkArtifactV1]) -> ReducedParentResultV1:
    """Reducer for S2.7 source reconciliation."""
    all_reconciled = []
    all_conflicts = []
    all_records = []
    for art in sorted(artifacts, key=lambda a: a.chunk_index):
        if art.status != "PASS":
            raise ReducerError(f"REDUCER_FAILED: S2.7 chunk {art.chunk_id} status is {art.status}")

        payload = art.payload or {}
        rec = payload.get("reconciled_facts") or []
        for r in rec:
            if isinstance(r, dict):
                all_reconciled.append(r)

        conf = payload.get("unresolved_conflicts") or payload.get("conflicts") or payload.get("disputed_facts") or []
        for c in conf:
            if isinstance(c, dict):
                all_conflicts.append(c)

        ev_recs = art.event_records or payload.get("event_records") or []
        for r in ev_recs:
            if isinstance(r, dict):
                all_records.append(r)

    ev_refs, pred_bindings = _collect_common_chunk_metadata(artifacts)

    if len(artifacts) > 0 and len(all_reconciled) == 0 and len(all_records) == 0:
        return ReducedParentResultV1(
            status="BLOCK",
            payload={"reconciled_facts": [], "disputed_facts": []},
            event_records=all_records,
            blocked_reasons=("EMPTY_EVIDENCE_REDUCER_FAIL_CLOSED",),
            evidence_refs=tuple(ev_refs) if ev_refs else ("artifacts/chunks/",),
            predecessor_bindings=tuple(pred_bindings),
        )

    has_unresolved_required_conflict = any(c.get("status") == "UNRESOLVED" and c.get("is_required", True) for c in all_conflicts)
    status_val = "BLOCK" if has_unresolved_required_conflict else "PASS"
    blocked_reasons = ("UNRESOLVED_REQUIRED_CONFLICT",) if has_unresolved_required_conflict else ()

    payload_data = {
        "status": status_val,
        "total_reconciled": len(all_reconciled),
        "conflicts_detected": len(all_conflicts),
        "reconciled_facts": all_reconciled,
        "reconciliation": {"reconciled_facts": all_reconciled, "conflicts": all_conflicts},
        "disputed_facts": all_conflicts,
        "unresolved_conflicts": all_conflicts,
    }

    return ReducedParentResultV1(
        status=status_val,
        payload=payload_data,
        event_records=all_records if all_records else [{"total_reconciled": len(all_reconciled)}],
        blocked_reasons=blocked_reasons,
        evidence_refs=tuple(ev_refs) if ev_refs else ("artifacts/chunks/",),
        predecessor_bindings=tuple(pred_bindings),
    )


def reduce_s2_9_chunks(artifacts: Sequence[ChunkArtifactV1]) -> ReducedParentResultV1:
    """Reducer for S2.9 data readiness gate (S2.9 PASS parent)."""
    all_readiness = []
    all_records = []
    overall_quality = "HIGH"
    has_placeholder_identity = False

    for art in sorted(artifacts, key=lambda a: a.chunk_index):
        if art.status not in ("PASS", "READY"):
            raise ReducerError(f"REDUCER_FAILED: S2.9 chunk {art.chunk_id} status is {art.status}")

        payload = art.payload or {}
        readiness = payload.get("readiness_by_event") or []
        for r in readiness:
            if isinstance(r, dict):
                all_readiness.append(r)
                q = r.get("quality_grade", "HIGH")
                if q == "LOW":
                    overall_quality = "LOW"
                elif q == "MEDIUM" and overall_quality != "LOW":
                    overall_quality = "MEDIUM"

                # V4-P1-06: Check placeholder identities
                home = str(r.get("home_team") or "").lower()
                away = str(r.get("away_team") or "").lower()
                comp = str(r.get("competition") or "").lower()
                if home in ("home", "unknown") or away in ("away", "unknown") or comp in ("all", "unknown"):
                    has_placeholder_identity = True

        ev_recs = art.event_records or payload.get("event_records") or []
        for r in ev_recs:
            if isinstance(r, dict):
                all_records.append(r)

    ev_refs, pred_bindings = _collect_common_chunk_metadata(artifacts)

    any_blocked = any(r.get("readiness_tier") == "BLOCKED" for r in all_readiness)
    is_empty = len(artifacts) > 0 and len(all_readiness) == 0

    if any_blocked or has_placeholder_identity or is_empty:
        status_val = "BLOCK"
        readiness_label = "BLOCK"
        s3_may_proceed = False
        blocked_reasons = ("EVENT_READINESS_BLOCKED",) if any_blocked else (("PLACEHOLDER_IDENTITY_FORBIDDEN",) if has_placeholder_identity else ("EMPTY_EVIDENCE_REDUCER_FAIL_CLOSED",))
    else:
        status_val = "PASS" # V4-P0-07: AGENT_ARTIFACT success status MUST BE PASS!
        readiness_label = "PASS"
        s3_may_proceed = True
        blocked_reasons = ()

    payload_data = {
        "status": status_val,
        "readiness": readiness_label,
        "s3_may_proceed": s3_may_proceed,
        "data_quality_label": overall_quality,
        "readiness_by_event": all_readiness,
    }

    return ReducedParentResultV1(
        status=status_val,
        payload=payload_data,
        event_records=all_records if all_records else [{"total_ready_events": len(all_readiness)}],
        blocked_reasons=blocked_reasons,
        evidence_refs=tuple(ev_refs) if ev_refs else ("artifacts/chunks/",),
        predecessor_bindings=tuple(pred_bindings),
    )


def reduce_s5_chunks(artifacts: Sequence[ChunkArtifactV1]) -> ReducedParentResultV1:
    """Reducer for S5 context motivation & risk."""
    all_ctx = []
    all_records = []
    for art in sorted(artifacts, key=lambda a: a.chunk_index):
        if art.status != "PASS":
            raise ReducerError(f"REDUCER_FAILED: S5 chunk {art.chunk_id} status is {art.status}")

        payload = art.payload or {}
        ctx = payload.get("context_records") or payload.get("candidates") or []
        for c in ctx:
            if isinstance(c, dict):
                all_ctx.append(c)

        ev_recs = art.event_records or payload.get("event_records") or []
        for r in ev_recs:
            if isinstance(r, dict):
                all_records.append(r)

    ev_refs, pred_bindings = _collect_common_chunk_metadata(artifacts)

    if len(artifacts) > 0 and len(all_ctx) == 0 and len(all_records) == 0:
        return ReducedParentResultV1(
            status="BLOCK",
            payload={"context_records": [], "total_candidates_screened": 0},
            event_records=all_records,
            blocked_reasons=("EMPTY_EVIDENCE_REDUCER_FAIL_CLOSED",),
            evidence_refs=tuple(ev_refs) if ev_refs else ("artifacts/chunks/",),
            predecessor_bindings=tuple(pred_bindings),
        )

    any_unacceptable = any(c.get("risk_classification") == "UNACCEPTABLE" for c in all_ctx)
    status_val = "BLOCK" if any_unacceptable else "PASS"
    blocked_reasons = ("UNACCEPTABLE_RISK_CANDIDATE",) if any_unacceptable else ()

    payload_data = {
        "status": status_val,
        "total_candidates_screened": len(all_ctx),
        "context_records": all_ctx,
        "candidates": all_ctx,
    }

    return ReducedParentResultV1(
        status=status_val,
        payload=payload_data,
        event_records=all_records if all_records else [{"total_screened": len(all_ctx)}],
        blocked_reasons=blocked_reasons,
        evidence_refs=tuple(ev_refs) if ev_refs else ("artifacts/chunks/",),
        predecessor_bindings=tuple(pred_bindings),
    )


_REDUCER_REGISTRY: dict[str, Callable[[Sequence[ChunkArtifactV1]], ReducedParentResultV1]] = {
    "S2.3": reduce_s2_3_chunks,
    "S2.5": reduce_s2_5_chunks,
    "S2.7": reduce_s2_7_chunks,
    "S2.9": reduce_s2_9_chunks,
    "S5": reduce_s5_chunks,
}


def get_reducer_for_step(step_id: str, strict: bool = False) -> Callable[[Sequence[ChunkArtifactV1]], ReducedParentResultV1] | None:
    """Get the registered reducer function for a sharded step.
    
    If strict is True and step_id is unregistered, raises KeyError.
    """
    reducer = _REDUCER_REGISTRY.get(step_id)
    if strict and not reducer:
        raise KeyError(f"UNREGISTERED_SHARDED_REDUCER: No reducer registered for step {step_id}")
    return reducer
