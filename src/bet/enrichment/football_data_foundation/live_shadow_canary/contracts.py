from dataclasses import dataclass
from dataclasses import field
from typing import Any
from typing import Dict
from typing import List
from typing import Optional


@dataclass(frozen=True)
class OfficialFixtureContext:
    fixture_slug: str
    competition_name: str
    official_source_url: str
    official_source_name: str
    match_id: Optional[str] = None
    home_team: Optional[str] = None
    away_team: Optional[str] = None
    kickoff_at: Optional[str] = None
    venue: Optional[str] = None
    city: Optional[str] = None
    raw_payload_stored: bool = False
    selectable_for_production: bool = False


@dataclass(frozen=True)
class ProviderProbeResult:
    provider: str
    credential_env: str
    credential_present: bool
    status: str
    request_attempted: bool
    evidence_claim_count: int
    error: Optional[str] = None
    selectable_for_production: bool = False


@dataclass(frozen=True)
class LiveShadowCanarySummary:
    run_id: str
    status: str
    official_context: Dict[str, Any]
    provider_results: List[Dict[str, Any]]
    fusion_summary: Optional[Dict[str, Any]] = None
    certification_result: Optional[Dict[str, Any]] = None
    network_used: bool = False
    provider_network_calls: int = 0
    manual_authorization_required: bool = True
    selectable_for_production: bool = False
    no_betting_decisions: bool = True
    no_db_writes: bool = True
