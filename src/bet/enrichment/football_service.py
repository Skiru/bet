import json
import hashlib
import yaml
from dataclasses import dataclass
from datetime import datetime, timezone, UTC
from typing import Any, Protocol, get_type_hints, get_origin, get_args, Union
from enum import StrEnum
from pathlib import Path
import sqlite3

from bet.db.repositories import FixtureRepo, TeamRepo, FixtureCapabilityRepo, FootballSnapshotReader
from bet.db.observation_models import create_observation, create_projection
from bet.enrichment.football_snapshot import (
    FootballEnrichmentSnapshot,
    to_dict,
    from_dict,
    canonical_hash,
    canonical_json_bytes,
    parse_datetime,
)
from bet.enrichment.models import (
    NormalizedParticipant,
    NormalizedTeamMatch,
    NormalizedMetricSet,
    NormalizedStandingTable,
    NormalizedStandingRow,
)
from bet.integration.source_result import SourceOperationResult, SourceResultStatus
from bet.integration.evidence import namespaced_source_refs, write_source_operation_bundle
from bet.api_clients.espn import ESPNClient
from bet.api_clients.api_football import APIFootballClient
from bet.api_clients.rate_limiter import RateLimiter


# ---------------------------------------------------------------------------
# Provider States and Registry
# ---------------------------------------------------------------------------

class ProviderState(StrEnum):
    CANDIDATE = "CANDIDATE"
    QUALIFIED_SHADOW = "QUALIFIED_SHADOW"
    PRODUCTION_ALLOWED = "PRODUCTION_ALLOWED"
    CREDENTIAL_UNAVAILABLE = "CREDENTIAL_UNAVAILABLE"
    GOVERNANCE_BLOCKED = "GOVERNANCE_BLOCKED"
    REJECTED = "REJECTED"


PROVIDER_REGISTRY = {
    "espn": ProviderState.QUALIFIED_SHADOW,
    "api-football": ProviderState.CANDIDATE,
    "football-data": ProviderState.CANDIDATE,
    "sportdb": ProviderState.CANDIDATE,
    "highlightly": ProviderState.CANDIDATE,
    "understat": ProviderState.CANDIDATE,
    "thesportsdb": ProviderState.CANDIDATE,
}


# ---------------------------------------------------------------------------
# Configuration Loader and Validator
# ---------------------------------------------------------------------------

def parse_enrichment_mode() -> str:
    import os
    raw_mode = os.environ.get("FOOTBALL_ENRICHMENT_MODE", "off")
    mode = raw_mode.strip().lower()
    if mode not in ("off", "shadow", "canary", "on"):
        raise ValueError(f"Invalid FOOTBALL_ENRICHMENT_MODE: '{raw_mode}'")
    if mode in ("canary", "on"):
        raise PermissionError(f"FOOTBALL_ENRICHMENT_MODE '{mode}' is explicitly unauthorized in this phase")
    return mode


def load_and_validate_config(config_dir: Path | str = "config") -> dict[str, Any]:
    config_dir = Path(config_dir)
    
    # Load capabilities
    with open(config_dir / "football_capabilities.yaml", "r") as f:
        caps_data = yaml.safe_load(f) or {}
    capabilities = caps_data.get("capabilities", {})
    
    # Load freshness
    with open(config_dir / "football_freshness.yaml", "r") as f:
        fresh_data = yaml.safe_load(f) or {}
    freshness = fresh_data.get("freshness", {})
    
    # Load routing
    with open(config_dir / "football_routing.yaml", "r") as f:
        routing_data = yaml.safe_load(f) or {}
    routing = routing_data.get("routing", {})
    
    # Load metrics
    with open(config_dir / "football_metrics.yaml", "r") as f:
        metrics_data = yaml.safe_load(f) or {}
    metrics = metrics_data.get("metrics", {})
    
    # Validation rules:
    # 1. Reject unknown capability names in routing
    # 2. Validate freshness values (must be positive integers)
    for k, v in freshness.items():
        if not isinstance(v, int) or v <= 0:
            raise ValueError(f"Invalid freshness value for {k}: {v}")
            
    # 3. Validate routing
    for route_name, route_info in routing.items():
        precedence = route_info.get("precedence", [])
        # Check for duplicate routes/providers in precedence
        if len(precedence) != len(set(precedence)):
            raise ValueError(f"Duplicate providers in route {route_name}: {precedence}")
            
        for provider in precedence:
            # Check provider present in registry
            if provider not in PROVIDER_REGISTRY:
                raise ValueError(f"Provider {provider} in route {route_name} is not present in the registry")
            # Check routing to a governance-blocked provider
            if PROVIDER_REGISTRY[provider] == ProviderState.GOVERNANCE_BLOCKED:
                raise ValueError(f"Provider {provider} in route {route_name} is governance-blocked")
                
    # Compute policy_config_hash from canonicalized contents of the configuration actually used for the run
    canonical_config = {
        "capabilities": capabilities,
        "freshness": freshness,
        "routing": routing,
        "metrics": metrics,
    }
    config_json = json.dumps(canonical_config, sort_keys=True, separators=(",", ":"))
    policy_config_hash = hashlib.sha256(config_json.encode("utf-8")).hexdigest()
    
    return {
        "capabilities": capabilities,
        "freshness": freshness,
        "routing": routing,
        "metrics": metrics,
        "policy_config_hash": policy_config_hash,
    }


# ---------------------------------------------------------------------------
# Football Capability-Adapter Protocol and Implementations
# ---------------------------------------------------------------------------

class FootballCapabilityAdapter(Protocol):
    @property
    def provider(self) -> str:
        ...

    def fetch_capability(
        self,
        capability: str,
        canonical_fixture_id: int,
        analysis_cutoff_at: datetime,
        **kwargs
    ) -> SourceOperationResult[Any]:
        ...


class ESPNFootballAdapter:
    def __init__(self, client: ESPNClient):
        self.client = client
        self.provider_name = "espn"

    @property
    def provider(self) -> str:
        return self.provider_name

    def fetch_capability(
        self,
        capability: str,
        canonical_fixture_id: int,
        analysis_cutoff_at: datetime,
        **kwargs
    ) -> SourceOperationResult[Any]:
        if capability == "current_recent_form":
            team_id = kwargs.get("team_id")
            native_team_id = kwargs.get("native_team_id")
            target_event_id = kwargs.get("native_fixture_id")
            
            if not native_team_id:
                return SourceOperationResult(SourceResultStatus.NOT_FOUND, error_code="native_team_id_missing")
                
            last_fixtures_res = self.client.get_team_last_fixtures_result(
                native_team_id,
                last_n=5,
                analysis_cutoff_at=analysis_cutoff_at.isoformat(),
                exclude_event_ids={target_event_id} if target_event_id else None
            )
            
            if last_fixtures_res.status is not SourceResultStatus.SUCCESS:
                return SourceOperationResult(
                    status=last_fixtures_res.status,
                    http_status=last_fixtures_res.http_status,
                    error_code=last_fixtures_res.error_code,
                    evidence_refs=last_fixtures_res.evidence_refs,
                )
                
            last_fixtures = last_fixtures_res.value or []
            if not last_fixtures:
                return SourceOperationResult(
                    status=SourceResultStatus.VALID_EMPTY,
                    value=[],
                    evidence_refs=last_fixtures_res.evidence_refs,
                )
                
            matches = []
            evidence_refs = list(last_fixtures_res.evidence_refs)
            
            for fix_data in last_fixtures:
                fix_id = str(fix_data.get("id", ""))
                if not fix_id:
                    continue
                    
                stats_res = self.client.get_fixture_stats_result(fix_id)
                evidence_refs.extend(stats_res.evidence_refs)
                
                if stats_res.status is not SourceResultStatus.SUCCESS or not stats_res.value:
                    continue
                    
                for ms in stats_res.value:
                    home_id = getattr(ms, "home_participant_id", "")
                    away_id = getattr(ms, "away_participant_id", "")
                    
                    if str(native_team_id) not in (str(home_id), str(away_id)):
                        continue
                        
                    is_home = str(native_team_id) == str(home_id)
                    opp_id = away_id if is_home else home_id
                    goals_val = ms.stats.get("goals", {}).get("home" if is_home else "away", 0)
                    
                    match_dto = NormalizedTeamMatch(
                        canonical_fixture_id=None,
                        native_fixture_id=fix_id,
                        provider="espn",
                        source_timestamp=analysis_cutoff_at,
                        team_canonical_id=team_id,
                        team_native_id=str(native_team_id),
                        opponent_canonical_id=None,
                        opponent_native_id=str(opp_id),
                        kickoff_at=parse_datetime(fix_data.get("date")),
                        metrics=NormalizedMetricSet(
                            provider="espn",
                            source_timestamp=analysis_cutoff_at,
                            values={"goals": goals_val}
                        )
                    )
                    matches.append(match_dto)
                    
            if not evidence_refs:
                return SourceOperationResult(SourceResultStatus.EVIDENCE_ERROR, error_code="no_evidence_refs")
                
            source_refs = namespaced_source_refs("espn-football", [target_event_id] if target_event_id else [])
            bundle_id, _ = write_source_operation_bundle(
                registered_source_key="espn-football",
                operation_name="current_recent_form",
                request_identity=f"GET /teams/{native_team_id}/schedule",
                parser_version="espn-v1",
                source_event_refs=source_refs,
                evidence_refs=evidence_refs,
            )
            
            return SourceOperationResult(
                status=SourceResultStatus.SUCCESS,
                value=matches,
                provider="espn",
                operation="current_recent_form",
                request_identity=f"GET /teams/{native_team_id}/schedule",
                evidence_refs=tuple(evidence_refs),
                bundle_id=bundle_id,
                retrieved_at=datetime.now(timezone.utc),
            )

        elif capability == "h2h_head_to_head":
            team1_id = kwargs.get("team1_id")
            team2_id = kwargs.get("team2_id")
            native_team1_id = kwargs.get("native_team1_id")
            native_team2_id = kwargs.get("native_team2_id")
            target_event_id = kwargs.get("native_fixture_id")
            
            if not native_team1_id or not native_team2_id:
                return SourceOperationResult(SourceResultStatus.NOT_FOUND, error_code="native_team_ids_missing")
                
            h2h_res = self.client.get_h2h_result(
                native_team1_id,
                native_team2_id,
                analysis_cutoff_at=analysis_cutoff_at.isoformat(),
                exclude_event_ids={target_event_id} if target_event_id else None,
                last_n=5
            )
            
            if h2h_res.status is not SourceResultStatus.SUCCESS:
                return SourceOperationResult(
                    status=h2h_res.status,
                    http_status=h2h_res.http_status,
                    error_code=h2h_res.error_code,
                    evidence_refs=h2h_res.evidence_refs,
                )
                
            meetings = h2h_res.value or []
            if not meetings:
                return SourceOperationResult(
                    status=SourceResultStatus.VALID_EMPTY,
                    value=[],
                    evidence_refs=h2h_res.evidence_refs,
                )
                
            matches = []
            evidence_refs = list(h2h_res.evidence_refs)
            
            for meeting in meetings:
                fix_id = meeting.get("event_id")
                home_id = meeting.get("home_participant_id")
                away_id = meeting.get("away_participant_id")
                score = meeting.get("score", "")
                
                home_goals = 0
                away_goals = 0
                if "-" in score:
                    try:
                        home_goals, away_goals = map(int, score.split("-"))
                    except ValueError:
                        pass
                        
                match_dto = NormalizedTeamMatch(
                    canonical_fixture_id=None,
                    native_fixture_id=fix_id,
                    provider="espn",
                    source_timestamp=analysis_cutoff_at,
                    team_canonical_id=team1_id if str(home_id) == str(native_team1_id) else team2_id,
                    team_native_id=str(home_id),
                    opponent_canonical_id=team2_id if str(home_id) == str(native_team1_id) else team1_id,
                    opponent_native_id=str(away_id),
                    kickoff_at=parse_datetime(meeting.get("date")),
                    metrics=NormalizedMetricSet(
                        provider="espn",
                        source_timestamp=analysis_cutoff_at,
                        values={"goals": home_goals if str(home_id) == str(native_team1_id) else away_goals}
                    )
                )
                matches.append(match_dto)
                
            if not evidence_refs:
                return SourceOperationResult(SourceResultStatus.EVIDENCE_ERROR, error_code="no_evidence_refs")
                
            source_refs = namespaced_source_refs("espn-football", [target_event_id] if target_event_id else [])
            bundle_id, _ = write_source_operation_bundle(
                registered_source_key="espn-football",
                operation_name="h2h_head_to_head",
                request_identity=f"GET /teams/{native_team1_id}/schedule",
                parser_version="espn-v1",
                source_event_refs=source_refs,
                evidence_refs=evidence_refs,
            )
            
            return SourceOperationResult(
                status=SourceResultStatus.SUCCESS,
                value=matches,
                provider="espn",
                operation="h2h_head_to_head",
                request_identity=f"GET /teams/{native_team1_id}/schedule",
                evidence_refs=tuple(evidence_refs),
                bundle_id=bundle_id,
                retrieved_at=datetime.now(timezone.utc),
            )

        elif capability == "standings_competition_context":
            competition_id = kwargs.get("competition_id")
            native_competition_id = kwargs.get("native_competition_id")
            
            standings_res = self.client.get_standings_result()
            
            if standings_res.status is not SourceResultStatus.SUCCESS:
                return SourceOperationResult(
                    status=standings_res.status,
                    http_status=standings_res.http_status,
                    error_code=standings_res.error_code,
                    evidence_refs=standings_res.evidence_refs,
                )
                
            raw_rows = standings_res.value or []
            if not raw_rows:
                return SourceOperationResult(
                    status=SourceResultStatus.VALID_EMPTY,
                    value=None,
                    evidence_refs=standings_res.evidence_refs,
                )
                
            rows = []
            for r in raw_rows:
                row_dto = NormalizedStandingRow(
                    team_canonical_id=None,
                    team_native_id=str(r.get("team_id")),
                    rank=int(r.get("rank") or 0),
                    points=int(r.get("points") or 0),
                    played=int(r.get("played") or 0),
                    wins=int(r.get("wins") or 0),
                    draws=int(r.get("draws") or 0),
                    losses=int(r.get("losses") or 0),
                    goals_for=int(r.get("goals_for") or 0),
                    goals_against=int(r.get("goals_against") or 0),
                    goal_diff=int(r.get("goal_diff") or 0),
                    form=str(r.get("form") or "")
                )
                rows.append(row_dto)
                
            table_dto = NormalizedStandingTable(
                competition_canonical_id=competition_id,
                competition_native_id=str(native_competition_id),
                provider="espn",
                source_timestamp=analysis_cutoff_at,
                rows=tuple(rows)
            )
            
            if not standings_res.evidence_refs:
                return SourceOperationResult(SourceResultStatus.EVIDENCE_ERROR, error_code="no_evidence_refs")
                
            bundle_id, _ = write_source_operation_bundle(
                registered_source_key="espn-football",
                operation_name="standings_competition_context",
                request_identity="GET /standings",
                parser_version="espn-v1",
                source_event_refs=[],
                evidence_refs=list(standings_res.evidence_refs),
            )
            
            return SourceOperationResult(
                status=SourceResultStatus.SUCCESS,
                value=table_dto,
                provider="espn",
                operation="standings_competition_context",
                request_identity="GET /standings",
                evidence_refs=standings_res.evidence_refs,
                bundle_id=bundle_id,
                retrieved_at=datetime.now(timezone.utc),
            )

        elif capability == "fixture_team_statistics":
            native_fixture_id = kwargs.get("native_fixture_id")
            
            if not native_fixture_id:
                return SourceOperationResult(SourceResultStatus.NOT_FOUND, error_code="native_fixture_id_missing")
                
            stats_res = self.client.get_fixture_stats_result(native_fixture_id)
            
            if stats_res.status is not SourceResultStatus.SUCCESS:
                return SourceOperationResult(
                    status=stats_res.status,
                    http_status=stats_res.http_status,
                    error_code=stats_res.error_code,
                    evidence_refs=stats_res.evidence_refs,
                )
                
            raw_stats = stats_res.value or []
            if not raw_stats:
                return SourceOperationResult(
                    status=SourceResultStatus.VALID_EMPTY,
                    value=None,
                    evidence_refs=stats_res.evidence_refs,
                )
                
            ms = raw_stats[0]
            metric_set = NormalizedMetricSet(
                provider="espn",
                source_timestamp=analysis_cutoff_at,
                values=ms.stats
            )
            
            if not stats_res.evidence_refs:
                return SourceOperationResult(SourceResultStatus.EVIDENCE_ERROR, error_code="no_evidence_refs")
                
            bundle_id, _ = write_source_operation_bundle(
                registered_source_key="espn-football",
                operation_name="fixture_team_statistics",
                request_identity=f"GET /summary?event={native_fixture_id}",
                parser_version="espn-v1",
                source_event_refs=namespaced_source_refs("espn-football", [native_fixture_id]),
                evidence_refs=list(stats_res.evidence_refs),
            )
            
            return SourceOperationResult(
                status=SourceResultStatus.SUCCESS,
                value=metric_set,
                provider="espn",
                operation="fixture_team_statistics",
                request_identity=f"GET /summary?event={native_fixture_id}",
                evidence_refs=stats_res.evidence_refs,
                bundle_id=bundle_id,
                retrieved_at=datetime.now(timezone.utc),
            )

        return SourceOperationResult(
            status=SourceResultStatus.NOT_SUPPORTED,
            error_code="capability_not_supported",
        )


class APIFootballCandidateAdapter:
    def __init__(self, client: APIFootballClient):
        self.client = client
        self.provider_name = "api-football"

    @property
    def provider(self) -> str:
        return self.provider_name

    def fetch_capability(
        self,
        capability: str,
        canonical_fixture_id: int,
        analysis_cutoff_at: datetime,
        **kwargs
    ) -> SourceOperationResult[Any]:
        native_fixture_id = kwargs.get("native_fixture_id")
        if capability == "fixture_team_statistics":
            if not native_fixture_id:
                return SourceOperationResult(SourceResultStatus.NOT_FOUND, error_code="native_fixture_id_missing")
            res = self.client.get_fixture_stats_result(native_fixture_id)
            return res
        return SourceOperationResult(SourceResultStatus.NOT_SUPPORTED, error_code="capability_not_supported")


class FootballAdapterRegistry:
    def __init__(self):
        self._adapters = {}

    def register(self, provider: str, adapter: FootballCapabilityAdapter) -> None:
        self._adapters[provider] = adapter

    def get(self, provider: str) -> FootballCapabilityAdapter | None:
        return self._adapters.get(provider)


# ---------------------------------------------------------------------------
# Executable Candidate Registry and Probe Runner
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CandidateRecord:
    provider_key: str
    implementation_state: str
    credential_requirement: bool
    governance_state: str
    provenance_family: str
    supported_capabilities: tuple[str, ...]
    replay_availability: bool
    live_probe_eligibility: bool
    reason_when_blocked: str = ""


CANDIDATE_REGISTRY: dict[str, CandidateRecord] = {
    "espn": CandidateRecord(
        provider_key="espn",
        implementation_state="PRODUCTION_READY",
        credential_requirement=False,
        governance_state="QUALIFIED_SHADOW",
        provenance_family="espn-football",
        supported_capabilities=("current_recent_form", "h2h_head_to_head", "standings_competition_context", "fixture_team_statistics"),
        replay_availability=True,
        live_probe_eligibility=True,
    ),
    "api-football": CandidateRecord(
        provider_key="api-football",
        implementation_state="LIVE_PARTIAL",
        credential_requirement=True,
        governance_state="CANDIDATE",
        provenance_family="api-football",
        supported_capabilities=("current_recent_form", "h2h_head_to_head", "standings_competition_context", "fixture_team_statistics"),
        replay_availability=True,
        live_probe_eligibility=True,
    ),
    "football-data": CandidateRecord(
        provider_key="football-data",
        implementation_state="IMPLEMENTED_UNVERIFIED",
        credential_requirement=True,
        governance_state="CANDIDATE",
        provenance_family="football-data-org",
        supported_capabilities=("current_recent_form", "h2h_head_to_head", "standings_competition_context"),
        replay_availability=False,
        live_probe_eligibility=False,
        reason_when_blocked="unverified_implementation",
    ),
    "thesportsdb": CandidateRecord(
        provider_key="thesportsdb",
        implementation_state="IMPLEMENTED_UNVERIFIED",
        credential_requirement=True,
        governance_state="CANDIDATE",
        provenance_family="thesportsdb",
        supported_capabilities=("current_recent_form", "h2h_head_to_head"),
        replay_availability=False,
        live_probe_eligibility=False,
        reason_when_blocked="unverified_implementation",
    ),
    "sportdb": CandidateRecord(
        provider_key="sportdb",
        implementation_state="NOT_IMPLEMENTED",
        credential_requirement=False,
        governance_state="REJECTED",
        provenance_family="sportdb",
        supported_capabilities=(),
        replay_availability=False,
        live_probe_eligibility=False,
        reason_when_blocked="no_implementation",
    ),
    "highlightly": CandidateRecord(
        provider_key="highlightly",
        implementation_state="NOT_IMPLEMENTED",
        credential_requirement=True,
        governance_state="REJECTED",
        provenance_family="highlightly",
        supported_capabilities=(),
        replay_availability=False,
        live_probe_eligibility=False,
        reason_when_blocked="no_implementation",
    ),
    "understat": CandidateRecord(
        provider_key="understat",
        implementation_state="IMPLEMENTED_UNVERIFIED",
        credential_requirement=False,
        governance_state="CANDIDATE",
        provenance_family="understat",
        supported_capabilities=("advanced_xg",),
        replay_availability=False,
        live_probe_eligibility=False,
        reason_when_blocked="narrow_scope",
    ),
}


class ProbeRunner:
    def __init__(
        self,
        allow_live: bool = False,
        provider_budgets: dict[str, int] | None = None,
        global_budget: int = 10,
    ):
        self.allow_live = allow_live
        self.provider_budgets = provider_budgets or {"espn": 5, "api-football": 5}
        self.global_budget = global_budget
        self.call_ledger: list[dict[str, Any]] = []

    def run_probe(
        self,
        provider: str,
        operation: str,
        **kwargs
    ) -> SourceOperationResult[Any]:
        if provider not in CANDIDATE_REGISTRY:
            raise ValueError(f"Provider {provider} not found in candidate registry")
            
        record = CANDIDATE_REGISTRY[provider]
        
        if not record.live_probe_eligibility and not self.allow_live:
            return SourceOperationResult(
                status=SourceResultStatus.BLOCKED,
                error_code="probe_blocked",
                parser_diagnostics={"reason": record.reason_when_blocked or "not_eligible"}
            )
            
        provider_calls = len([c for c in self.call_ledger if c["provider"] == provider])
        if provider_calls >= self.provider_budgets.get(provider, 0):
            return SourceOperationResult(SourceResultStatus.RATE_LIMITED, error_code="provider_budget_exceeded")
            
        if len(self.call_ledger) >= self.global_budget:
            return SourceOperationResult(SourceResultStatus.RATE_LIMITED, error_code="global_budget_exceeded")
            
        if not self.allow_live:
            self.call_ledger.append({
                "provider": provider,
                "operation": operation,
                "mode": "offline",
                "timestamp": datetime.now(UTC).isoformat(),
            })
            return SourceOperationResult(
                status=SourceResultStatus.SUCCESS,
                value={"probe": "offline_success"},
                provider=provider,
                operation=operation,
                retrieved_at=datetime.now(UTC),
            )
            
        raise PermissionError("External network calls are blocked by default. Live mode is unused in this session.")


# ---------------------------------------------------------------------------
# Football Enrichment Service
# ---------------------------------------------------------------------------

class FootballEnrichmentService:
    def __init__(self, adapter_registry: FootballAdapterRegistry | None = None):
        self.adapter_registry = adapter_registry or FootballAdapterRegistry()

    def enrich_fixture(
        self,
        canonical_fixture_id: int,
        analysis_cutoff_at: datetime,
        *,
        force_refresh: bool = False,
    ) -> FootballEnrichmentSnapshot:
        """Enrich a football fixture and publish an atomic immutable snapshot."""
        from bet.db.connection import get_db
        
        # Validate mode
        try:
            mode = parse_enrichment_mode()
        except Exception as e:
            raise RuntimeError(f"Configuration error: {e}") from e

        if analysis_cutoff_at.tzinfo is None:
            analysis_cutoff_at = analysis_cutoff_at.replace(tzinfo=UTC)
        else:
            analysis_cutoff_at = analysis_cutoff_at.astimezone(UTC)

        # Load and validate config
        config = load_and_validate_config()
        policy_config_hash = config["policy_config_hash"]

        # Compute run identity
        base_identity = hashlib.sha256(
            f"football|{canonical_fixture_id}|{analysis_cutoff_at.isoformat()}|{policy_config_hash}".encode()
        ).hexdigest()
        
        if force_refresh:
            run_identity = f"{base_identity}_ref_{int(datetime.now(UTC).timestamp())}"
        else:
            run_identity = base_identity

        # Idempotency check
        if not force_refresh:
            with get_db() as conn:
                existing_run = conn.execute(
                    "SELECT id FROM sports_enrichment_run WHERE run_identity = ? AND status = 'COMPLETE'",
                    (run_identity,)
                ).fetchone()
                if existing_run:
                    reader = FootballSnapshotReader(conn)
                    snap = reader.get_snapshot(canonical_fixture_id)
                    if snap:
                        return snap

        with get_db() as conn:
            fixture_repo = FixtureRepo(conn)
            team_repo = TeamRepo(conn)
            cap_repo = FixtureCapabilityRepo(conn)

            # 1. Resolve fixture and teams
            fixture = fixture_repo.get_by_id(canonical_fixture_id)
            if not fixture:
                raise ValueError(f"Fixture {canonical_fixture_id} not found")

            home_team = team_repo.get_by_id(fixture.home_team_id)
            away_team = team_repo.get_by_id(fixture.away_team_id)
            if not home_team or not away_team:
                raise ValueError(f"Teams for fixture {canonical_fixture_id} not found")

            # Start transaction savepoint
            conn.execute("SAVEPOINT enrich_fixture")
            try:
                # 2. Start enrichment run
                now_str = datetime.now(UTC).isoformat()
                conn.execute(
                    """INSERT OR IGNORE INTO sports_enrichment_run
                       (run_identity, sport, canonical_event_id, analysis_cutoff_at, status, started_at, policy_config_hash, requested_capabilities)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        run_identity,
                        "football",
                        canonical_fixture_id,
                        analysis_cutoff_at.isoformat(),
                        "RUNNING",
                        now_str,
                        policy_config_hash,
                        "recent_form,h2h,standings,stats",
                    ),
                )
                run_row = conn.execute(
                    "SELECT id FROM sports_enrichment_run WHERE run_identity = ?", (run_identity,)
                ).fetchone()
                run_id = run_row[0] if run_row else 1

                # 3. Fetch native IDs from fixture_sources
                espn_fixture_row = conn.execute(
                    "SELECT external_id FROM fixture_sources WHERE fixture_id = ? AND source = 'espn-football'",
                    (canonical_fixture_id,)
                ).fetchone()
                native_fixture_id = espn_fixture_row["external_id"] if espn_fixture_row else ""

                espn_home_row = conn.execute(
                    "SELECT provider_entity_id FROM source_entity_reference WHERE canonical_entity_id = (SELECT id FROM sports_entity WHERE domain_entity_id = ? AND domain_table = 'teams') AND provider = 'espn-football'",
                    (fixture.home_team_id,)
                ).fetchone()
                native_home_id = espn_home_row["provider_entity_id"] if espn_home_row else ""

                espn_away_row = conn.execute(
                    "SELECT provider_entity_id FROM source_entity_reference WHERE canonical_entity_id = (SELECT id FROM sports_entity WHERE domain_entity_id = ? AND domain_table = 'teams') AND provider = 'espn-football'",
                    (fixture.away_team_id,)
                ).fetchone()
                native_away_id = espn_away_row["provider_entity_id"] if espn_away_row else ""

                # 4. Execute capabilities
                capabilities = ["current_recent_form", "h2h_head_to_head", "standings_competition_context", "fixture_team_statistics"]
                selected_obs_ids = []
                
                home_form_matches = []
                away_form_matches = []
                h2h_matches = []
                standings_table = None

                for cap in capabilities:
                    # Determine provider from routing
                    route_name = "current_form" if "form" in cap else ("historical_form_h2h" if "h2h" in cap else ("standings" if "standings" in cap else "detailed_metrics"))
                    precedence = config["routing"].get(route_name, {}).get("precedence", [])
                    
                    selected_provider = None
                    selected_result = None
                    
                    for provider in precedence:
                        # Check if provider is allowed
                        state = PROVIDER_REGISTRY.get(provider)
                        if state not in (ProviderState.PRODUCTION_ALLOWED, ProviderState.QUALIFIED_SHADOW):
                            continue
                            
                        adapter = self.adapter_registry.get(provider)
                        if not adapter:
                            continue
                            
                        # Call adapter
                        kwargs = {
                            "team_id": fixture.home_team_id,
                            "native_team_id": native_home_id,
                            "native_fixture_id": native_fixture_id,
                            "team1_id": fixture.home_team_id,
                            "team2_id": fixture.away_team_id,
                            "native_team1_id": native_home_id,
                            "native_team2_id": native_away_id,
                            "competition_id": fixture.competition_id,
                            "native_competition_id": "eng.1",
                        }
                        
                        # Record attempt start
                        attempt_identity = f"{run_id}|{provider}|{cap}|{now_str}"
                        conn.execute(
                            """INSERT INTO source_operation_attempt
                               (attempt_identity, run_id, provider, operation, request_identity, status, started_at)
                               VALUES (?, ?, ?, ?, ?, ?, ?)""",
                            (attempt_identity, run_id, provider, cap, f"GET /{provider}/{cap}", "IN_FLIGHT", now_str)
                        )
                        attempt_row = conn.execute(
                            "SELECT id FROM source_operation_attempt WHERE attempt_identity = ?", (attempt_identity,)
                        ).fetchone()
                        attempt_id = attempt_row[0] if attempt_row else 1
                        
                        res = adapter.fetch_capability(cap, canonical_fixture_id, analysis_cutoff_at, **kwargs)
                        
                        # Check evidence requirement
                        if res.status == SourceResultStatus.SUCCESS and not res.bundle_id:
                            res = SourceOperationResult(
                                status=SourceResultStatus.EVIDENCE_ERROR,
                                error_code="missing_required_evidence",
                                evidence_refs=res.evidence_refs,
                            )
                            
                        # Record attempt completion
                        conn.execute(
                            """UPDATE source_operation_attempt
                               SET status = ?, completed_at = ?, http_status = ?, error_code = ?, retry_count = ?, parser_version = ?, dto_version = ?, evidence_bundle_id = ?, selectable = ?, diagnostics = ?
                               WHERE id = ?""",
                            (
                                res.status,
                                datetime.now(UTC).isoformat(),
                                res.http_status,
                                res.error_code,
                                res.retry_count,
                                res.parser_version,
                                res.normalization_version,
                                res.bundle_id,
                                1 if res.status == SourceResultStatus.SUCCESS else 0,
                                json.dumps(res.parser_diagnostics),
                                attempt_id
                            )
                        )
                        
                        if res.status == SourceResultStatus.SUCCESS:
                            selected_provider = provider
                            selected_result = res
                            break
                            
                    # If no provider succeeded, record failure/empty status
                    if not selected_result:
                        # Create a failed/empty observation
                        obs = create_observation(
                            canonical_fixture_id=canonical_fixture_id,
                            team_id=fixture.home_team_id,
                            capability=cap,
                            source="none",
                            request_identity=f"GET /football/{cap}/{canonical_fixture_id}",
                            status="NOT_SUPPORTED",
                            valid_at=analysis_cutoff_at.isoformat(),
                        )
                        obs_id = cap_repo.save_observation(obs)
                        
                        proj = create_projection(
                            canonical_fixture_id=canonical_fixture_id,
                            team_id=fixture.home_team_id,
                            capability=cap,
                            analysis_cutoff_at=analysis_cutoff_at.isoformat(),
                            selected_source="none",
                            selected_status="NOT_SUPPORTED",
                            selected_observation_id=obs_id,
                            primary_source="none",
                            primary_status="NOT_SUPPORTED",
                            snapshot_run_id=run_id
                        )
                        cap_repo.save_projection(proj)
                        continue
                        
                    # Save observation and projection
                    payload_json = json.dumps(to_dict(selected_result.value))
                    payload_sha256 = hashlib.sha256(payload_json.encode()).hexdigest()
                    
                    obs = create_observation(
                        canonical_fixture_id=canonical_fixture_id,
                        team_id=fixture.home_team_id,
                        capability=cap,
                        source=selected_provider,
                        request_identity=selected_result.request_identity,
                        status=selected_result.status,
                        valid_at=analysis_cutoff_at.isoformat(),
                        evidence_bundle_id=selected_result.bundle_id,
                        native_fixture_id=native_fixture_id,
                        native_team_id=native_home_id,
                        http_status=selected_result.http_status,
                        error_code=selected_result.error_code,
                        parser_version=selected_result.parser_version,
                        parser_diagnostics=dict(selected_result.parser_diagnostics),
                        payload_sha256=payload_sha256,
                        payload_json=payload_json,
                        dto_version="1.0",
                        evidence_package_id=selected_result.bundle_id,
                    )
                    obs_id = cap_repo.save_observation(obs)
                    selected_obs_ids.append(obs_id)
                    
                    proj = create_projection(
                        canonical_fixture_id=canonical_fixture_id,
                        team_id=fixture.home_team_id,
                        capability=cap,
                        analysis_cutoff_at=analysis_cutoff_at.isoformat(),
                        selected_source=selected_provider,
                        selected_status=selected_result.status,
                        selected_observation_id=obs_id,
                        primary_source=selected_provider,
                        primary_status=selected_result.status,
                        snapshot_run_id=run_id
                    )
                    cap_repo.save_projection(proj)
                    
                    # Write selection history automatically
                    conn.execute(
                        """INSERT INTO capability_selection_history
                           (canonical_fixture_id, team_id, capability, analysis_cutoff_at, selected_observation_id, selected_source, selected_status, recorded_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            canonical_fixture_id,
                            fixture.home_team_id,
                            cap,
                            analysis_cutoff_at.isoformat(),
                            obs_id,
                            selected_provider,
                            selected_result.status,
                            datetime.now(UTC).isoformat()
                        )
                    )
                    
                    # Assign to snapshot fields
                    if cap == "current_recent_form":
                        home_form_matches = selected_result.value
                    elif cap == "h2h_head_to_head":
                        h2h_matches = selected_result.value
                    elif cap == "standings_competition_context":
                        standings_table = selected_result.value

                # 5. Build and publish snapshot
                snapshot = FootballEnrichmentSnapshot(
                    run_id=str(run_id),
                    snapshot_id=f"snap_{canonical_fixture_id}_{analysis_cutoff_at.strftime('%Y%m%dT%H%M%S')}",
                    snapshot_state="COMPLETE",
                    canonical_fixture_id=canonical_fixture_id,
                    analysis_cutoff_at=analysis_cutoff_at,
                    kickoff_at=datetime.fromisoformat(fixture.kickoff.replace("Z", "+00:00")),
                    event_status=fixture.status,
                    competition_canonical_id=fixture.competition_id,
                    home_participant=NormalizedParticipant(
                        canonical_id=fixture.home_team_id,
                        name=home_team.name,
                        role="HOME"
                    ),
                    away_participant=NormalizedParticipant(
                        canonical_id=fixture.away_team_id,
                        name=away_team.name,
                        role="AWAY"
                    ),
                    home_form=tuple(home_form_matches),
                    away_form=tuple(away_form_matches),
                    h2h_records=tuple(h2h_matches),
                    standings=standings_table,
                    bundle_ids=tuple(row["evidence_bundle_id"] for row in conn.execute("SELECT DISTINCT evidence_bundle_id FROM fixture_capability_observation WHERE canonical_fixture_id = ? AND evidence_bundle_id != ''", (canonical_fixture_id,)).fetchall()),
                )

                snapshot_json = json.dumps(to_dict(snapshot))
                snapshot_hash = canonical_hash(snapshot)

                # Save snapshot to analysis_snapshot table
                conn.execute(
                    """INSERT INTO analysis_snapshot
                       (schema_version, run_id, canonical_fixture_id, analysis_cutoff_at, status, snapshot_hash, payload_json, created_at, published_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        "1.0",
                        run_id,
                        canonical_fixture_id,
                        analysis_cutoff_at.isoformat(),
                        "COMPLETE",
                        snapshot_hash,
                        snapshot_json,
                        now_str,
                        now_str,
                    ),
                )

                # Update run status to COMPLETE
                conn.execute(
                    "UPDATE sports_enrichment_run SET status = 'COMPLETE', completed_at = ? WHERE id = ?",
                    (now_str, run_id),
                )
                conn.execute("RELEASE SAVEPOINT enrich_fixture")
                return snapshot
                
            except Exception as e:
                conn.execute("ROLLBACK TO SAVEPOINT enrich_fixture")
                conn.execute("RELEASE SAVEPOINT enrich_fixture")
                _record_failed_run(canonical_fixture_id, analysis_cutoff_at, str(e))
                raise


def _record_failed_run(canonical_fixture_id: int, cutoff: datetime, reason: str) -> None:
    from bet.db.connection import get_db
    with get_db() as conn:
        now_str = datetime.now(UTC).isoformat()
        run_identity = hashlib.sha256(
            f"football|{canonical_fixture_id}|{cutoff.isoformat()}|failed|{now_str}".encode()
        ).hexdigest()
        conn.execute(
            """INSERT INTO sports_enrichment_run
               (run_identity, sport, canonical_event_id, analysis_cutoff_at, status, started_at, completed_at, policy_config_hash, requested_capabilities, failure_reason)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run_identity,
                "football",
                canonical_fixture_id,
                cutoff.isoformat(),
                "FAILED",
                now_str,
                now_str,
                "error",
                "",
                reason,
            ),
        )
        conn.commit()


def create_football_enrichment_service(
    espn_client: ESPNClient | None = None,
    api_football_client: APIFootballClient | None = None,
) -> FootballEnrichmentService:
    registry = FootballAdapterRegistry()
    
    if not espn_client:
        espn_client = ESPNClient(sport="football", league="eng.1", rate_limiter=RateLimiter())
    registry.register("espn", ESPNFootballAdapter(espn_client))
    
    if not api_football_client:
        api_football_client = APIFootballClient(rate_limiter=RateLimiter())
    registry.register("api-football", APIFootballCandidateAdapter(api_football_client))
    
    return FootballEnrichmentService(registry)
