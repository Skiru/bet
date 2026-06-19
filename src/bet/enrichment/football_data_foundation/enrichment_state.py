from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class EnrichmentCapabilityRequirement:
    capability: str
    required_for_profile: bool
    freshness_ttl_seconds: int | None
    heavy_fetch: bool
    provider_priority: tuple[str, ...]


@dataclass(frozen=True)
class EnrichmentCompletenessRecord:
    profile_id: str
    canonical_entity_id: str
    entity_type: str
    capability: str
    provider_id: str
    evidence_identity: str | None
    schema_fingerprint: str | None
    last_verified_at: str | None
    last_enriched_at: str | None
    completeness_status: str
    stale_reason: str | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> EnrichmentCompletenessRecord:
        return cls(
            profile_id=str(data["profile_id"]),
            canonical_entity_id=str(data["canonical_entity_id"]),
            entity_type=str(data["entity_type"]),
            capability=str(data["capability"]),
            provider_id=str(data["provider_id"]),
            evidence_identity=data.get("evidence_identity"),
            schema_fingerprint=data.get("schema_fingerprint"),
            last_verified_at=data.get("last_verified_at"),
            last_enriched_at=data.get("last_enriched_at"),
            completeness_status=str(data["completeness_status"]),
            stale_reason=data.get("stale_reason"),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FetchDecision:
    capability: str
    decision: str
    reason: str
    provider_priority: tuple[str, ...]
    force_refresh: bool


class EnrichmentStateStore(Protocol):
    def get_completeness(
        self, profile_id: str, entity_id: str, capability: str
    ) -> EnrichmentCompletenessRecord | None: ...

    def put_completeness(self, record: EnrichmentCompletenessRecord) -> None: ...

    def get_evidence(self, evidence_identity: str) -> Mapping[str, Any] | None: ...

    def put_evidence(
        self, evidence_identity: str, payload: Mapping[str, Any]
    ) -> None: ...


class FileEnrichmentStateStore:
    """File-backed EnrichmentStateStore implementation for tests and reports."""

    def __init__(self, base_dir: Path | str) -> None:
        self.base_dir = Path(base_dir)
        self.completeness_dir = self.base_dir / "completeness"
        self.evidence_dir = self.base_dir / "evidence"
        self.completeness_dir.mkdir(parents=True, exist_ok=True)
        self.evidence_dir.mkdir(parents=True, exist_ok=True)

    def _completeness_path(
        self, profile_id: str, entity_id: str, capability: str
    ) -> Path:
        filename = f"{profile_id}_{entity_id}_{capability}.json".replace(
            ":", "_"
        ).replace("/", "_")
        return self.completeness_dir / filename

    def _evidence_path(self, evidence_identity: str) -> Path:
        return self.evidence_dir / f"{evidence_identity}.json"

    def get_completeness(
        self, profile_id: str, entity_id: str, capability: str
    ) -> EnrichmentCompletenessRecord | None:
        path = self._completeness_path(profile_id, entity_id, capability)
        if not path.is_file():
            return None
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            return EnrichmentCompletenessRecord.from_dict(data)
        except Exception:
            return None

    def put_completeness(self, record: EnrichmentCompletenessRecord) -> None:
        path = self._completeness_path(
            record.profile_id, record.canonical_entity_id, record.capability
        )
        with open(path, "w", encoding="utf-8") as f:
            json.dump(record.to_dict(), f, indent=2, sort_keys=True)

    def get_evidence(self, evidence_identity: str) -> Mapping[str, Any] | None:
        path = self._evidence_path(evidence_identity)
        if not path.is_file():
            return None
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def put_evidence(self, evidence_identity: str, payload: Mapping[str, Any]) -> None:
        path = self._evidence_path(evidence_identity)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(dict(payload), f, indent=2, sort_keys=True)


def make_fetch_decision(
    requirement: EnrichmentCapabilityRequirement,
    completeness: EnrichmentCompletenessRecord | None,
    force_refresh: bool = False,
) -> FetchDecision:
    """Evaluate completeness state to determine active enrichment fetch action."""
    capability = requirement.capability

    if force_refresh:
        return FetchDecision(
            capability=capability,
            decision="FETCH_FORCED",
            reason="Explicit force_refresh flag requested.",
            provider_priority=requirement.provider_priority,
            force_refresh=True,
        )

    if completeness is None:
        decision = (
            "FETCH_REQUIRED" if requirement.required_for_profile else "FETCH_OPTIONAL"
        )
        return FetchDecision(
            capability=capability,
            decision=decision,
            reason=f"No completeness record exists for capability {capability}.",
            provider_priority=requirement.provider_priority,
            force_refresh=False,
        )

    status = completeness.completeness_status

    if status == "PROVIDER_UNSUPPORTED":
        return FetchDecision(
            capability=capability,
            decision="SKIP_UNSUPPORTED",
            reason="Capability or provider marked as unsupported for this profile.",
            provider_priority=(),
            force_refresh=False,
        )

    if status == "COMPLETE_FRESH":
        return FetchDecision(
            capability=capability,
            decision="REUSE_CACHED",
            reason="Completeness record is fresh and clean.",
            provider_priority=requirement.provider_priority,
            force_refresh=False,
        )

    if status == "COMPLETE_STALE":
        decision = (
            "FETCH_REQUIRED" if requirement.required_for_profile else "FETCH_OPTIONAL"
        )
        return FetchDecision(
            capability=capability,
            decision=decision,
            reason=completeness.stale_reason or "Completeness record is stale.",
            provider_priority=requirement.provider_priority,
            force_refresh=False,
        )

    if status == "MISSING" or status == "UNKNOWN":
        decision = (
            "FETCH_REQUIRED" if requirement.required_for_profile else "FETCH_OPTIONAL"
        )
        return FetchDecision(
            capability=capability,
            decision=decision,
            reason="Capability state is missing/unknown.",
            provider_priority=requirement.provider_priority,
            force_refresh=False,
        )

    if status == "PARTIAL":
        return FetchDecision(
            capability=capability,
            decision="VERIFY_LIGHT_ONLY",
            reason="Capability has partial evidence; verify light identity/freshness only.",
            provider_priority=requirement.provider_priority,
            force_refresh=False,
        )

    if status == "SCHEMA_DRIFT":
        return FetchDecision(
            capability=capability,
            decision="BLOCKED",
            reason="Schema drift detected; fetch blocked to prevent corruption.",
            provider_priority=(),
            force_refresh=False,
        )

    return FetchDecision(
        capability=capability,
        decision="BLOCKED",
        reason=f"Safety guard: unhandled completeness status '{status}'.",
        provider_priority=(),
        force_refresh=False,
    )
