from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

@dataclass(frozen=True)
class NormalizedFact:
    source: str
    source_role: str
    fact_type: str
    key: str
    value: Any
    provider_match_id: Optional[str]
    body_sha256: str
    source_file: str
    confidence: float = 1.0
    production_selectable: bool = False
    notes: List[str] = field(default_factory=list)

    def to_json(self) -> Dict[str, Any]:
        data = asdict(self)
        return data

@dataclass(frozen=True)
class NormalizedMatchSnapshot:
    fixture_slug: str
    provider_ids: Dict[str, str]
    teams: Dict[str, str]
    status: Optional[str]
    score: Dict[str, Optional[int]]
    kickoff_utc: Optional[str]
    competition: Optional[str]
    venue: Optional[str]
    referee: Optional[str]
    facts: List[NormalizedFact] = field(default_factory=list)
    conflicts: List[Dict[str, Any]] = field(default_factory=list)
    source_priority: List[str] = field(default_factory=lambda: [
        "api-football",
        "sportdb",
        "highlightly",
        "football-data-org",
        "espn-baseline"
    ])
    production_selectable: bool = False
    manual_authorization_required: bool = True
    shadow_status: str = "SHADOW_ENRICHMENT_READY_FOR_MANUAL_REVIEW"

    def to_json(self) -> Dict[str, Any]:
        data = asdict(self)
        data["facts"] = [fact.to_json() for fact in self.facts]
        return data

@dataclass(frozen=True)
class NetworkProbeResult:
    runner_executed_under_socket_block: bool
    network_attempts_detected: int
    socket_blocking_mode: str
    output_root: str

@dataclass(frozen=True)
class PublicRawResult:
    path: str
    line_count: int
    max_line_length: int
    ast_parse_ok: bool
    collapsed: bool
    failures: Tuple[str, ...] = field(default_factory=tuple)

    @property
    def passed(self) -> bool:
        return not self.failures

@dataclass(frozen=True)
class ArtifactBlobResult:
    path: str
    size_bytes: int
    sqlite_header_ok: bool
    required_tables_present: bool
    facts_row_count: int
    provider_count: int
    provider_row_counts: Dict[str, int] = field(default_factory=dict)
    failures: Tuple[str, ...] = field(default_factory=tuple)

    @property
    def passed(self) -> bool:
        return not self.failures
