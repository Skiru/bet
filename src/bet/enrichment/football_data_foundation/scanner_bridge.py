from __future__ import annotations

import argparse
import json
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bet.integration.source_result import SourceOperationResult, SourceResultStatus

from .active_enrichment import ActiveEnrichmentOrchestrator, ActiveEnrichmentRequest
from .persistence_bridge import (
    FileBackedProductionEnrichmentStore,
    PersistedCompletenessState,
    PersistedEnrichmentFact,
    PersistedScannerEvent,
    ProductionEnrichmentStore,
    ProductionStoreStateAdapter,
    persist_result_facts,
    seed_store_from_a3c1_state,
    summarize_db_schema_discovery,
)
from .scanner_contracts import ScannerEventBatch, ScannerEventCandidate

REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_OUTPUT_ROOT = (
    REPO_ROOT / "reports/football_data_foundation/production_bridge"
)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _canonical_match_identity(scanner_event: ScannerEventCandidate) -> dict[str, str]:
    return {
        "home_team": scanner_event.home_team_name,
        "away_team": scanner_event.away_team_name,
    }


@dataclass(frozen=True)
class ScannerEnrichmentRunRecord:
    profile_id: str
    scanner_event_id: str
    provider_event_id: str | None
    evidence_identity: str | None
    provider_event_ids: tuple[str, ...]
    evidence_identities: tuple[str, ...]
    facts: tuple[PersistedEnrichmentFact, ...]
    completeness_state: tuple[PersistedCompletenessState, ...]
    fetch_decisions: tuple[Mapping[str, Any], ...]
    status: str
    storage_kind: str
    db_activation_status: str
    production_betting_decision: bool
    force_refresh: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "scanner_event_id": self.scanner_event_id,
            "provider_event_id": self.provider_event_id,
            "evidence_identity": self.evidence_identity,
            "provider_event_ids": list(self.provider_event_ids),
            "evidence_identities": list(self.evidence_identities),
            "facts": [fact.to_dict() for fact in self.facts],
            "completeness_state": [
                record.to_dict() for record in self.completeness_state
            ],
            "fetch_decisions": [dict(decision) for decision in self.fetch_decisions],
            "status": self.status,
            "storage_kind": self.storage_kind,
            "db_activation_status": self.db_activation_status,
            "production_betting_decision": self.production_betting_decision,
            "force_refresh": self.force_refresh,
        }


def _source_status_for_result(
    status: str, *, facts_present: bool, force_refresh: bool
) -> tuple[SourceResultStatus, str]:
    if status == "ENRICHED_COMPLETE":
        return SourceResultStatus.SUCCESS, ""
    if status == "ENRICHED_PARTIAL":
        return SourceResultStatus.PARTIAL, "partial_enrichment"
    if force_refresh:
        return SourceResultStatus.EVIDENCE_ERROR, "fresh_evidence_required"
    if not facts_present:
        return SourceResultStatus.EVIDENCE_ERROR, "fetch_required"
    return SourceResultStatus.BLOCKED, "bridge_blocked"


def _storage_kind(store: ProductionEnrichmentStore) -> str:
    return str(getattr(store, "storage_kind", type(store).__name__))


def run_scanner_event_enrichment(
    scanner_event: ScannerEventCandidate,
    profile_id: str,
    store: ProductionEnrichmentStore,
    requested_capabilities: tuple[str, ...],
    force_refresh: bool = False,
) -> SourceOperationResult[ScannerEnrichmentRunRecord]:
    if scanner_event.profile_id != profile_id:
        raise ValueError(
            "scanner_event.profile_id must match profile_id for "
            "scanner bridge fail-closed execution"
        )

    store.upsert_scanner_event(PersistedScannerEvent.from_candidate(scanner_event))
    state_store = ProductionStoreStateAdapter(
        store, profile_id=profile_id, scanner_event_id=scanner_event.scanner_event_id
    )
    orchestrator = ActiveEnrichmentOrchestrator(state_store)
    result = orchestrator.enrich_event(
        ActiveEnrichmentRequest(
            profile_id=profile_id,
            scanner_event_candidate=scanner_event,
            canonical_match_identity=_canonical_match_identity(scanner_event),
            canonical_competition_scope=scanner_event.canonical_competition_scope,
            canonical_season_scope=scanner_event.canonical_season_scope,
            requested_capabilities=requested_capabilities,
            force_refresh=force_refresh,
        )
    )
    persisted_facts = persist_result_facts(
        store,
        scanner_event_id=scanner_event.scanner_event_id,
        facts=result.facts,
    )
    completeness_state = tuple(
        record
        for capability in requested_capabilities
        for record in [
            store.get_completeness(
                profile_id, scanner_event.scanner_event_id, capability
            )
        ]
        if record is not None
    )
    provider_event_ids = tuple(
        sorted(
            {
                fact.provider_event_id
                for fact in persisted_facts
                if fact.provider_event_id
            }
        )
    )
    evidence_identities = tuple(
        sorted(
            {
                fact.evidence_identity
                for fact in persisted_facts
                if fact.evidence_identity
            }
        )
    )
    run_record = ScannerEnrichmentRunRecord(
        profile_id=profile_id,
        scanner_event_id=scanner_event.scanner_event_id,
        provider_event_id=(
            provider_event_ids[0] if len(provider_event_ids) == 1 else None
        ),
        evidence_identity=(
            evidence_identities[0] if len(evidence_identities) == 1 else None
        ),
        provider_event_ids=provider_event_ids,
        evidence_identities=evidence_identities,
        facts=persisted_facts,
        completeness_state=completeness_state,
        fetch_decisions=tuple(asdict(decision) for decision in result.fetch_decisions),
        status=result.status,
        storage_kind=_storage_kind(store),
        db_activation_status=summarize_db_schema_discovery()["activation_decision"]["status"],
        production_betting_decision=False,
        force_refresh=force_refresh,
    )
    source_status, error_code = _source_status_for_result(
        result.status, facts_present=bool(persisted_facts), force_refresh=force_refresh
    )
    return SourceOperationResult(
        status=source_status,
        value=run_record,
        provider="scanner-bridge",
        operation="scanner_event_enrichment",
        request_identity=(
            f"{profile_id}:{scanner_event.scanner_event_id}:{','.join(requested_capabilities)}:"
            f"{'force' if force_refresh else 'normal'}"
        ),
        retrieved_at=datetime.now(UTC),
        error_code=error_code,
        parser_diagnostics={
            "storage_kind": _storage_kind(store),
            "requested_capabilities": list(requested_capabilities),
            "fetch_decisions": [
                asdict(decision) for decision in result.fetch_decisions
            ],
            "production_betting_decision": False,
            "db_activation_status": summarize_db_schema_discovery()[
                "activation_decision"
            ]["status"],
        },
        schema_fingerprint=(
            persisted_facts[0].schema_fingerprint if persisted_facts else ""
        ),
    )


def run_scanner_batch_enrichment(
    batch: ScannerEventBatch,
    store: ProductionEnrichmentStore,
    requested_capabilities: tuple[str, ...],
    force_refresh: bool = False,
) -> tuple[SourceOperationResult[ScannerEnrichmentRunRecord], ...]:
    return tuple(
        run_scanner_event_enrichment(
            scanner_event,
            batch.profile_id,
            store,
            requested_capabilities=requested_capabilities,
            force_refresh=force_refresh,
        )
        for scanner_event in batch.events
    )


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _load_scanner_event(path: Path) -> ScannerEventCandidate:
    return ScannerEventCandidate.from_dict(json.loads(path.read_text(encoding="utf-8")))


def _build_store(
    base_dir: Path, store_kind: str
) -> FileBackedProductionEnrichmentStore:
    if store_kind != "temp":
        raise ValueError(
            "A4 scanner bridge supports only --store-kind temp in this phase"
        )
    return FileBackedProductionEnrichmentStore(base_dir, storage_kind=store_kind)


def _reset_dir(path: Path) -> None:
    if not path.name.startswith(".temp_store_"):
        raise ValueError(
            "scanner bridge cleanup is limited to dedicated .temp_store_* directories"
        )
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def _record_json(
    result: SourceOperationResult[ScannerEnrichmentRunRecord],
) -> dict[str, Any]:
    return {
        "source_result_status": result.status.value,
        "error_code": result.error_code,
        "request_identity": result.request_identity,
        "provider": result.provider,
        "operation": result.operation,
        "retrieved_at": (
            result.retrieved_at.isoformat() if result.retrieved_at else None
        ),
        "parser_diagnostics": dict(result.parser_diagnostics),
        "result": result.value.to_dict() if result.value else None,
    }


def _summary_lines(
    *,
    profile_id: str,
    empty_store: dict[str, Any],
    reuse_store: dict[str, Any],
    force_refresh: dict[str, Any],
) -> list[str]:
    return [
        f"# Scanner Enrichment Summary - {profile_id}",
        "",
        f"- Generated at UTC: `{_utc_now()}`",
        (
            "- Store kind: `temp` (file-backed temporary acceptance store; "
            "no production DB writes)"
        ),
        "- Production DB activation: `DB_ACTIVATION_DEFERRED`",
        "- Production betting decision: `false`",
        "",
        "## Empty store",
        f"- Source status: `{empty_store['source_result_status']}`",
        f"- Bridge status: `{empty_store['result']['status']}`",
        f"- Facts persisted: `{len(empty_store['result']['facts'])}`",
        "",
        "## Reuse store",
        f"- Source status: `{reuse_store['source_result_status']}`",
        f"- Bridge status: `{reuse_store['result']['status']}`",
        f"- Facts persisted: `{len(reuse_store['result']['facts'])}`",
        f"- Provider event id: `{reuse_store['result']['provider_event_id']}`",
        "",
        "## Force refresh",
        f"- Source status: `{force_refresh['source_result_status']}`",
        f"- Bridge status: `{force_refresh['result']['status']}`",
        f"- Facts persisted: `{len(force_refresh['result']['facts'])}`",
        "- Fresh evidence remains deferred without a live fetcher in this phase.",
    ]


def run_scanner_enrich_dry_run(args: argparse.Namespace) -> None:
    scanner_event = _load_scanner_event(Path(args.scanner_event_file))
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    requested_capabilities = (
        "current_discovery",
        "detailed_metrics",
        "current_form",
    )

    empty_store_dir = output_dir / ".temp_store_empty"
    _reset_dir(empty_store_dir)
    empty_store = _build_store(empty_store_dir, args.store_kind)
    empty_result = run_scanner_event_enrichment(
        scanner_event,
        args.profile_id,
        empty_store,
        requested_capabilities=requested_capabilities,
        force_refresh=False,
    )
    empty_payload = _record_json(empty_result)
    _write_json(output_dir / "scanner_enrich_empty_store.json", empty_payload)

    reuse_store_dir = output_dir / ".temp_store_reuse"
    _reset_dir(reuse_store_dir)
    reuse_store = _build_store(reuse_store_dir, args.store_kind)
    seed_store_from_a3c1_state(
        reuse_store,
        profile_id=args.profile_id,
        scanner_event_id=scanner_event.scanner_event_id,
    )
    reuse_result = run_scanner_event_enrichment(
        scanner_event,
        args.profile_id,
        reuse_store,
        requested_capabilities=requested_capabilities,
        force_refresh=False,
    )
    reuse_payload = _record_json(reuse_result)
    _write_json(output_dir / "scanner_enrich_reuse_store.json", reuse_payload)

    force_store_dir = output_dir / ".temp_store_force_refresh"
    _reset_dir(force_store_dir)
    force_store = _build_store(force_store_dir, args.store_kind)
    seed_store_from_a3c1_state(
        force_store,
        profile_id=args.profile_id,
        scanner_event_id=scanner_event.scanner_event_id,
    )
    force_result = run_scanner_event_enrichment(
        scanner_event,
        args.profile_id,
        force_store,
        requested_capabilities=requested_capabilities,
        force_refresh=True,
    )
    force_payload = _record_json(force_result)
    _write_json(output_dir / "scanner_enrich_force_refresh.json", force_payload)

    summary_path = output_dir / "scanner_enrich_summary.md"
    summary_path.write_text(
        "\n".join(
            _summary_lines(
                profile_id=args.profile_id,
                empty_store=empty_payload,
                reuse_store=reuse_payload,
                force_refresh=force_payload,
            )
        )
        + "\n",
        encoding="utf-8",
    )


def scanner_batch_from_events(
    profile_id: str, events: Sequence[ScannerEventCandidate]
) -> ScannerEventBatch:
    return ScannerEventBatch(
        profile_id=profile_id,
        generated_at=_utc_now(),
        events=tuple(events),
    )
