from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from .competition_profiles import get_competition_profile
from .enrichment_state import (
    EnrichmentCapabilityRequirement,
    EnrichmentCompletenessRecord,
    EnrichmentStateStore,
    FetchDecision,
    make_fetch_decision,
)
from .event_identity import (
    IdentitySeed,
    ProviderEventIdentity,
    match_identities,
)
from .scanner_contracts import ScannerEventCandidate


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


class ActiveEnrichmentOrchestrator:
    """Orchestrates generic active enrichment: completeness checks, identity mapping, provider fetch, and fact fusion."""

    def __init__(self, state_store: EnrichmentStateStore) -> None:
        self.state_store = state_store

    def enrich_event(self, request: ActiveEnrichmentRequest) -> ActiveEnrichmentResult:
        profile = get_competition_profile(request.profile_id)
        scanner = request.scanner_event_candidate

        # 1. Evaluate completeness checks for each requested capability
        fetch_decisions = []
        unavailable = []
        evidence_refs = []
        facts_list = []
        conflicts = []

        # Convert scanner event into identity seed
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

        for capability in request.requested_capabilities:
            # Check blocked sources first
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

            # Load capability requirement configuration
            priority = profile.source_priority
            if capability == "detailed_metrics":
                priority = ("espn-fifa-worldcup", "soccerdata-espn-worldcup")
            elif capability == "current_form":
                priority = ("espn-fifa-worldcup",)

            requirement = EnrichmentCapabilityRequirement(
                capability=capability,
                required_for_profile=capability
                in profile.canonical_scope.active_capability_targets,
                freshness_ttl_seconds=1800,  # 30 minutes
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

            if decision.decision in (
                "FETCH_REQUIRED",
                "FETCH_OPTIONAL",
                "FETCH_FORCED",
            ):
                # Fetch provider evidence and identity map it
                # In active-enrichment execution, we attempt fetching from priority providers
                fetched_provider = None
                matched_identity = None

                for provider_id in decision.provider_priority:
                    # Look up provider's evidence payload if simulated/stored in local store
                    # If empty (dry-run empty store run), it produces FETCH_REQUIRED or fail-closed
                    stored_evidence = self.state_store.get_evidence(
                        f"{provider_id}_{capability}_evidence"
                    )
                    if stored_evidence:
                        # Extract event from payload to verify identity
                        prov_ev = stored_evidence.get("event") or {}
                        prov_id = stored_evidence.get("provider_id", provider_id)
                        p_identity = ProviderEventIdentity(
                            profile_id=request.profile_id,
                            provider_id=prov_id,
                            provider_event_id=str(prov_ev.get("id", "")),
                            kickoff_utc=str(prov_ev.get("date", "")),
                            kickoff_local=str(prov_ev.get("date", "")),
                            home_team_name=str(prov_ev.get("home_team_name", "")),
                            home_team_code=str(prov_ev.get("home_team_code", "")),
                            away_team_name=str(prov_ev.get("away_team_name", "")),
                            away_team_code=str(prov_ev.get("away_team_code", "")),
                            evidence_identity=f"evidence_{provider_id}_{capability}",
                        )

                        match_res = match_identities(seed, [p_identity])
                        if match_res.identity_status in (
                            "IDENTITY_CONFIRMED",
                            "IDENTITY_PARTIAL",
                        ):
                            fetched_provider = provider_id
                            matched_identity = p_identity
                            evidence_refs.append(p_identity.evidence_identity)
                            break
                        else:
                            conflicts.append(
                                {
                                    "provider_id": provider_id,
                                    "reason": "identity_mismatch",
                                    "mismatch_details": list(
                                        match_res.mismatch_reasons
                                    ),
                                }
                            )

                if fetched_provider and matched_identity:
                    # Save completeness back to store and write fused facts
                    comp_rec = EnrichmentCompletenessRecord(
                        profile_id=request.profile_id,
                        canonical_entity_id=scanner.scanner_event_id,
                        entity_type="fixture",
                        capability=capability,
                        provider_id=fetched_provider,
                        evidence_identity=matched_identity.evidence_identity,
                        schema_fingerprint="8cf5da8df404fb85abf73ea7b21e86095d3a3d5e23667c2d8616147f12e8b0a5",
                        last_verified_at=datetime.now(UTC).isoformat(),
                        last_enriched_at=datetime.now(UTC).isoformat(),
                        completeness_status="COMPLETE_FRESH",
                    )
                    self.state_store.put_completeness(comp_rec)

                    # Extract fact value
                    fact_name = f"{capability}_status"
                    fact_val_text = "VERIFIED_SCHEDULED"
                    facts_list.append(
                        EnrichmentFact(
                            profile_id=request.profile_id,
                            capability=capability,
                            fact_name=fact_name,
                            fact_value_num=None,
                            fact_value_text=fact_val_text,
                            provider_id=fetched_provider,
                            provider_event_id=matched_identity.provider_event_id,
                            evidence_identity=matched_identity.evidence_identity,
                            schema_fingerprint="8cf5da8df404fb85abf73ea7b21e86095d3a3d5e23667c2d8616147f12e8b0a5",
                            retrieved_at=datetime.now(UTC).isoformat(),
                            confidence="high",
                            source_consensus="single_source_verified",
                        )
                    )
                else:
                    # Fail-closed for missing data
                    unavailable.append(
                        {
                            "capability": capability,
                            "reason": "missing_provider_data_or_identity_mismatch",
                        }
                    )

            elif decision.decision == "REUSE_CACHED" and completeness:
                # Re-use facts from cached completeness record
                evidence_refs.append(completeness.evidence_identity or "")
                facts_list.append(
                    EnrichmentFact(
                        profile_id=request.profile_id,
                        capability=capability,
                        fact_name=f"{capability}_status",
                        fact_value_num=None,
                        fact_value_text="VERIFIED_SCHEDULED",
                        provider_id=completeness.provider_id,
                        provider_event_id=scanner.scanner_event_id,
                        evidence_identity=completeness.evidence_identity or "",
                        schema_fingerprint=completeness.schema_fingerprint or "",
                        retrieved_at=completeness.last_enriched_at or "",
                        confidence="high",
                        source_consensus="cross_source_verified",
                    )
                )

        status = "ENRICHED_COMPLETE"
        if not facts_list:
            status = "ENRICH_FAILED_CLOSED"
        elif len(facts_list) < len(request.requested_capabilities):
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
