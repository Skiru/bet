"""Typed step reducers for sharded agent step aggregation in BET PIPELINE V5."""
from __future__ import annotations

from typing import Any, Callable, Sequence
from bet.pipeline.sharding.models import ChunkArtifactV1
from bet.pipeline.sharding.lifecycle import ChunkLifecycleError


class ReducerError(ChunkLifecycleError):
    """Raised when step-specific chunk reduction fails business or contract rules."""
    pass


def reduce_s2_3_chunks(artifacts: Sequence[ChunkArtifactV1]) -> dict[str, Any]:
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

    has_blocking_gaps = any(g.get("severity") == "HIGH" and g.get("status") == "OPEN" for g in all_gaps)
    return {
        "status": "BLOCK" if has_blocking_gaps else "PASS",
        "total_gaps_identified": len(all_gaps),
        "gaps": all_gaps,
        "event_records": all_records if all_records else [{"total_gaps": len(all_gaps)}],
        "gaps_bounded": True,
    }


def reduce_s2_5_chunks(artifacts: Sequence[ChunkArtifactV1]) -> dict[str, Any]:
    """Reducer for S2.5 provider observations (Fixes RUNTIME-01 schema mismatch)."""
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

    return {
        "status": "PASS",
        "total_observations": len(all_observations),
        "observations": all_observations,
        "provider_observations": all_observations,
        "event_records": all_records if all_records else [{"total_obs": len(all_observations)}],
    }


def reduce_s2_7_chunks(artifacts: Sequence[ChunkArtifactV1]) -> dict[str, Any]:
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

        conf = payload.get("unresolved_conflicts") or payload.get("conflicts") or []
        for c in conf:
            if isinstance(c, dict):
                all_conflicts.append(c)

        ev_recs = art.event_records or payload.get("event_records") or []
        for r in ev_recs:
            if isinstance(r, dict):
                all_records.append(r)

    has_unresolved_required_conflict = any(c.get("status") == "UNRESOLVED" and c.get("is_required", True) for c in all_conflicts)
    return {
        "status": "BLOCK" if has_unresolved_required_conflict else "PASS",
        "total_reconciled": len(all_reconciled),
        "conflicts_detected": len(all_conflicts),
        "reconciled_facts": all_reconciled,
        "unresolved_conflicts": all_conflicts,
        "event_records": all_records if all_records else [{"total_reconciled": len(all_reconciled)}],
    }


def reduce_s2_9_chunks(artifacts: Sequence[ChunkArtifactV1]) -> dict[str, Any]:
    """Reducer for S2.9 data readiness gate."""
    all_readiness = []
    all_records = []
    overall_quality = "HIGH"
    for art in sorted(artifacts, key=lambda a: a.chunk_index):
        if art.status != "PASS" and art.status != "READY":
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

        ev_recs = art.event_records or payload.get("event_records") or []
        for r in ev_recs:
            if isinstance(r, dict):
                all_records.append(r)

    any_blocked = any(r.get("readiness_tier") == "BLOCKED" for r in all_readiness)
    status_val = "BLOCK" if any_blocked else "READY"

    return {
        "status": status_val,
        "data_quality_label": overall_quality,
        "readiness_by_event": all_readiness,
        "event_records": all_records if all_records else [{"total_ready_events": len(all_readiness)}],
    }


def reduce_s5_chunks(artifacts: Sequence[ChunkArtifactV1]) -> dict[str, Any]:
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

    any_unacceptable = any(c.get("risk_classification") == "UNACCEPTABLE" for c in all_ctx)
    return {
        "status": "BLOCK" if any_unacceptable else "PASS",
        "total_candidates_screened": len(all_ctx),
        "context_records": all_ctx,
        "event_records": all_records if all_records else [{"total_screened": len(all_ctx)}],
    }


_REDUCER_REGISTRY: dict[str, Callable[[Sequence[ChunkArtifactV1]], dict[str, Any]]] = {
    "S2.3": reduce_s2_3_chunks,
    "S2.5": reduce_s2_5_chunks,
    "S2.7": reduce_s2_7_chunks,
    "S2.9": reduce_s2_9_chunks,
    "S5": reduce_s5_chunks,
}


def get_reducer_for_step(step_id: str) -> Callable[[Sequence[ChunkArtifactV1]], dict[str, Any]] | None:
    """Get the registered reducer function for a sharded step."""
    return _REDUCER_REGISTRY.get(step_id)
