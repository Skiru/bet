"""Typed contracts for compliant tipster ingestion.

These objects are intentionally independent from HTTP/Playwright so the parser
layer is deterministic, unit-testable, and safe to run in CI without network.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal


class SourceTier(str, Enum):
    STRUCTURED = "structured"
    HTML_STATIC = "html_static"
    HTML_DYNAMIC = "html_dynamic"
    MANUAL_REVIEW = "manual_review"


class ComplianceVerdict(str, Enum):
    ALLOW = "allow"
    BLOCK_ROBOTS = "block_robots"
    BLOCK_TERMS = "block_terms"
    BLOCK_AUTH_REQUIRED = "block_auth_required"
    BLOCK_ANTI_BOT = "block_anti_bot"
    UNKNOWN_REVIEW_REQUIRED = "unknown_review_required"


class ExtractorVerdict(str, Enum):
    OK = "ok"
    EMPTY = "empty"
    LOW_QUALITY = "low_quality"
    PARSE_ERROR = "parse_error"


MarketFamily = Literal[
    "goals",
    "corners",
    "cards",
    "shots",
    "fouls",
    "tennis_games",
    "basketball_points",
    "hockey_total",
    "winner",
    "btts",
    "handicap",
    "correct_score",
    "unknown",
]

Direction = Literal[
    "OVER",
    "UNDER",
    "WIN",
    "DRAW",
    "BTTS_YES",
    "BTTS_NO",
    "HOME",
    "AWAY",
    "DC",
    "DNB",
    "OTHER",
]


@dataclass(frozen=True)
class SourcePolicy:
    source_id: str
    display_name: str
    base_url: str
    tier: SourceTier
    sports: tuple[str, ...]
    entrypoints: tuple[str, ...]
    robots_required: bool = True
    terms_review_required: bool = True
    allow_playwright: bool = False
    allow_xhr_capture: bool = False
    allow_authenticated: bool = False
    max_pages_per_run: int = 12
    min_delay_seconds: float = 2.0
    parser_strategy: str = "generic_public_html"
    data_role: str = "cross_check"
    affiliate_bias_risk: str = "medium"
    production_status: str = "shadow_only"
    notes: str = ""


@dataclass
class ComplianceCheck:
    source_id: str
    url: str
    verdict: ComplianceVerdict
    robots_allowed: bool | None = None
    terms_reviewed: bool = False
    reason: str = ""
    checked_at_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class RawDocument:
    source_id: str
    url: str
    fetched_at_utc: str
    html: str
    status_code: int | None = None
    content_type: str | None = None
    final_url: str | None = None


@dataclass
class TipsterPick:
    source_id: str
    source_name: str
    sport: str
    event: str
    home_team: str
    away_team: str
    market: str
    market_family: MarketFamily
    direction: Direction
    line: float | None = None
    odds_decimal: float | None = None
    confidence_label: str = "source_claim"
    reasoning: str = ""
    stats_cited: list[str] = field(default_factory=list)
    tipster_name: str | None = None
    competition: str | None = None
    published_at: str | None = None
    source_url: str | None = None
    # The fixture's own date (YYYY-MM-DD) as the source states it, distinct from
    # extracted_at_utc. Without it a pick cannot be attributed to a betting day,
    # and a page that lists several days -- which every one of these sources
    # does -- silently contributes yesterday's opinions to today's column.
    match_date: str | None = None
    kickoff_time: str | None = None
    # A parlay: its legs do not resolve independently, so it is never a
    # single-market opinion. Flagged at extraction so the consensus layer does
    # not have to re-derive it from prose.
    is_combo: bool = False
    # Already resolved at the source. A settled claim is a historical record,
    # not a read on an upcoming fixture.
    is_settled: bool = False
    tipster_accuracy_pct: int | None = None
    tipster_bet_count: int | None = None
    source_ref: str | None = None
    extracted_at_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    extraction_quality: float = 0.0
    warnings: list[str] = field(default_factory=list)
    valuable_signals: dict[str, list[str]] = field(default_factory=dict)
    source_record_type: str = "source_claim"
    pipeline_use: list[str] = field(default_factory=lambda: ["s2_tipster_evidence", "s3_context_cross_check"])

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ExtractionResult:
    source_id: str
    url: str
    verdict: ExtractorVerdict
    picks: list[TipsterPick]
    warnings: list[str] = field(default_factory=list)
    parser_version: str = "tipster_parser_v2"
    extracted_at_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    block_reason: str | None = None
    robots_blocked_live: bool = False
    live_fetch_allowed: bool = True
    fallback: str | None = None
    skip_reason: str | None = None
    required_flags_missing: list[str] = field(default_factory=list)
    invalid_attestation: list[str] = field(default_factory=list)
    expected_visible_count: int | None = None
    extracted_count: int | None = None
    coverage_ratio: float | None = None
    coverage_status: str | None = None

    @property
    def pick_count(self) -> int:
        return len(self.picks)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
