from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from .competition_profiles import get_competition_profile
from .endpoint_verification import validate_evidence_identity
from .enrichment_state import (
    EnrichmentCapabilityRequirement,
    EnrichmentCompletenessRecord,
    EnrichmentStateStore,
    FetchDecision,
    make_fetch_decision,
)
from .event_identity import IdentitySeed, ProviderEventIdentity, match_identities
from .scanner_contracts import ScannerEventCandidate

ALLOWED_DETAILED_METRICS = {
    "possessionPct",
    "totalShots",
    "shotsOnTarget",
    "wonCorners",
    "foulsCommitted",
    "totalGoals",
}


@dataclass(frozen=True)
class ActiveEnrichmentRequest:
    profile_id: str
    scanner_event_candidate: ScannerEventCandidate
    canonical_match_identity: Mapping[str, Any]
    canonical_competition_scope: str
    canonical_season_scope: str
    requested_capabilities: tuple[str, ...]
    allow_partial: bool = True
    force_refresh: bool = False


@dataclass(frozen=True)
class EnrichmentFact:
    profile_id: str
    capability: str
    fact_name: str
    fact_value_num: float | None
    fact_value_text: str | None
    provider_id: str
    provider_event_id: str | None
    evidence_identity: str
    schema_fingerprint: str
    retrieved_at: str
    confidence: str
    source_consensus: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ActiveEnrichmentResult:
    profile_id: str
    scanner_event_id: str
    canonical_match_identity: Mapping[str, Any]
    status: str
    fetch_decisions: tuple[FetchDecision, ...]
    facts: tuple[EnrichmentFact, ...]
    evidence_refs: tuple[str, ...]
    unavailable_capabilities: tuple[Mapping[str, Any], ...] = field(
        default_factory=tuple
    )
    conflict_diagnostics: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    production_betting_decision: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "scanner_event_id": self.scanner_event_id,
            "canonical_match_identity": dict(self.canonical_match_identity),
            "status": self.status,
            "fetch_decisions": [asdict(d) for d in self.fetch_decisions],
            "facts": [f.to_dict() for f in self.facts],
            "evidence_refs": list(self.evidence_refs),
            "unavailable_capabilities": list(self.unavailable_capabilities),
            "conflict_diagnostics": list(self.conflict_diagnostics),
            "production_betting_decision": self.production_betting_decision,
        }


def _metric_value(raw_value: Any) -> float | None:
    if raw_value in (None, ""):
        return None
    try:
        return float(str(raw_value).replace("%", ""))
    except ValueError:
        return None


def _retrieved_at(payload: Mapping[str, Any], event: Mapping[str, Any]) -> str:
    return str(
        payload.get("retrieved_at")
        or event.get("retrieval_timestamp_utc")
        or datetime.now(UTC).isoformat()
    )


def _provider_event_id(event: Mapping[str, Any]) -> str:
    return str(event.get("provider_event_id") or event.get("id") or "")


def _kickoff_utc(event: Mapping[str, Any]) -> str:
    return str(event.get("event_date_utc") or event.get("date") or "")


def _kickoff_local(event: Mapping[str, Any]) -> str:
    return str(event.get("event_date_local") or event.get("date") or "")


def _normalize_evidence_payload(
    payload: Mapping[str, Any],
    provider_id: str,
    fallback_evidence_identity: str,
) -> dict[str, Any]:
    event = dict(payload.get("event") or {})
    evidence_identity = validate_evidence_identity(
        str(payload.get("evidence_identity") or fallback_evidence_identity)
    )
    return {
        "provider_id": str(payload.get("provider_id") or provider_id),
        "provider_event_id": _provider_event_id(event),
        "evidence_identity": evidence_identity,
        "schema_fingerprint": str(payload.get("schema_fingerprint") or ""),
        "retrieved_at": _retrieved_at(payload, event),
        "event": event,
    }


def _provider_identity_from_evidence(
    request: ActiveEnrichmentRequest,
    payload: Mapping[str, Any],
) -> ProviderEventIdentity:
    event = payload["event"]
    return ProviderEventIdentity(
        profile_id=request.profile_id,
        provider_id=str(payload["provider_id"]),
        provider_event_id=str(payload["provider_event_id"]),
        kickoff_utc=_kickoff_utc(event),
        kickoff_local=_kickoff_local(event),
        home_team_name=str(event.get("home_team_name") or ""),
        home_team_code=str(event.get("home_team_code") or ""),
        away_team_name=str(event.get("away_team_name") or ""),
        away_team_code=str(event.get("away_team_code") or ""),
        canonical_competition_scope=request.canonical_competition_scope,
        canonical_season_scope=request.canonical_season_scope,
        group_label=event.get("group_label"),
        evidence_identity=str(payload["evidence_identity"]),
        status_name=(
            None
            if event.get("status_name") in (None, "")
            else str(event.get("status_name"))
        ),
        status_state=(
            None
            if event.get("status_state") in (None, "")
            else str(event.get("status_state"))
        ),
    )


def _make_fact(
    *,
    request: ActiveEnrichmentRequest,
    capability: str,
    fact_name: str,
    provider_id: str,
    provider_event_id: str,
    evidence_identity: str,
    schema_fingerprint: str,
    retrieved_at: str,
    text: str | None = None,
    num: float | None = None,
) -> EnrichmentFact:
    return EnrichmentFact(
        profile_id=request.profile_id,
        capability=capability,
        fact_name=fact_name,
        fact_value_num=num,
        fact_value_text=text,
        provider_id=provider_id,
        provider_event_id=provider_event_id,
        evidence_identity=evidence_identity,
        schema_fingerprint=schema_fingerprint,
        retrieved_at=retrieved_at,
        confidence="high",
        source_consensus="single_source_verified",
    )


def _extract_current_discovery_facts(
    request: ActiveEnrichmentRequest,
    payload: Mapping[str, Any],
) -> list[EnrichmentFact]:
    event = payload["event"]
    facts: list[EnrichmentFact] = []
    common = {
        "request": request,
        "capability": "current_discovery",
        "provider_id": str(payload["provider_id"]),
        "provider_event_id": str(payload["provider_event_id"]),
        "evidence_identity": str(payload["evidence_identity"]),
        "schema_fingerprint": str(payload["schema_fingerprint"]),
        "retrieved_at": str(payload["retrieved_at"]),
    }

    text_fields = {
        "event_status_state": event.get("status_state"),
        "event_status_name": event.get("status_name"),
        "kickoff_utc": _kickoff_utc(event),
        "kickoff_local": _kickoff_local(event),
        "venue_name": event.get("venue_name"),
        "venue_city": event.get("venue_city"),
    }
    for fact_name, raw_value in text_fields.items():
        if raw_value not in (None, ""):
            facts.append(_make_fact(fact_name=fact_name, text=str(raw_value), **common))

    for index, broadcast_name in enumerate(event.get("broadcasts") or [], start=1):
        facts.append(
            _make_fact(
                fact_name=f"broadcast_name_{index}",
                text=str(broadcast_name),
                **common,
            )
        )

    for fact_name, raw_value in {
        "score_home": event.get("score_home"),
        "score_away": event.get("score_away"),
    }.items():
        numeric_value = _metric_value(raw_value)
        if numeric_value is not None:
            facts.append(_make_fact(fact_name=fact_name, num=numeric_value, **common))

    return facts


def _extract_current_form_facts(
    request: ActiveEnrichmentRequest,
    payload: Mapping[str, Any],
) -> tuple[list[EnrichmentFact], str | None]:
    event = payload["event"]
    facts: list[EnrichmentFact] = []
    common = {
        "request": request,
        "capability": "current_form",
        "provider_id": str(payload["provider_id"]),
        "provider_event_id": str(payload["provider_event_id"]),
        "evidence_identity": str(payload["evidence_identity"]),
        "schema_fingerprint": str(payload["schema_fingerprint"]),
        "retrieved_at": str(payload["retrieved_at"]),
    }

    records = event.get("team_records") or []
    for record in records:
        home_away = str(record.get("home_away") or "").strip().lower()
        prefix = (
            "home" if home_away == "home" else "away" if home_away == "away" else None
        )
        summary = record.get("team_record_summary")
        if prefix and summary not in (None, ""):
            facts.append(
                _make_fact(
                    fact_name=f"{prefix}_team_record_summary",
                    text=str(summary),
                    **common,
                )
            )
        team_form = record.get("team_form")
        if prefix and team_form not in (None, ""):
            facts.append(
                _make_fact(
                    fact_name=f"{prefix}_team_form", text=str(team_form), **common
                )
            )

    if not facts:
        return [], "missing_current_form_data"
    return facts, None


def _extract_detailed_metrics_facts(
    request: ActiveEnrichmentRequest,
    payload: Mapping[str, Any],
) -> tuple[list[EnrichmentFact], str | None]:
    event = payload["event"]
    statistics = event.get("statistics") or []
    facts: list[EnrichmentFact] = []
    common = {
        "request": request,
        "capability": "detailed_metrics",
        "provider_id": str(payload["provider_id"]),
        "provider_event_id": str(payload["provider_event_id"]),
        "evidence_identity": str(payload["evidence_identity"]),
        "schema_fingerprint": str(payload["schema_fingerprint"]),
        "retrieved_at": str(payload["retrieved_at"]),
    }

    for statistic in statistics:
        stat_name = str(statistic.get("name") or "")
        if stat_name not in ALLOWED_DETAILED_METRICS:
            continue
        numeric_value = statistic.get("value")
        if numeric_value is None:
            numeric_value = _metric_value(statistic.get("display_value"))
        numeric_value = _metric_value(numeric_value)
        if numeric_value is None:
            continue
        side = str(statistic.get("home_away") or "").strip().lower()
        prefix = "home" if side == "home" else "away" if side == "away" else "team"
        facts.append(
            _make_fact(fact_name=f"{prefix}_{stat_name}", num=numeric_value, **common)
        )

    if not facts:
        return [], "missing_detailed_metrics_data"
    return facts, None


def _extract_capability_facts(
    request: ActiveEnrichmentRequest,
    capability: str,
    payload: Mapping[str, Any],
) -> tuple[list[EnrichmentFact], str | None]:
    if capability == "current_discovery":
        facts = _extract_current_discovery_facts(request, payload)
        return facts, None if facts else "missing_current_discovery_data"
    if capability == "current_form":
        return _extract_current_form_facts(request, payload)
    if capability == "detailed_metrics":
        return _extract_detailed_metrics_facts(request, payload)
    return [], "unsupported_capability"


class ActiveEnrichmentOrchestrator:
    """Orchestrate completeness checks, provider evidence validation, and fact extraction."""

    def __init__(self, state_store: EnrichmentStateStore) -> None:
        self.state_store = state_store

    def _load_evidence(
        self,
        provider_id: str,
        capability: str,
        evidence_identity: str | None = None,
    ) -> Mapping[str, Any] | None:
        keys = []
        if evidence_identity:
            keys.append(evidence_identity)
        keys.append(f"{provider_id}_{capability}_evidence")
        for key in keys:
            evidence = self.state_store.get_evidence(key)
            if evidence is not None:
                return evidence
        return None

    def enrich_event(self, request: ActiveEnrichmentRequest) -> ActiveEnrichmentResult:
        profile = get_competition_profile(request.profile_id)
        scanner = request.scanner_event_candidate
        fetch_decisions: list[FetchDecision] = []
        unavailable: list[Mapping[str, Any]] = []
        evidence_refs: list[str] = []
        facts_list: list[EnrichmentFact] = []
        conflicts: list[Mapping[str, Any]] = []

        seed = IdentitySeed(
            profile_id=request.profile_id,
            fixture_seed_id=scanner.scanner_event_id,
            canonical_competition_scope=scanner.canonical_competition_scope,
            canonical_season_scope=scanner.canonical_season_scope,
            kickoff_local=scanner.kickoff_local,
            kickoff_utc=scanner.kickoff_utc,
            home_team_name=scanner.home_team_name,
            home_team_code=scanner.home_team_code or "",
            away_team_name=scanner.away_team_name,
            away_team_code=scanner.away_team_code or "",
            group_label=scanner.group_label,
        )

        identity_tolerance = int(
            profile.identity_mapping_policy.get("time_tolerance_seconds", 18000)
        )

        for capability in request.requested_capabilities:
            if capability in profile.blocked_source_policy:
                fetch_decisions.append(
                    FetchDecision(
                        capability=capability,
                        decision="BLOCKED",
                        reason=profile.blocked_source_policy[capability],
                        provider_priority=(),
                        force_refresh=False,
                    )
                )
                unavailable.append(
                    {"capability": capability, "reason": "blocked_by_profile_policy"}
                )
                continue

            priority = profile.source_priority
            if capability == "detailed_metrics":
                priority = ("espn-fifa-worldcup", "soccerdata-espn-worldcup")
            elif capability == "current_form":
                priority = ("espn-fifa-worldcup",)

            requirement = EnrichmentCapabilityRequirement(
                capability=capability,
                required_for_profile=capability
                in profile.canonical_scope.active_capability_targets,
                freshness_ttl_seconds=1800,
                heavy_fetch=capability == "detailed_metrics",
                provider_priority=priority,
            )

            completeness = self.state_store.get_completeness(
                request.profile_id, scanner.scanner_event_id, capability
            )
            decision = make_fetch_decision(
                requirement, completeness, force_refresh=request.force_refresh
            )
            fetch_decisions.append(decision)

            if decision.decision == "SKIP_UNSUPPORTED":
                unavailable.append(
                    {"capability": capability, "reason": "unsupported_by_provider"}
                )
                continue

            if decision.decision == "BLOCKED":
                unavailable.append(
                    {"capability": capability, "reason": decision.reason}
                )
                continue

            provider_candidates = decision.provider_priority
            cached_only = (
                decision.decision == "REUSE_CACHED" and completeness is not None
            )
            if cached_only and completeness is not None:
                provider_candidates = (completeness.provider_id,)

            resolved = False
            capability_reason = "missing_provider_data_or_identity_mismatch"
            for provider_id in provider_candidates:
                evidence_identity = (
                    completeness.evidence_identity
                    if cached_only and completeness
                    else None
                )
                stored_evidence = self._load_evidence(
                    provider_id, capability, evidence_identity=evidence_identity
                )
                if stored_evidence is None:
                    if capability_reason not in {
                        "invalid_evidence_identity",
                        "identity_mismatch",
                    }:
                        capability_reason = (
                            "cached_evidence_missing_or_invalid"
                            if cached_only
                            else "missing_provider_data_or_identity_mismatch"
                        )
                    continue

                fallback_identity = evidence_identity or (
                    f"{provider_id}_{capability}_evidence"
                )
                try:
                    normalized = _normalize_evidence_payload(
                        stored_evidence, provider_id, fallback_identity
                    )
                except ValueError as exc:
                    conflicts.append(
                        {
                            "provider_id": provider_id,
                            "capability": capability,
                            "reason": "invalid_evidence_identity",
                            "details": str(exc),
                        }
                    )
                    capability_reason = "invalid_evidence_identity"
                    continue

                provider_identity = _provider_identity_from_evidence(
                    request, normalized
                )
                match_res = match_identities(
                    seed,
                    [provider_identity],
                    time_tolerance_seconds=identity_tolerance,
                )
                if match_res.identity_status not in {
                    "IDENTITY_CONFIRMED",
                    "IDENTITY_PARTIAL",
                }:
                    conflicts.append(
                        {
                            "provider_id": provider_id,
                            "capability": capability,
                            "reason": "identity_mismatch",
                            "mismatch_details": list(match_res.mismatch_reasons),
                        }
                    )
                    capability_reason = "identity_mismatch"
                    continue

                capability_facts, missing_reason = _extract_capability_facts(
                    request, capability, normalized
                )
                if not capability_facts:
                    capability_reason = missing_reason or capability_reason
                    conflicts.append(
                        {
                            "provider_id": provider_id,
                            "capability": capability,
                            "reason": capability_reason,
                        }
                    )
                    continue

                self.state_store.put_evidence(
                    str(normalized["evidence_identity"]), stored_evidence
                )
                if not cached_only:
                    self.state_store.put_completeness(
                        EnrichmentCompletenessRecord(
                            profile_id=request.profile_id,
                            canonical_entity_id=scanner.scanner_event_id,
                            entity_type="fixture",
                            capability=capability,
                            provider_id=str(normalized["provider_id"]),
                            evidence_identity=str(normalized["evidence_identity"]),
                            schema_fingerprint=str(normalized["schema_fingerprint"]),
                            last_verified_at=datetime.now(UTC).isoformat(),
                            last_enriched_at=str(normalized["retrieved_at"]),
                            completeness_status="COMPLETE_FRESH",
                        )
                    )

                facts_list.extend(capability_facts)
                evidence_refs.append(str(normalized["evidence_identity"]))
                resolved = True
                break

            if not resolved:
                unavailable.append(
                    {"capability": capability, "reason": capability_reason}
                )

        status = "ENRICHED_COMPLETE"
        if not facts_list:
            status = "ENRICH_FAILED_CLOSED"
        elif unavailable:
            status = "ENRICHED_PARTIAL"

        return ActiveEnrichmentResult(
            profile_id=request.profile_id,
            scanner_event_id=scanner.scanner_event_id,
            canonical_match_identity=request.canonical_match_identity,
            status=status,
            fetch_decisions=tuple(fetch_decisions),
            facts=tuple(facts_list),
            evidence_refs=tuple(evidence_refs),
            unavailable_capabilities=tuple(unavailable),
            conflict_diagnostics=tuple(conflicts),
            production_betting_decision=False,
        )
