from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List


class Provider(str, Enum):
    SPORTDB = "sportdb"
    FOOTBALL_DATA_ORG = "football-data-org"
    HIGHLIGHTLY = "highlightly"
    API_FOOTBALL = "api-football"
    ESPN_BASELINE = "espn-baseline"


class CaptureStatus(str, Enum):
    FETCHED = "FETCHED"
    SKIPPED_CREDENTIALS_MISSING = "SKIPPED_CREDENTIALS_MISSING"
    SKIPPED_PROVIDER_NOT_CONFIGURED = "SKIPPED_PROVIDER_NOT_CONFIGURED"
    BLOCKED_PROVIDER_MAPPING_MISSING = "BLOCKED_PROVIDER_MAPPING_MISSING"
    BLOCKED_OFFICIAL_CONTEXT_UNAVAILABLE = "BLOCKED_OFFICIAL_CONTEXT_UNAVAILABLE"
    FAILED_HTTP = "FAILED_HTTP"
    FAILED_PARSE = "FAILED_PARSE"
    FAILED_PROVIDER_ERROR = "FAILED_PROVIDER_ERROR"


@dataclass(frozen=True)
class ProviderResponseEnvelope:
    provider: str
    status: str
    fixture_slug: str
    source_url: str | None
    captured_at_utc: str
    status_code: int | None = None
    body: Any = None
    body_sha256: str | None = None
    error: str | None = None
    raw_headers_stored: bool = False
    secrets_stored: bool = False
    selectable_for_production: bool = False

    def validate(self) -> None:
        if self.raw_headers_stored:
            raise ValueError("raw_headers_stored must be False")
        if self.secrets_stored:
            raise ValueError("secrets_stored must be False")
        if self.selectable_for_production:
            raise ValueError("selectable_for_production must be False")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "status": self.status,
            "fixture_slug": self.fixture_slug,
            "source_url": self.source_url,
            "captured_at_utc": self.captured_at_utc,
            "status_code": self.status_code,
            "body": self.body,
            "body_sha256": self.body_sha256,
            "error": self.error,
            "raw_headers_stored": self.raw_headers_stored,
            "secrets_stored": self.secrets_stored,
            "selectable_for_production": self.selectable_for_production,
        }


@dataclass(frozen=True)
class LiveCorpusManifest:
    run_id: str
    run_started_at_utc: str
    target_date_utc: str
    fixture_count: int
    provider_count: int
    fetched_count: int
    skipped_count: int
    failed_count: int
    credentials_present: Dict[str, bool]
    files_written: List[str]
    selectable_for_production: bool = False

    def validate(self) -> None:
        if self.selectable_for_production:
            raise ValueError("selectable_for_production must be False")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "run_started_at_utc": self.run_started_at_utc,
            "target_date_utc": self.target_date_utc,
            "fixture_count": self.fixture_count,
            "provider_count": self.provider_count,
            "fetched_count": self.fetched_count,
            "skipped_count": self.skipped_count,
            "failed_count": self.failed_count,
            "credentials_present": self.credentials_present,
            "files_written": self.files_written,
            "selectable_for_production": self.selectable_for_production,
        }
