from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

SHADOW_ONLY_STATUS = "WORLD_CUP_2026_24_JUNE_LIVE_SHADOW_COMPLETE"

@dataclass(frozen=True)
class FixtureSpec:
    slug: str
    home_team: str
    away_team: str
    group: str
    kickoff_utc_or_unknown: str
    official_context_status: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProviderCaptureEnvelope:
    fixture_slug: str
    provider: str
    request_purpose: str
    source_url: Optional[str]
    status: str
    status_code: Optional[int]
    body: Any
    body_sha256: str
    captured_at_utc: str
    sanitized: bool = True
    headers_retained: bool = False
    secrets_stored: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LiveFixtureShadowSnapshot:
    fixture_slug: str
    provider_ids: Dict[str, str]
    provider_fact_counts: Dict[str, int]
    score: Dict[str, Optional[int]]
    status: str
    kickoff: str
    conflicts: List[Any]
    source_files: List[str]
    activation_candidate_status: str
    production_selectable: bool = False
    manual_authorization_required: bool = True
    betting_decisions_allowed: bool = False
    production_db_write_allowed: bool = False
    live_network_used: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LiveShadowRunSummary:
    run_id: str
    fixture_count: int
    fixtures_attempted: List[str]
    fixtures_shadow_ready: List[str]
    fixtures_blocked: List[str]
    provider_matrix: Dict[str, Dict[str, str]]
    secret_leak_check: str
    production_guardrail_check: str
    betting_decision_check: str
    activation_bridge_success_count: int
    final_status: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
