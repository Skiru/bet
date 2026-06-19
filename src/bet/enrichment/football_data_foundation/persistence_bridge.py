from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, Protocol

from .active_enrichment import EnrichmentFact
from .enrichment_state import EnrichmentCompletenessRecord, EnrichmentStateStore
from .scanner_contracts import ScannerEventCandidate

REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_PROFILE_REPORT_ROOT = (
    REPO_ROOT / "reports/football_data_foundation/active_enrichment_profiles"
)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _json_dump(path: Path, payload: Mapping[str, Any] | list[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _json_load(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_key(*parts: str) -> str:
    return "__".join(
        re.sub(r"[^A-Za-z0-9._-]", "_", part)
        for part in parts
    )


def _fact_identity(
    *,
    scanner_event_id: str,
    capability: str,
    fact_name: str,
    evidence_identity: str,
    provider_event_id: str | None,
) -> str:
    seed = "|".join(
        [
            scanner_event_id,
            capability,
            fact_name,
            evidence_identity,
            provider_event_id or "",
        ]
    )
    return sha256(seed.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PersistedScannerEvent:
    scanner_event_id: str
    profile_id: str
    sport: str
    competition_scope: str
    season_scope: str
    kickoff_utc: str
    home_team_name: str
    away_team_name: str
    scanner_source: str
    scanner_confidence: str
    created_at: str
    kickoff_local: str | None = None
    home_team_code: str | None = None
    away_team_code: str | None = None
    group_label: str | None = None
    scanner_truth_kind: str | None = None
    raw_refs: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_candidate(
        cls, candidate: ScannerEventCandidate, created_at: str | None = None
    ) -> PersistedScannerEvent:
        return cls(
            scanner_event_id=candidate.scanner_event_id,
            profile_id=candidate.profile_id,
            sport=candidate.sport,
            competition_scope=candidate.canonical_competition_scope,
            season_scope=candidate.canonical_season_scope,
            kickoff_utc=candidate.kickoff_utc,
            home_team_name=candidate.home_team_name,
            away_team_name=candidate.away_team_name,
            scanner_source=candidate.scanner_source,
            scanner_confidence=candidate.scanner_confidence,
            created_at=created_at or _utc_now(),
            kickoff_local=candidate.kickoff_local,
            home_team_code=candidate.home_team_code,
            away_team_code=candidate.away_team_code,
            group_label=candidate.group_label,
            scanner_truth_kind=candidate.scanner_truth_kind,
            raw_refs=candidate.raw_refs,
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> PersistedScannerEvent:
        return cls(
            scanner_event_id=str(payload["scanner_event_id"]),
            profile_id=str(payload["profile_id"]),
            sport=str(payload["sport"]),
            competition_scope=str(payload["competition_scope"]),
            season_scope=str(payload["season_scope"]),
            kickoff_utc=str(payload["kickoff_utc"]),
            home_team_name=str(payload["home_team_name"]),
            away_team_name=str(payload["away_team_name"]),
            scanner_source=str(payload["scanner_source"]),
            scanner_confidence=str(payload["scanner_confidence"]),
            created_at=str(payload["created_at"]),
            kickoff_local=payload.get("kickoff_local"),
            home_team_code=payload.get("home_team_code"),
            away_team_code=payload.get("away_team_code"),
            group_label=payload.get("group_label"),
            scanner_truth_kind=payload.get("scanner_truth_kind"),
            raw_refs=tuple(payload.get("raw_refs") or []),
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["raw_refs"] = list(self.raw_refs)
        return payload


@dataclass(frozen=True)
class PersistedEnrichmentEvidence:
    evidence_identity: str
    profile_id: str
    provider_id: str
    provider_event_id: str
    scanner_event_id: str
    capability: str
    schema_fingerprint: str
    retrieved_at: str
    source_truth_kind: str
    storage_ref: str
    raw_payload_stored: bool = False

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> PersistedEnrichmentEvidence:
        return cls(
            evidence_identity=str(payload["evidence_identity"]),
            profile_id=str(payload["profile_id"]),
            provider_id=str(payload["provider_id"]),
            provider_event_id=str(payload["provider_event_id"]),
            scanner_event_id=str(payload["scanner_event_id"]),
            capability=str(payload["capability"]),
            schema_fingerprint=str(payload["schema_fingerprint"]),
            retrieved_at=str(payload["retrieved_at"]),
            source_truth_kind=str(payload["source_truth_kind"]),
            storage_ref=str(payload["storage_ref"]),
            raw_payload_stored=bool(payload.get("raw_payload_stored", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PersistedEnrichmentFact:
    fact_id: str
    evidence_identity: str
    scanner_event_id: str
    provider_event_id: str | None
    profile_id: str
    capability: str
    fact_name: str
    fact_value_num: float | None
    fact_value_text: str | None
    source_consensus: str
    schema_fingerprint: str
    created_at: str

    @classmethod
    def from_enrichment_fact(
        cls,
        fact: EnrichmentFact,
        *,
        scanner_event_id: str,
        created_at: str | None = None,
    ) -> PersistedEnrichmentFact:
        return cls(
            fact_id=_fact_identity(
                scanner_event_id=scanner_event_id,
                capability=fact.capability,
                fact_name=fact.fact_name,
                evidence_identity=fact.evidence_identity,
                provider_event_id=fact.provider_event_id,
            ),
            evidence_identity=fact.evidence_identity,
            scanner_event_id=scanner_event_id,
            provider_event_id=fact.provider_event_id,
            profile_id=fact.profile_id,
            capability=fact.capability,
            fact_name=fact.fact_name,
            fact_value_num=fact.fact_value_num,
            fact_value_text=fact.fact_value_text,
            source_consensus=fact.source_consensus,
            schema_fingerprint=fact.schema_fingerprint,
            created_at=created_at or _utc_now(),
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> PersistedEnrichmentFact:
        return cls(
            fact_id=str(payload["fact_id"]),
            evidence_identity=str(payload["evidence_identity"]),
            scanner_event_id=str(payload["scanner_event_id"]),
            provider_event_id=payload.get("provider_event_id"),
            profile_id=str(payload["profile_id"]),
            capability=str(payload["capability"]),
            fact_name=str(payload["fact_name"]),
            fact_value_num=payload.get("fact_value_num"),
            fact_value_text=payload.get("fact_value_text"),
            source_consensus=str(payload["source_consensus"]),
            schema_fingerprint=str(payload["schema_fingerprint"]),
            created_at=str(payload["created_at"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PersistedCompletenessState:
    profile_id: str
    scanner_event_id: str
    entity_type: str
    capability: str
    provider_id: str
    completeness_status: str
    evidence_identity: str | None
    schema_fingerprint: str | None
    last_verified_at: str | None
    last_enriched_at: str | None
    stale_reason: str | None = None

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> PersistedCompletenessState:
        return cls(
            profile_id=str(payload["profile_id"]),
            scanner_event_id=str(payload["scanner_event_id"]),
            entity_type=str(payload["entity_type"]),
            capability=str(payload["capability"]),
            provider_id=str(payload["provider_id"]),
            completeness_status=str(payload["completeness_status"]),
            evidence_identity=payload.get("evidence_identity"),
            schema_fingerprint=payload.get("schema_fingerprint"),
            last_verified_at=payload.get("last_verified_at"),
            last_enriched_at=payload.get("last_enriched_at"),
            stale_reason=payload.get("stale_reason"),
        )

    @classmethod
    def from_enrichment_record(
        cls, record: EnrichmentCompletenessRecord, *, scanner_event_id: str
    ) -> PersistedCompletenessState:
        return cls(
            profile_id=record.profile_id,
            scanner_event_id=scanner_event_id,
            entity_type=record.entity_type,
            capability=record.capability,
            provider_id=record.provider_id,
            completeness_status=record.completeness_status,
            evidence_identity=record.evidence_identity,
            schema_fingerprint=record.schema_fingerprint,
            last_verified_at=record.last_verified_at,
            last_enriched_at=record.last_enriched_at,
            stale_reason=record.stale_reason,
        )

    def to_enrichment_record(self) -> EnrichmentCompletenessRecord:
        return EnrichmentCompletenessRecord(
            profile_id=self.profile_id,
            canonical_entity_id=self.scanner_event_id,
            entity_type=self.entity_type,
            capability=self.capability,
            provider_id=self.provider_id,
            evidence_identity=self.evidence_identity,
            schema_fingerprint=self.schema_fingerprint,
            last_verified_at=self.last_verified_at,
            last_enriched_at=self.last_enriched_at,
            completeness_status=self.completeness_status,
            stale_reason=self.stale_reason,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ProductionEnrichmentStore(Protocol):
    def upsert_scanner_event(self, candidate: PersistedScannerEvent) -> None: ...

    def get_scanner_event(
        self, scanner_event_id: str
    ) -> PersistedScannerEvent | None: ...

    def upsert_evidence(self, record: PersistedEnrichmentEvidence) -> None: ...

    def get_evidence(
        self, evidence_identity: str
    ) -> PersistedEnrichmentEvidence | None: ...

    def upsert_fact(self, fact: PersistedEnrichmentFact) -> None: ...

    def list_facts(
        self, scanner_event_id: str, capability: str | None = None
    ) -> tuple[PersistedEnrichmentFact, ...]: ...

    def upsert_completeness(self, record: PersistedCompletenessState) -> None: ...

    def get_completeness(
        self, profile_id: str, scanner_event_id: str, capability: str
    ) -> PersistedCompletenessState | None: ...


class InMemoryProductionEnrichmentStore:
    storage_kind = "temp"

    def __init__(self) -> None:
        self._scanner_events: dict[str, PersistedScannerEvent] = {}
        self._evidence: dict[str, PersistedEnrichmentEvidence] = {}
        self._evidence_payloads: dict[str, dict[str, Any]] = {}
        self._facts: dict[str, PersistedEnrichmentFact] = {}
        self._completeness: dict[tuple[str, str, str], PersistedCompletenessState] = {}

    def upsert_scanner_event(self, candidate: PersistedScannerEvent) -> None:
        self._scanner_events[candidate.scanner_event_id] = candidate

    def get_scanner_event(self, scanner_event_id: str) -> PersistedScannerEvent | None:
        return self._scanner_events.get(scanner_event_id)

    def upsert_evidence(self, record: PersistedEnrichmentEvidence) -> None:
        self._evidence[record.evidence_identity] = record

    def get_evidence(
        self, evidence_identity: str
    ) -> PersistedEnrichmentEvidence | None:
        return self._evidence.get(evidence_identity)

    def store_evidence_payload(
        self, evidence_identity: str, payload: Mapping[str, Any]
    ) -> str:
        self._evidence_payloads[evidence_identity] = dict(payload)
        return f"memory://evidence/{evidence_identity}.json"

    def get_evidence_payload(self, evidence_identity: str) -> dict[str, Any] | None:
        payload = self._evidence_payloads.get(evidence_identity)
        if payload is None:
            return None
        return dict(payload)

    def upsert_fact(self, fact: PersistedEnrichmentFact) -> None:
        self._facts[fact.fact_id] = fact

    def list_facts(
        self, scanner_event_id: str, capability: str | None = None
    ) -> tuple[PersistedEnrichmentFact, ...]:
        facts = [
            fact
            for fact in self._facts.values()
            if fact.scanner_event_id == scanner_event_id
            and (capability is None or fact.capability == capability)
        ]
        facts.sort(key=lambda item: (item.capability, item.fact_name, item.fact_id))
        return tuple(facts)

    def upsert_completeness(self, record: PersistedCompletenessState) -> None:
        key = (record.profile_id, record.scanner_event_id, record.capability)
        self._completeness[key] = record

    def get_completeness(
        self, profile_id: str, scanner_event_id: str, capability: str
    ) -> PersistedCompletenessState | None:
        return self._completeness.get((profile_id, scanner_event_id, capability))


class FileBackedProductionEnrichmentStore:
    storage_kind = "report"

    def __init__(self, base_dir: Path | str, *, storage_kind: str = "report") -> None:
        self.base_dir = Path(base_dir)
        self.storage_kind = storage_kind
        self.scanner_events_dir = self.base_dir / "scanner_events"
        self.evidence_dir = self.base_dir / "evidence"
        self.evidence_payload_dir = self.base_dir / "evidence_payloads"
        self.facts_dir = self.base_dir / "facts"
        self.completeness_dir = self.base_dir / "completeness"
        for directory in (
            self.scanner_events_dir,
            self.evidence_dir,
            self.evidence_payload_dir,
            self.facts_dir,
            self.completeness_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    def _scanner_event_path(self, scanner_event_id: str) -> Path:
        return self.scanner_events_dir / f"{_safe_key(scanner_event_id)}.json"

    def _evidence_path(self, evidence_identity: str) -> Path:
        return self.evidence_dir / f"{evidence_identity}.json"

    def _payload_path(self, evidence_identity: str) -> Path:
        return self.evidence_payload_dir / f"{evidence_identity}.json"

    def _fact_path(self, fact_id: str) -> Path:
        return self.facts_dir / f"{fact_id}.json"

    def _completeness_path(
        self, profile_id: str, scanner_event_id: str, capability: str
    ) -> Path:
        filename = f"{_safe_key(profile_id, scanner_event_id, capability)}.json"
        return self.completeness_dir / filename

    def upsert_scanner_event(self, candidate: PersistedScannerEvent) -> None:
        _json_dump(
            self._scanner_event_path(candidate.scanner_event_id),
            candidate.to_dict(),
        )

    def get_scanner_event(self, scanner_event_id: str) -> PersistedScannerEvent | None:
        payload = _json_load(self._scanner_event_path(scanner_event_id))
        if payload is None:
            return None
        return PersistedScannerEvent.from_dict(payload)

    def upsert_evidence(self, record: PersistedEnrichmentEvidence) -> None:
        _json_dump(self._evidence_path(record.evidence_identity), record.to_dict())

    def get_evidence(
        self, evidence_identity: str
    ) -> PersistedEnrichmentEvidence | None:
        payload = _json_load(self._evidence_path(evidence_identity))
        if payload is None:
            return None
        return PersistedEnrichmentEvidence.from_dict(payload)

    def store_evidence_payload(
        self, evidence_identity: str, payload: Mapping[str, Any]
    ) -> str:
        payload_path = self._payload_path(evidence_identity)
        _json_dump(payload_path, dict(payload))
        return str(payload_path.relative_to(self.base_dir))

    def get_evidence_payload(self, evidence_identity: str) -> dict[str, Any] | None:
        payload = _json_load(self._payload_path(evidence_identity))
        if payload is None:
            return None
        return payload

    def upsert_fact(self, fact: PersistedEnrichmentFact) -> None:
        _json_dump(self._fact_path(fact.fact_id), fact.to_dict())

    def list_facts(
        self, scanner_event_id: str, capability: str | None = None
    ) -> tuple[PersistedEnrichmentFact, ...]:
        facts: list[PersistedEnrichmentFact] = []
        for path in sorted(self.facts_dir.glob("*.json")):
            payload = _json_load(path)
            if payload is None:
                continue
            fact = PersistedEnrichmentFact.from_dict(payload)
            if fact.scanner_event_id != scanner_event_id:
                continue
            if capability is not None and fact.capability != capability:
                continue
            facts.append(fact)
        facts.sort(key=lambda item: (item.capability, item.fact_name, item.fact_id))
        return tuple(facts)

    def upsert_completeness(self, record: PersistedCompletenessState) -> None:
        _json_dump(
            self._completeness_path(
                record.profile_id, record.scanner_event_id, record.capability
            ),
            record.to_dict(),
        )

    def get_completeness(
        self, profile_id: str, scanner_event_id: str, capability: str
    ) -> PersistedCompletenessState | None:
        payload = _json_load(
            self._completeness_path(profile_id, scanner_event_id, capability)
        )
        if payload is None:
            return None
        return PersistedCompletenessState.from_dict(payload)


class ProductionStoreStateAdapter(EnrichmentStateStore):
    def __init__(
        self,
        store: ProductionEnrichmentStore,
        *,
        profile_id: str,
        scanner_event_id: str,
    ) -> None:
        self.store = store
        self.profile_id = profile_id
        self.scanner_event_id = scanner_event_id

    def get_completeness(
        self, profile_id: str, entity_id: str, capability: str
    ) -> EnrichmentCompletenessRecord | None:
        record = self.store.get_completeness(profile_id, entity_id, capability)
        if record is None:
            return None
        return record.to_enrichment_record()

    def put_completeness(self, record: EnrichmentCompletenessRecord) -> None:
        self.store.upsert_completeness(
            PersistedCompletenessState.from_enrichment_record(
                record, scanner_event_id=self.scanner_event_id
            )
        )

    def get_evidence(self, evidence_identity: str) -> Mapping[str, Any] | None:
        record = self.store.get_evidence(evidence_identity)
        if record is None:
            return None
        payload = self._get_payload(evidence_identity)
        if payload is None:
            return None
        merged = dict(payload)
        merged.setdefault("provider_id", record.provider_id)
        merged.setdefault("provider_event_id", record.provider_event_id)
        merged.setdefault("evidence_identity", record.evidence_identity)
        merged.setdefault("schema_fingerprint", record.schema_fingerprint)
        merged.setdefault("retrieved_at", record.retrieved_at)
        merged.setdefault("capability", record.capability)
        return merged

    def put_evidence(self, evidence_identity: str, payload: Mapping[str, Any]) -> None:
        provider_id = str(payload.get("provider_id") or "")
        event = payload.get("event") or {}
        existing_record = self.store.get_evidence(evidence_identity)
        capability = str(
            payload.get("capability")
            or (existing_record.capability if existing_record is not None else "")
        )
        provider_event_id = str(
            payload.get("provider_event_id")
            or event.get("provider_event_id")
            or event.get("id")
            or ""
        )
        retrieved_at = str(
            payload.get("retrieved_at")
            or event.get("retrieval_timestamp_utc")
            or _utc_now()
        )
        storage_ref = self._store_payload(evidence_identity, payload)
        self.store.upsert_evidence(
            PersistedEnrichmentEvidence(
                evidence_identity=evidence_identity,
                profile_id=self.profile_id,
                provider_id=provider_id,
                provider_event_id=provider_event_id,
                scanner_event_id=self.scanner_event_id,
                capability=capability,
                schema_fingerprint=str(payload.get("schema_fingerprint") or ""),
                retrieved_at=retrieved_at,
                source_truth_kind=str(
                    payload.get("source_truth_kind") or "provider_verified_payload"
                ),
                storage_ref=storage_ref,
                raw_payload_stored=False,
            )
        )

    def _store_payload(self, evidence_identity: str, payload: Mapping[str, Any]) -> str:
        store_payload = getattr(self.store, "store_evidence_payload", None)
        if callable(store_payload):
            return str(store_payload(evidence_identity, payload))
        raise TypeError("store does not support evidence payload persistence")

    def _get_payload(self, evidence_identity: str) -> dict[str, Any] | None:
        get_payload = getattr(self.store, "get_evidence_payload", None)
        if callable(get_payload):
            payload = get_payload(evidence_identity)
            if payload is None:
                return None
            return dict(payload)
        raise TypeError("store does not support evidence payload lookup")


def persist_result_facts(
    store: ProductionEnrichmentStore,
    *,
    scanner_event_id: str,
    facts: tuple[EnrichmentFact, ...],
    created_at: str | None = None,
) -> tuple[PersistedEnrichmentFact, ...]:
    persisted = tuple(
        PersistedEnrichmentFact.from_enrichment_fact(
            fact, scanner_event_id=scanner_event_id, created_at=created_at
        )
        for fact in facts
    )
    for fact in persisted:
        store.upsert_fact(fact)
    return persisted


def summarize_db_schema_discovery(repo_root: Path | None = None) -> dict[str, Any]:
    root = repo_root or REPO_ROOT
    return {
        "repo_root": str(root),
        "production_sqlite_convention": {
            "status": "SUPPORTED_IN_CODE",
            "db_path_config": "betting/data/betting.db",
            "db_path_exists_locally": (root / "betting/data/betting.db").is_file(),
            "schema_module": "src/bet/db/schema.py",
            "migration_dir": "src/bet/db/migrations",
        },
        "scanner_event_storage_candidates": [
            "fixture_sources",
            "source_entity_reference",
        ],
        "fixture_source_mapping_tables": [
            "fixture_sources",
            "source_entity_reference",
        ],
        "enrichment_fact_tables": [
            "team_form",
            "match_stats",
            "fixture_capability_observation",
            "fixture_capability_projection",
            "analysis_snapshot",
        ],
        "evidence_reference_tables": [
            "evidence_package_revision",
            "source_operation_attempt",
            "fixture_capability_observation",
        ],
        "pipeline_scripts": {
            "s1_scanner": [
                "scripts/pipeline_steps/s1_discover.py",
                "scripts/discover_events.py",
                "scripts/build_shortlist.py",
            ],
            "s3_enrichment_stats": [
                "scripts/pipeline_steps/s3_stats.py",
                "scripts/deep_stats_report.py",
            ],
            "s5_context_gate": [
                "scripts/pipeline_steps/s5_gate.py",
                "scripts/pipeline_steps/s7_validate.py",
            ],
        },
        "migration_convention": {
            "status": "EXISTS",
            "entrypoint": "src/bet/db/schema.py",
            "latest_discovered_schema_version": 20,
        },
        "activation_decision": {
            "status": "DB_ACTIVATION_DEFERRED",
            "safe_existing_table_mapping": False,
            "reason": (
                "Existing persisted entities are canonical-fixture/team scoped "
                "and require integer canonical IDs, while A4 starts from "
                "scanner_event_id before safe canonical fixture assignment "
                "exists. Reusing those tables would invent "
                "production schema semantics or hidden mappings."
            ),
            "safe_current_adapter": (
                "FileBackedProductionEnrichmentStore and "
                "InMemoryProductionEnrichmentStore only"
            ),
        },
    }


def default_seed_state_root(profile_id: str) -> Path:
    return DEFAULT_PROFILE_REPORT_ROOT / profile_id / "state_store"


def seed_store_from_a3c1_state(
    store: ProductionEnrichmentStore,
    *,
    profile_id: str,
    scanner_event_id: str,
    state_root: Path | None = None,
) -> dict[str, Any]:
    root = state_root or default_seed_state_root(profile_id)
    completeness_dir = root / "completeness"
    evidence_dir = root / "evidence"
    completeness_records: list[PersistedCompletenessState] = []
    evidence_by_identity: dict[str, tuple[str, str]] = {}
    for path in sorted(completeness_dir.glob("*.json")):
        payload = _json_load(path)
        if payload is None:
            continue
        record = PersistedCompletenessState(
            profile_id=str(payload["profile_id"]),
            scanner_event_id=str(
                payload.get("canonical_entity_id") or scanner_event_id
            ),
            entity_type=str(payload["entity_type"]),
            capability=str(payload["capability"]),
            provider_id=str(payload["provider_id"]),
            completeness_status=str(payload["completeness_status"]),
            evidence_identity=payload.get("evidence_identity"),
            schema_fingerprint=payload.get("schema_fingerprint"),
            last_verified_at=payload.get("last_verified_at"),
            last_enriched_at=payload.get("last_enriched_at"),
            stale_reason=payload.get("stale_reason"),
        )
        store.upsert_completeness(record)
        completeness_records.append(record)
        if record.evidence_identity:
            evidence_by_identity[record.evidence_identity] = (
                record.capability,
                record.provider_id,
            )

    adapter = ProductionStoreStateAdapter(
        store, profile_id=profile_id, scanner_event_id=scanner_event_id
    )
    seeded_evidence = 0
    for evidence_identity, (capability, provider_id) in sorted(
        evidence_by_identity.items()
    ):
        payload = _json_load(evidence_dir / f"{evidence_identity}.json")
        if payload is None:
            continue
        payload.setdefault("capability", capability)
        payload.setdefault("provider_id", provider_id)
        adapter.put_evidence(evidence_identity, payload)
        seeded_evidence += 1

    return {
        "seed_state_root": str(root),
        "seeded_completeness": len(completeness_records),
        "seeded_evidence": seeded_evidence,
    }
