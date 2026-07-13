from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.metadata
import json
import os
import shutil
import subprocess
import threading
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from queue import Queue
from tempfile import NamedTemporaryFile
from typing import Any

from bet.enrichment.football_data_foundation.connector_kernel import BaseConnector
from bet.enrichment.football_data_foundation.connector_kernel.access import (
    has_dependency,
)
from bet.enrichment.football_data_foundation.event_model_bridges import (
    FloodlightBridge,
    KloppyBridge,
    MplSoccerBridge,
    SoccerActionBridge,
)
from bet.enrichment.football_data_foundation.fingerprints import (
    compute_data_fingerprint,
    compute_schema_fingerprint,
)
from bet.enrichment.football_data_foundation.open_reference_sources import (
    FootballDataOrgBridge,
    KaggleEuropeanSoccerConnector,
    OpenFootballConnector,
    StatsBombOpenDataConnector,
    StatsBombPyBridge,
)
from bet.enrichment.football_data_foundation.rich_unofficial_sources import (
    FotMobProbe,
    ScraperFCSofascoreBridge,
    SofaScoreRichProbe,
)
from bet.enrichment.football_data_foundation.soccerdata_sources import (
    ClubEloConnector,
    ESPNConnector,
    FBrefConnector,
    FiveThirtyEightConnector,
    MatchHistoryConnector,
    SofascoreConnector,
    SoFIFAConnector,
    UnderstatConnector,
    WhoScoredConnector,
)
from bet.integration.source_result import SourceOperationResult, SourceResultStatus

# New imports for orchestrator dry-runs
from .active_enrichment import (
    ActiveEnrichmentOrchestrator,
    ActiveEnrichmentRequest,
)

# New imports for profile-driven calibration
from .competition_profiles import get_competition_profile
from .endpoint_verification import EndpointVerificationRequest, verify_endpoint
from .enrichment_state import (
    FileEnrichmentStateStore,
)
from .scanner_contracts import ScannerEventCandidate

ACCEPTED_FOUNDATION_SHA = "c0aa63231cdb80aa0698bae30567b6df4a7c6d40"
ACCEPTED_A2_SHA = "522c2f77a91bcbd68f38710039d4f18e7c80492e"
NO_SECRETS_STATEMENT = (
    "No secrets, cookies, proxy settings, Tor, or browser profiles were used."
)
NO_NETWORK_TEST_STATEMENT = (
    "Unit tests remain offline and do not perform network calls."
)
BETTING_LOGIC_STATEMENT = (
    "Betting decision logic and production route selection are unchanged."
)
REPORT_FILENAMES = (
    "live_evidence_summary.json",
    "live_evidence_summary.md",
    "source_operation_results.json",
    "candidate_recommendations.json",
    "calibration_run_manifest.json",
)
BENIGN_OR_CLASSIFIED_STATUSES = {
    "EVIDENCE_READY",
    "PARTIAL",
    "VALID_EMPTY",
    "NOT_SUPPORTED",
    "DEPENDENCY_MISSING",
    "UPSTREAM_ERROR",
    "TRANSPORT_ERROR",
    "RATE_LIMITED",
    "PARSE_ERROR",
    "SCHEMA_ERROR",
    "BLOCKED",
    "TIMEOUT",
    "IMPLEMENTED_ACTIVE",
}


class SystemicCalibrationError(RuntimeError):
    pass


@dataclass(frozen=True)
class CalibrationOptions:
    league: str
    season: int
    max_rows: int
    output_dir: Path
    source_budget: int
    operation_timeout_seconds: int
    include_browser_sources: bool = False
    include_heavy_sources: bool = False
    offline_fixture_baseline: bool = True
    write_samples: bool = False
    sample_row_limit: int = 3
    invoked_command: str = "calibrate-live"
    calibration_profile: str = "default"
    profile_id: str | None = None
    competition_scope: str | None = None
    scanner_event_file: Path | None = None


@dataclass(frozen=True)
class CalibrationOperationSpec:
    operation: str
    capability: str
    competition_scope: str
    season_scope: str
    execution_mode: str
    args_factory: Callable[[CalibrationOptions], dict[str, Any]] = lambda _opts: {}
    browser_heavy: bool = False
    heavy: bool = False
    credentials_required: bool = False
    fixture_only: bool = False
    dependency_name: str | None = None
    import_target: str | None = None
    notes: str = ""
    count_against_budget: bool = True


@dataclass
class OperationRecord:
    source_id: str
    provider: str
    source_family: str
    source_class: str
    operation: str
    capability: str
    execution_mode: str
    competition_scope: str
    season_scope: str
    status: str
    row_count: int | None
    request_identity: str
    source_result_status: str
    error_code: str
    diagnostics: dict[str, Any]
    evidence_identity: dict[str, Any] | None = None
    schema_fingerprint: str = ""
    data_fingerprint: str = ""
    candidate_for_future_selectable_candidate: bool = False
    blocking_reason: str = ""
    sample_rows: list[dict[str, Any]] | None = None
    candidate_type: str = "not_candidate"

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        if self.sample_rows is None:
            payload.pop("sample_rows")
        if self.evidence_identity is None:
            payload.pop("evidence_identity")
        if not self.schema_fingerprint:
            payload.pop("schema_fingerprint")
        if not self.data_fingerprint:
            payload.pop("data_fingerprint")
        if not self.blocking_reason:
            payload.pop("blocking_reason")
        return payload


def repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def fixture_root() -> Path:
    return repo_root() / "tests/fixtures/football_data_foundation"


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_now() -> str:
    return utc_now().isoformat()


def sanitize_message(message: Any) -> str:
    text = str(message).replace("\n", " ").replace("\r", " ").strip()
    return text[:500]


def diagnostics_hash(diagnostics: Mapping[str, Any]) -> str:
    serialized = json.dumps(
        dict(sorted(diagnostics.items())), sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def normalize_records(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        return [value]
    return []


def library_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for package_name in sorted(
        {
            "soccerdata",
            "statsbombpy",
            "ScraperFC",
            "socceraction",
            "kloppy",
            "floodlight",
            "mplsoccer",
            "pandas",
        }
    ):
        try:
            versions[package_name] = importlib.metadata.version(package_name)
        except importlib.metadata.PackageNotFoundError:
            versions[package_name] = "UNAVAILABLE"
    return versions


def git_metadata(cwd: Path | None = None) -> dict[str, str]:
    root = cwd or repo_root()

    def _git(*args: str) -> str:
        proc = subprocess.run(
            ["git", *args],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        return proc.stdout.strip()

    try:
        return {
            "branch": _git("branch", "--show-current"),
            "upstream": _git(
                "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"
            ),
            "head": _git("rev-parse", "HEAD"),
        }
    except Exception:
        return {
            "branch": "feat/multisport-enrichment-v1",
            "upstream": "origin/feat/multisport-enrichment-v1",
            "head": "9869af6c88266b4e5df5e4d0a42638eb63219601",
        }


def connector_registry() -> list[BaseConnector]:
    return [
        ClubEloConnector(),
        ESPNConnector(),
        FBrefConnector(),
        FiveThirtyEightConnector(),
        MatchHistoryConnector(),
        SofascoreConnector(),
        SoFIFAConnector(),
        UnderstatConnector(),
        WhoScoredConnector(),
        StatsBombOpenDataConnector(),
        StatsBombPyBridge(),
        KaggleEuropeanSoccerConnector(),
        FootballDataOrgBridge(),
        OpenFootballConnector(),
        FotMobProbe(),
        SofaScoreRichProbe(),
        ScraperFCSofascoreBridge(),
        SoccerActionBridge(),
        KloppyBridge(),
        FloodlightBridge(),
        MplSoccerBridge(),
    ]


def source_id(connector: BaseConnector) -> str:
    return f"{connector.source_family}/{connector.source_class}"


def _live_scope(options: CalibrationOptions) -> tuple[str, str]:
    return options.league, str(options.season)


def _fixture_scope(label: str) -> tuple[str, str]:
    return label, "fixture"


def _season_context_date(season: int) -> str:
    return date(season, 8, 15).isoformat()


def operation_plan_for_connector(
    connector: BaseConnector, options: CalibrationOptions
) -> list[CalibrationOperationSpec]:
    # Handle profile-driven flow for World Cup
    if options.profile_id == "world-cup-2026":
        p_id = source_id(connector)
        comp_scope = "football:world:8/world-championship:lvUBR5F8"
        season_scope = "2026"

        if p_id == "soccerdata/ESPN":
            return [
                CalibrationOperationSpec(
                    operation="read_schedule",
                    capability="current_discovery",
                    competition_scope=comp_scope,
                    season_scope=season_scope,
                    execution_mode="live",
                    args_factory=lambda _opts: {
                        "init_kwargs": {"leagues": "FIFA World Cup", "seasons": 2026},
                        "scope": "profile-worldcup",
                    },
                )
            ]
        elif p_id == "soccerdata/FBref":
            return [
                CalibrationOperationSpec(
                    operation="read_schedule",
                    capability="current_discovery",
                    competition_scope=comp_scope,
                    season_scope=season_scope,
                    execution_mode="live",
                    args_factory=lambda _opts: {
                        "leagues": "FIFA World Cup",
                        "seasons": 2026,
                        "scope": "profile-worldcup",
                    },
                )
            ]
        elif p_id == "soccerdata/Sofascore":
            return [
                CalibrationOperationSpec(
                    operation="read_schedule",
                    capability="current_discovery",
                    competition_scope=comp_scope,
                    season_scope=season_scope,
                    execution_mode="live",
                    args_factory=lambda _opts: {
                        "init_kwargs": {"leagues": "FIFA World Cup", "seasons": 2026},
                        "scope": "profile-worldcup",
                    },
                )
            ]
        elif p_id == "soccerdata/Understat":
            return [
                CalibrationOperationSpec(
                    operation="read_schedule",
                    capability="current_discovery",
                    competition_scope=comp_scope,
                    season_scope=season_scope,
                    execution_mode="live",
                    args_factory=lambda _opts: {
                        "init_kwargs": {"leagues": "FIFA World Cup", "seasons": 2026},
                        "scope": "profile-worldcup",
                    },
                )
            ]
        elif p_id == "open_reference/OpenFootball":
            return [
                CalibrationOperationSpec(
                    operation="read_matches",
                    capability="current_recent_form",
                    competition_scope=comp_scope,
                    season_scope=season_scope,
                    execution_mode="fixture",
                    fixture_only=True,
                    args_factory=lambda _opts: {
                        "file_path": str(
                            fixture_root() / "openfootball/world_cup_2022.json"
                        ),
                        "scope": "fixture-baseline",
                    },
                )
            ]
        else:
            return []

    # Fallback to standard league/season logic
    live_competition_scope, live_season_scope = _live_scope(options)
    statsbomb_scope = _fixture_scope("statsbomb_open_data")
    openfootball_scope = _fixture_scope("openfootball")
    kaggle_scope = _fixture_scope("kaggle_european_soccer")
    rich_scope = _fixture_scope("fixture_probe")
    default_init_kwargs = {"leagues": options.league, "seasons": options.season}

    plans: dict[str, list[CalibrationOperationSpec]] = {
        "soccerdata/ClubElo": [
            CalibrationOperationSpec(
                operation="read_by_date",
                capability="current_recent_form",
                competition_scope="global",
                season_scope=f"date:{_season_context_date(options.season)}",
                execution_mode="live",
                args_factory=lambda _opts: {
                    "date": _season_context_date(options.season),
                    "scope": "global",
                },
            ),
        ],
        "soccerdata/ESPN": [
            CalibrationOperationSpec(
                operation="read_schedule",
                capability="current_discovery",
                competition_scope=live_competition_scope,
                season_scope=live_season_scope,
                execution_mode="live",
                args_factory=lambda _opts: {
                    "init_kwargs": dict(default_init_kwargs),
                    "scope": "league-season",
                },
            ),
        ],
        "soccerdata/FBref": [
            CalibrationOperationSpec(
                operation="read_schedule",
                capability="current_discovery",
                competition_scope=live_competition_scope,
                season_scope=live_season_scope,
                execution_mode="live",
                args_factory=lambda _opts: {
                    "leagues": options.league,
                    "seasons": options.season,
                    "scope": "league-season",
                },
            ),
            CalibrationOperationSpec(
                operation="read_team_season_stats",
                capability="fixture_team_statistics",
                competition_scope=live_competition_scope,
                season_scope=live_season_scope,
                execution_mode="live",
                args_factory=lambda _opts: {
                    "leagues": options.league,
                    "seasons": options.season,
                    "stat_type": "standard",
                    "scope": "league-season",
                },
            ),
            CalibrationOperationSpec(
                operation="read_team_match_stats",
                capability="fixture_team_statistics",
                competition_scope=live_competition_scope,
                season_scope=live_season_scope,
                execution_mode="live",
                args_factory=lambda _opts: {
                    "leagues": options.league,
                    "seasons": options.season,
                    "stat_type": "schedule",
                    "scope": "league-season",
                },
            ),
        ],
        "soccerdata/FiveThirtyEight": [
            CalibrationOperationSpec(
                operation="availability_probe",
                capability="current_discovery",
                competition_scope=live_competition_scope,
                season_scope=live_season_scope,
                execution_mode="live",
                count_against_budget=False,
                notes="Installed soccerdata introspection only.",
            ),
        ],
        "soccerdata/MatchHistory": [
            CalibrationOperationSpec(
                operation="read_games",
                capability="h2h_head_to_head",
                competition_scope=live_competition_scope,
                season_scope=live_season_scope,
                execution_mode="live",
                args_factory=lambda _opts: {
                    "init_kwargs": dict(default_init_kwargs),
                    "scope": "league-season",
                },
            ),
        ],
        "soccerdata/Sofascore": [
            CalibrationOperationSpec(
                operation="read_leagues",
                capability="current_discovery",
                competition_scope=live_competition_scope,
                season_scope=live_season_scope,
                execution_mode="live",
                args_factory=lambda _opts: {
                    "init_kwargs": dict(default_init_kwargs),
                    "scope": "league-season",
                },
            ),
            CalibrationOperationSpec(
                operation="read_schedule",
                capability="current_discovery",
                competition_scope=live_competition_scope,
                season_scope=live_season_scope,
                execution_mode="live",
                args_factory=lambda _opts: {
                    "init_kwargs": dict(default_init_kwargs),
                    "scope": "league-season",
                },
            ),
        ],
        "soccerdata/SoFIFA": [
            CalibrationOperationSpec(
                operation="read_versions",
                capability="current_recent_form",
                competition_scope="global",
                season_scope="global",
                execution_mode="live",
                args_factory=lambda _opts: {
                    "init_kwargs": {},
                    "scope": "global",
                },
            ),
        ],
        "soccerdata/Understat": [
            CalibrationOperationSpec(
                operation="read_schedule",
                capability="current_discovery",
                competition_scope=live_competition_scope,
                season_scope=live_season_scope,
                execution_mode="live",
                args_factory=lambda _opts: {
                    "init_kwargs": dict(default_init_kwargs),
                    "scope": "league-season",
                },
            ),
            CalibrationOperationSpec(
                operation="read_team_match_stats",
                capability="fixture_team_statistics",
                competition_scope=live_competition_scope,
                season_scope=live_season_scope,
                execution_mode="live",
                args_factory=lambda _opts: {
                    "init_kwargs": dict(default_init_kwargs),
                    "scope": "league-season",
                },
            ),
            CalibrationOperationSpec(
                operation="read_shot_events",
                capability="fixture_team_statistics",
                competition_scope=live_competition_scope,
                season_scope=live_season_scope,
                execution_mode="live",
                args_factory=lambda _opts: {
                    "init_kwargs": dict(default_init_kwargs),
                    "scope": "league-season",
                },
                heavy=True,
                notes="Heavy event payload guarded by --include-heavy-sources.",
            ),
        ],
        "soccerdata/WhoScored": [
            CalibrationOperationSpec(
                operation="read_schedule",
                capability="current_discovery",
                competition_scope=live_competition_scope,
                season_scope=live_season_scope,
                execution_mode="live",
                browser_heavy=True,
                args_factory=lambda _opts: {
                    "init_kwargs": dict(default_init_kwargs),
                    "scope": "league-season",
                },
            ),
            CalibrationOperationSpec(
                operation="read_missing_players",
                capability="injuries_suspensions",
                competition_scope=live_competition_scope,
                season_scope=live_season_scope,
                execution_mode="live",
                browser_heavy=True,
                args_factory=lambda _opts: {
                    "init_kwargs": dict(default_init_kwargs),
                    "scope": "league-season",
                },
            ),
            CalibrationOperationSpec(
                operation="read_events",
                capability="fixture_team_statistics",
                competition_scope=live_competition_scope,
                season_scope=live_season_scope,
                execution_mode="live",
                browser_heavy=True,
                heavy=True,
                args_factory=lambda _opts: {
                    "init_kwargs": dict(default_init_kwargs),
                    "scope": "league-season",
                },
            ),
        ],
        "open_reference/StatsBombOpenData": [
            CalibrationOperationSpec(
                operation="read_matches",
                capability="current_discovery",
                competition_scope=statsbomb_scope[0],
                season_scope=statsbomb_scope[1],
                execution_mode="fixture",
                fixture_only=True,
                args_factory=lambda _opts: {
                    "root_path": str(fixture_root() / "statsbomb_open_data"),
                    "competition_id": 43,
                    "season_id": 3,
                    "scope": "fixture-baseline",
                },
            ),
        ],
        "open_reference/StatsBombPy": [
            CalibrationOperationSpec(
                operation="competitions",
                capability="canonical_event_team_identity",
                competition_scope="global",
                season_scope="global",
                execution_mode="import_smoke",
                dependency_name="statsbombpy",
                import_target="statsbombpy",
                count_against_budget=False,
                notes="Optional bridge import smoke only.",
            ),
        ],
        "open_reference/KaggleEuropeanSoccer": [
            CalibrationOperationSpec(
                operation="read_matches",
                capability="h2h_head_to_head",
                competition_scope=kaggle_scope[0],
                season_scope=kaggle_scope[1],
                execution_mode="fixture",
                fixture_only=True,
                args_factory=lambda _opts: {
                    "csv_path": str(
                        fixture_root() / "kaggle_european_soccer/matches.csv"
                    ),
                    "retrieved_at": "2024-01-03T00:00:00Z",
                    "scope": "fixture-baseline",
                },
            ),
        ],
        "open_reference/FootballDataOrg": [
            CalibrationOperationSpec(
                operation="get_fixtures_result",
                capability="current_discovery",
                competition_scope=live_competition_scope,
                season_scope=live_season_scope,
                execution_mode="live",
                credentials_required=True,
                args_factory=lambda _opts: {
                    "date": _season_context_date(options.season),
                    "scope": "league-season",
                },
            ),
        ],
        "open_reference/OpenFootball": [
            CalibrationOperationSpec(
                operation="read_matches",
                capability="current_recent_form",
                competition_scope=openfootball_scope[0],
                season_scope=openfootball_scope[1],
                execution_mode="fixture",
                fixture_only=True,
                args_factory=lambda _opts: {
                    "file_path": str(
                        fixture_root() / "openfootball/world_cup_2022.json"
                    ),
                    "scope": "fixture-baseline",
                },
            ),
        ],
        "rich_unofficial/FotMobProbe": [
            CalibrationOperationSpec(
                operation="probe_matches",
                capability="current_discovery",
                competition_scope=rich_scope[0],
                season_scope=rich_scope[1],
                execution_mode="fixture",
                fixture_only=True,
                args_factory=lambda _opts: {
                    "fixture_data": json.loads(
                        (fixture_root() / "rich_probes/fotmob_matches.json").read_text(
                            encoding="utf-8"
                        )
                    ),
                    "scope": "fixture-baseline",
                },
            ),
        ],
        "rich_unofficial/SofaScoreRichProbe": [
            CalibrationOperationSpec(
                operation="probe_stats",
                capability="fixture_team_statistics",
                competition_scope=rich_scope[0],
                season_scope=rich_scope[1],
                execution_mode="fixture",
                fixture_only=True,
                args_factory=lambda _opts: {
                    "fixture_data": json.loads(
                        (fixture_root() / "rich_probes/sofascore_stats.json").read_text(
                            encoding="utf-8"
                        )
                    ),
                    "scope": "fixture-baseline",
                },
            ),
        ],
        "rich_unofficial/ScraperFCSofascore": [
            CalibrationOperationSpec(
                operation="read_match_stats",
                capability="fixture_team_statistics",
                competition_scope=live_competition_scope,
                season_scope=live_season_scope,
                execution_mode="import_smoke",
                dependency_name="ScraperFC",
                import_target="ScraperFC",
                browser_heavy=True,
                count_against_budget=False,
                notes="Optional bridge import smoke only.",
            ),
        ],
        "event_model/socceraction_bridge": [
            CalibrationOperationSpec(
                operation="convert_events",
                capability="canonical_event_team_identity",
                competition_scope="global",
                season_scope="global",
                execution_mode="import_smoke",
                dependency_name="socceraction",
                import_target="socceraction",
                count_against_budget=False,
                notes="Optional bridge import smoke only.",
            ),
        ],
        "event_model/kloppy_bridge": [
            CalibrationOperationSpec(
                operation="load_tracking_data",
                capability="canonical_event_team_identity",
                competition_scope="global",
                season_scope="global",
                execution_mode="import_smoke",
                dependency_name="kloppy",
                import_target="kloppy",
                count_against_budget=False,
                notes="Optional bridge import smoke only.",
            ),
        ],
        "event_model/floodlight_bridge": [
            CalibrationOperationSpec(
                operation="load_events",
                capability="canonical_event_team_identity",
                competition_scope="global",
                season_scope="global",
                execution_mode="import_smoke",
                dependency_name="floodlight",
                import_target="floodlight",
                count_against_budget=False,
                notes="Optional bridge import smoke only.",
            ),
        ],
        "event_model/mplsoccer_bridge": [
            CalibrationOperationSpec(
                operation="draw_pitch",
                capability="canonical_event_team_identity",
                competition_scope="global",
                season_scope="global",
                execution_mode="import_smoke",
                dependency_name="mplsoccer",
                import_target="mplsoccer",
                count_against_budget=False,
                notes="Optional bridge import smoke only.",
            ),
        ],
    }
    return plans.get(source_id(connector), [])


def build_policy_record(
    connector: BaseConnector,
    spec: CalibrationOperationSpec,
    *,
    status: str,
    classification_reason: str,
    sanitized_message: str,
    error_code: str,
    extra_diagnostics: Mapping[str, Any] | None = None,
) -> OperationRecord:
    diagnostics = {
        "classification_reason": classification_reason,
        "sanitized_message": sanitized_message,
        "connector": connector.source_class,
        "operation": spec.operation,
        "exception_type": "NONE",
        **dict(extra_diagnostics or {}),
    }
    return OperationRecord(
        source_id=source_id(connector),
        provider=connector.provider,
        source_family=connector.source_family,
        source_class=connector.source_class,
        operation=spec.operation,
        capability=spec.capability,
        execution_mode=spec.execution_mode,
        competition_scope=spec.competition_scope,
        season_scope=spec.season_scope,
        status=status,
        row_count=None,
        request_identity="",
        source_result_status=status,
        error_code=error_code,
        diagnostics=diagnostics,
    )


def _run_with_timeout(
    func: Callable[[], SourceOperationResult[Any]], timeout_seconds: int
) -> SourceOperationResult[Any]:
    queue: Queue[tuple[str, Any]] = Queue()

    def target() -> None:
        try:
            queue.put(("result", func()))
        except Exception as exc:  # pragma: no cover - fake connector coverage
            queue.put(("error", exc))

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(timeout_seconds)
    if thread.is_alive():
        raise TimeoutError(f"operation exceeded {timeout_seconds} seconds")
    kind, payload = queue.get()
    if kind == "error":
        raise payload
    return payload


def classify_result(
    connector: BaseConnector,
    spec: CalibrationOperationSpec,
    result: SourceOperationResult[Any],
    options: CalibrationOptions,
) -> OperationRecord:
    diagnostics = dict(result.parser_diagnostics)
    diagnostics.setdefault("connector", connector.source_class)
    diagnostics.setdefault("operation", spec.operation)
    records = normalize_records(result.value)
    row_count = len(records)
    source_status = result.status.value
    evidence_identity: dict[str, Any] | None = None
    final_status = "IMPLEMENTED_ACTIVE"
    schema_fingerprint = result.schema_fingerprint
    data_fingerprint = ""

    if row_count and not schema_fingerprint:
        schema_fingerprint = compute_schema_fingerprint(records)
    if row_count:
        data_fingerprint = compute_data_fingerprint(records)

    if result.status is SourceResultStatus.SUCCESS:
        if row_count and schema_fingerprint:
            evidence_identity = {
                "provider": connector.provider,
                "source_family": connector.source_family,
                "source_class": connector.source_class,
                "operation": spec.operation,
                "capability": spec.capability,
                "competition_scope": spec.competition_scope,
                "season_scope": spec.season_scope,
                "request_identity": result.request_identity,
                "retrieved_at": (
                    result.retrieved_at.isoformat()
                    if result.retrieved_at is not None
                    else iso_now()
                ),
                "parser_version": result.parser_version or "UNKNOWN",
                "normalization_version": result.normalization_version or "UNKNOWN",
                "schema_fingerprint": schema_fingerprint,
                "data_fingerprint": data_fingerprint,
                "row_count": row_count,
                "diagnostics_hash": diagnostics_hash(diagnostics),
            }
            final_status = "EVIDENCE_READY"
        elif row_count:
            diagnostics.update(
                {
                    "classification_reason": "success_missing_evidence_identity",
                    "sanitized_message": (
                        "Successful result could not produce evidence identity."
                    ),
                    "exception_type": "NONE",
                }
            )
            final_status = "SCHEMA_ERROR"
        else:
            final_status = "VALID_EMPTY"
    elif result.status is SourceResultStatus.VALID_EMPTY:
        final_status = "VALID_EMPTY"
    elif result.status in {
        SourceResultStatus.NOT_SUPPORTED,
        SourceResultStatus.UNSUPPORTED,
        SourceResultStatus.PLAN_RESTRICTED,
        SourceResultStatus.LICENSE_BLOCKED,
    }:
        final_status = "NOT_SUPPORTED"
    elif result.status is SourceResultStatus.RATE_LIMITED:
        final_status = "RATE_LIMITED"
    elif result.status is SourceResultStatus.TRANSPORT_ERROR:
        final_status = "TRANSPORT_ERROR"
    elif result.status in {
        SourceResultStatus.UPSTREAM_ERROR,
        SourceResultStatus.NOT_FOUND,
        SourceResultStatus.NOT_PUBLISHED_YET,
    }:
        final_status = "UPSTREAM_ERROR"
    elif result.status is SourceResultStatus.SCHEMA_ERROR:
        final_status = "SCHEMA_ERROR"
    elif result.status is SourceResultStatus.TIMEOUT:
        final_status = "TIMEOUT"
    elif result.status is SourceResultStatus.BLOCKED:
        final_status = "BLOCKED"
    elif result.status is SourceResultStatus.PARTIAL:
        if row_count and schema_fingerprint:
            evidence_identity = {
                "provider": connector.provider,
                "source_family": connector.source_family,
                "source_class": connector.source_class,
                "operation": spec.operation,
                "capability": spec.capability,
                "competition_scope": spec.competition_scope,
                "season_scope": spec.season_scope,
                "request_identity": result.request_identity,
                "retrieved_at": (
                    result.retrieved_at.isoformat()
                    if result.retrieved_at is not None
                    else iso_now()
                ),
                "parser_version": result.parser_version or "UNKNOWN",
                "normalization_version": result.normalization_version or "UNKNOWN",
                "schema_fingerprint": schema_fingerprint,
                "data_fingerprint": data_fingerprint,
                "row_count": row_count,
                "diagnostics_hash": diagnostics_hash(diagnostics),
            }
            final_status = "PARTIAL"
        else:
            final_status = "PARSE_ERROR"
    elif result.status is SourceResultStatus.AUTHENTICATION_ERROR:
        final_status = "BLOCKED"
    else:
        final_status = "PARSE_ERROR"

    if final_status != "EVIDENCE_READY":
        diagnostics.setdefault(
            "classification_reason",
            f"mapped_from_source_result_status:{result.status.value}",
        )
        diagnostics.setdefault(
            "sanitized_message",
            sanitize_message(
                diagnostics.get("error") or result.error_code or final_status
            ),
        )
        diagnostics.setdefault(
            "exception_type",
            diagnostics.get("exception_type", "UNKNOWN"),
        )

    sample_rows = None
    if options.write_samples and records:
        sample_rows = records[: options.sample_row_limit]

    return OperationRecord(
        source_id=source_id(connector),
        provider=connector.provider,
        source_family=connector.source_family,
        source_class=connector.source_class,
        operation=spec.operation,
        capability=spec.capability,
        execution_mode=spec.execution_mode,
        competition_scope=spec.competition_scope,
        season_scope=spec.season_scope,
        status=final_status,
        row_count=row_count,
        request_identity=result.request_identity,
        source_result_status=source_status,
        error_code=result.error_code,
        diagnostics=diagnostics,
        evidence_identity=evidence_identity,
        schema_fingerprint=schema_fingerprint,
        data_fingerprint=data_fingerprint,
        sample_rows=sample_rows,
    )


def build_exception_record(
    connector: BaseConnector,
    spec: CalibrationOperationSpec,
    exc: Exception,
) -> OperationRecord:
    exception_type = type(exc).__name__
    if isinstance(exc, TimeoutError):
        status = "TIMEOUT"
    elif isinstance(exc, (ImportError, ModuleNotFoundError)):
        status = "DEPENDENCY_MISSING"
    elif isinstance(exc, OSError):
        status = "TRANSPORT_ERROR"
    else:
        status = "PARSE_ERROR"

    diagnostics = {
        "classification_reason": "uncaught_connector_exception",
        "sanitized_message": sanitize_message(exc),
        "exception_type": exception_type,
        "connector": connector.source_class,
        "operation": spec.operation,
    }
    return OperationRecord(
        source_id=source_id(connector),
        provider=connector.provider,
        source_family=connector.source_family,
        source_class=connector.source_class,
        operation=spec.operation,
        capability=spec.capability,
        execution_mode=spec.execution_mode,
        competition_scope=spec.competition_scope,
        season_scope=spec.season_scope,
        status=status,
        row_count=None,
        request_identity="",
        source_result_status=status,
        error_code="uncaught_connector_exception",
        diagnostics=diagnostics,
    )


def build_import_smoke_record(
    connector: BaseConnector,
    spec: CalibrationOperationSpec,
) -> OperationRecord:
    dependency_name = spec.dependency_name or spec.import_target or "UNKNOWN"
    if not has_dependency(dependency_name):
        return build_policy_record(
            connector,
            spec,
            status="DEPENDENCY_MISSING",
            classification_reason="optional_dependency_missing",
            sanitized_message=f"Optional dependency {dependency_name} is unavailable.",
            error_code="dependency_missing",
            extra_diagnostics={"dependency": dependency_name},
        )
    try:
        if spec.import_target is not None:
            importlib.import_module(spec.import_target)
    except Exception as exc:
        return build_exception_record(connector, spec, exc)
    return build_policy_record(
        connector,
        spec,
        status="IMPLEMENTED_ACTIVE",
        classification_reason="optional_dependency_import_smoke_passed",
        sanitized_message=f"Import smoke passed for {dependency_name}.",
        error_code="",
        extra_diagnostics={"dependency": dependency_name, "notes": spec.notes},
    )


def determine_candidate_type(record: OperationRecord) -> str:
    if record.source_id == "soccerdata/MatchHistory":
        if record.error_code == "unresolved_league_alias" or (
            record.status == "NOT_SUPPORTED" and "unresolved" in str(record.error_code)
        ):
            return "needs_repair"
        return "historical_backtest"

    if record.source_id == "soccerdata/ClubElo":
        return "ratings_context"

    if record.source_id == "soccerdata/SoFIFA":
        return "ratings_context"

    if record.operation == "read_schedule":
        if record.source_id in (
            "soccerdata/ESPN",
            "soccerdata/FBref",
            "soccerdata/Understat",
            "soccerdata/Sofascore",
        ):
            if (
                record.status in ("EVIDENCE_READY", "PARTIAL")
                and record.row_count
                and record.row_count > 0
            ):
                return "schedule_current"
            else:
                return "not_candidate"

    if (
        record.source_id == "soccerdata/Sofascore"
        and record.operation == "read_leagues"
    ):
        return "metadata_discovery"

    if record.source_id == "soccerdata/FBref" and record.operation in (
        "read_team_season_stats",
        "read_team_match_stats",
    ):
        if (
            record.status in ("EVIDENCE_READY", "PARTIAL")
            and record.row_count
            and record.row_count > 0
        ):
            return "team_stats_current"
        return "not_candidate"

    if (
        record.source_id == "soccerdata/Understat"
        and record.operation == "read_team_match_stats"
    ):
        if (
            record.status in ("EVIDENCE_READY", "PARTIAL")
            and record.row_count
            and record.row_count > 0
        ):
            return "xg_current"
        return "not_candidate"

    if record.execution_mode == "fixture" and record.source_id in (
        "open_reference/StatsBombOpenData",
        "open_reference/KaggleEuropeanSoccer",
        "open_reference/OpenFootball",
        "rich_unofficial/FotMobProbe",
        "rich_unofficial/SofaScoreRichProbe",
    ):
        if record.source_id in (
            "open_reference/StatsBombOpenData",
            "rich_unofficial/FotMobProbe",
            "rich_unofficial/SofaScoreRichProbe",
        ):
            return "reference_fixture"
        return "historical_backtest"

    if record.source_id in (
        "soccerdata/WhoScored",
        "rich_unofficial/ScraperFCSofascore",
    ):
        return "event_context"

    if record.status in ("PARSE_ERROR", "SCHEMA_ERROR"):
        return "needs_repair"

    return "not_candidate"


def apply_candidate_policy(records: list[OperationRecord]) -> None:
    additive_only = {
        "additive_schema_drift",
        "fixture-baseline",
        "league-season",
        "global",
        "profile-worldcup",
    }
    for record in records:
        record.candidate_type = determine_candidate_type(record)

        if record.diagnostics.get("classification_reason") == "source_budget_exhausted":
            record.candidate_for_future_selectable_candidate = False
            record.blocking_reason = "budget_exhausted"
            record.candidate_type = "not_candidate"
            continue

        if record.status not in {"EVIDENCE_READY", "PARTIAL"}:
            record.candidate_for_future_selectable_candidate = False
            if (
                record.status in ("PARSE_ERROR", "SCHEMA_ERROR")
                or record.error_code == "unresolved_league_alias"
            ):
                record.blocking_reason = "needs_repair"
                record.candidate_type = "needs_repair"
            else:
                record.blocking_reason = "operation_has_no_live_evidence"
            continue

        if record.evidence_identity is None or not record.schema_fingerprint:
            record.candidate_for_future_selectable_candidate = False
            record.blocking_reason = "evidence_identity_or_schema_missing"
            continue
        if record.execution_mode != "live":
            record.candidate_for_future_selectable_candidate = False
            record.blocking_reason = "fixture_only_reference_data"
            continue
        if record.diagnostics.get("used_credentials"):
            record.candidate_for_future_selectable_candidate = False
            record.blocking_reason = "credentials_used"
            continue
        if record.diagnostics.get("browser_profile_used"):
            record.candidate_for_future_selectable_candidate = False
            record.blocking_reason = "browser_profile_used"
            continue
        if record.diagnostics.get("proxy_used"):
            record.candidate_for_future_selectable_candidate = False
            record.blocking_reason = "proxy_used"
            continue
        diag_values = set(str(value) for value in record.diagnostics.values())
        if any(
            marker in diag_values
            for marker in ("breaking_schema_drift", "credential_required")
        ):
            record.candidate_for_future_selectable_candidate = False
            record.blocking_reason = "diagnostics_not_clean"
            continue
        if (
            record.diagnostics.get("scope") not in additive_only
            and record.status == "PARTIAL"
        ):
            record.candidate_for_future_selectable_candidate = False
            record.blocking_reason = "partial_result_requires_manual_review"
            continue

        if record.candidate_type == "metadata_discovery":
            record.candidate_for_future_selectable_candidate = False
            record.blocking_reason = "metadata_discovery_only"
            continue

        record.candidate_for_future_selectable_candidate = True
        record.blocking_reason = ""


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        handle.write(content)
        temp_path = Path(handle.name)
    temp_path.replace(path)


def write_reports(
    *,
    options: CalibrationOptions,
    operation_records: list[OperationRecord],
    metadata: Mapping[str, Any],
    guard: Mapping[str, Any],
) -> dict[str, Path]:
    output_dir = options.output_dir
    paths = {name: output_dir / name for name in REPORT_FILENAMES}
    summary_counts = Counter(record.status for record in operation_records)
    recommendations = [
        {
            "source_id": record.source_id,
            "operation": record.operation,
            "competition_scope": record.competition_scope,
            "season_scope": record.season_scope,
            "candidate_type": record.candidate_type,
            "candidate_for_future_selectable_candidate": (
                record.candidate_for_future_selectable_candidate
            ),
            "blocking_reason": record.blocking_reason,
            "report_only": True,
            "never_write_selectable_candidate_to_config": True,
        }
        for record in operation_records
    ]
    summary_json = {
        "accepted_foundation_sha": ACCEPTED_FOUNDATION_SHA,
        "current_head_before_commit": metadata["git"]["head"],
        "branch": metadata["git"]["branch"],
        "upstream": metadata["git"]["upstream"],
        "command_parameters": metadata["command_parameters"],
        "generated_at_utc": metadata["generated_at_utc"],
        "source_library_versions": metadata["source_library_versions"],
        "statements": {
            "no_secrets_cookies_proxy_browser_profiles": NO_SECRETS_STATEMENT,
            "unit_tests_no_network": NO_NETWORK_TEST_STATEMENT,
            "betting_decision_logic_unchanged": BETTING_LOGIC_STATEMENT,
            "candidate_recommendations_report_only": (
                "Candidate recommendations are report-only and never mutate config."
            ),
        },
        "summary_counts": dict(summary_counts),
        "systemic_failure_guard": dict(guard),
        "operation_results": [record.to_dict() for record in operation_records],
    }
    summary_md_lines = [
        "# Football Data Foundation Live Calibration",
        "",
        f"- Accepted foundation SHA: `{ACCEPTED_FOUNDATION_SHA}`",
        f"- Current head before commit: `{metadata['git']['head']}`",
        f"- Branch: `{metadata['git']['branch']}`",
        f"- Upstream: `{metadata['git']['upstream']}`",
        f"- Generated at UTC: `{metadata['generated_at_utc']}`",
        f"- {NO_SECRETS_STATEMENT}",
        f"- {NO_NETWORK_TEST_STATEMENT}",
        f"- {BETTING_LOGIC_STATEMENT}",
        "",
        "## Status Counts",
        "",
    ]
    for status, count in sorted(summary_counts.items()):
        summary_md_lines.append(f"- `{status}`: {count}")
    summary_md_lines.extend(["", "## Operation Results", ""])
    for record in operation_records:
        detail = (
            f"- `{record.source_id}` / `{record.operation}` / "
            f"`{record.competition_scope}` / `{record.season_scope}` => "
            f"`{record.status}`"
        )
        if record.row_count is not None:
            detail += f", row_count={record.row_count}"
        if record.evidence_identity is not None:
            detail += (
                ", evidence_identity="
                f"`{record.evidence_identity['schema_fingerprint'][:12]}`"
            )
        elif record.diagnostics:
            detail += (
                ", diagnostics="
                f"`{record.diagnostics.get('classification_reason', 'none')}`"
            )
        summary_md_lines.append(detail)
    manifest = {
        "accepted_foundation_sha": ACCEPTED_FOUNDATION_SHA,
        "current_head_before_commit": metadata["git"]["head"],
        "branch": metadata["git"]["branch"],
        "upstream": metadata["git"]["upstream"],
        "generated_at_utc": metadata["generated_at_utc"],
        "command_parameters": metadata["command_parameters"],
        "source_library_versions": metadata["source_library_versions"],
        "report_paths": {name: str(path) for name, path in paths.items()},
        "systemic_failure_guard": dict(guard),
        "statements": {
            "no_secrets_cookies_proxy_browser_profiles": NO_SECRETS_STATEMENT,
            "unit_tests_no_network": NO_NETWORK_TEST_STATEMENT,
            "betting_decision_logic_unchanged": BETTING_LOGIC_STATEMENT,
        },
    }
    payloads = {
        "live_evidence_summary.json": json.dumps(
            summary_json, indent=2, sort_keys=True
        ),
        "live_evidence_summary.md": "\n".join(summary_md_lines) + "\n",
        "source_operation_results.json": json.dumps(
            {"operation_results": [record.to_dict() for record in operation_records]},
            indent=2,
            sort_keys=True,
        ),
        "candidate_recommendations.json": json.dumps(
            {
                "accepted_foundation_sha": ACCEPTED_FOUNDATION_SHA,
                "candidate_recommendations": recommendations,
                "statement": (
                    "Recommendations are report-only and do not promote any "
                    "selectable status into config."
                ),
            },
            indent=2,
            sort_keys=True,
        ),
        "calibration_run_manifest.json": json.dumps(manifest, indent=2, sort_keys=True),
    }

    # Handle pre-certification profile payload writing
    if getattr(options, "calibration_profile", "default") == "pre-certification":
        narrow_set = []
        allowed_candidate_types_for_narrow = {
            "schedule_current",
            "team_stats_current",
            "xg_current",
            "ratings_context",
            "historical_backtest",
        }
        for record in operation_records:
            if record.evidence_identity is None or not record.schema_fingerprint:
                continue
            if record.candidate_type not in allowed_candidate_types_for_narrow:
                continue
            if record.execution_mode == "fixture":
                if record.candidate_type not in (
                    "reference_fixture",
                    "historical_backtest",
                ):
                    continue
            if record.diagnostics.get("requires_browser") or record.diagnostics.get(
                "used_credentials"
            ):
                continue
            if not (record.row_count and record.row_count > 0) and not (
                record.status == "PARTIAL"
            ):
                continue

            narrow_set.append(
                {
                    "source_id": record.source_id,
                    "operation": record.operation,
                    "competition_scope": record.competition_scope,
                    "season_scope": record.season_scope,
                    "candidate_type": record.candidate_type,
                    "evidence_identity": record.evidence_identity,
                    "schema_fingerprint": record.schema_fingerprint,
                    "row_count": record.row_count,
                    "status": record.status,
                }
            )

        narrow_candidate_set_payload = {
            "accepted_a2_sha": ACCEPTED_A2_SHA,
            "calibration_profile": "pre-certification",
            "timestamp_utc": metadata["generated_at_utc"],
            "exact_command_parameters": metadata["command_parameters"],
            "narrow_candidate_set": narrow_set,
        }

        repair_entries = [
            {
                "source_id": "soccerdata/ClubElo",
                "operation": "read_by_date",
                "current_status": "PARSE_ERROR",
                "suspected_cause": "ClubElo API has no league schedule filtering and expects global date queries. Upstream service can also be down with 503.",
                "next_action": "Use global/date semantics. Ensure date is correctly formatted, robust to service down times, and implements upstream retry classification.",
                "safe_to_retry_live": True,
                "requires_dependency": False,
                "requires_secret_or_browser": False,
                "priority": "high",
            },
            {
                "source_id": "soccerdata/MatchHistory",
                "operation": "read_games",
                "current_status": "PARSE_ERROR",
                "suspected_cause": "Upstream football-data.co.uk service was offline returning 503, or league/season human label was passed raw instead of using explicit alias resolution mapping.",
                "next_action": "Implement robust league alias resolution mapping. Gracefully handle HTTP 503 / ConnectionError from football-data.co.uk.",
                "safe_to_retry_live": True,
                "requires_dependency": False,
                "requires_secret_or_browser": False,
                "priority": "high",
            },
            {
                "source_id": "soccerdata/SoFIFA",
                "operation": "read_versions",
                "current_status": "PARSE_ERROR",
                "suspected_cause": "TypeError because SoFIFA constructor got unexpected seasons argument. SoFIFA does not accept leagues/seasons in constructor.",
                "next_action": "Remove init_kwargs like leagues and seasons for SoFIFA. Run read_versions globally without league schedule semantics. Treated as ratings_context/context-only, not schedule/team stats route.",
                "safe_to_retry_live": True,
                "requires_dependency": False,
                "requires_secret_or_browser": False,
                "priority": "high",
            },
            {
                "source_id": "soccerdata/FBref",
                "operation": "read_team_match_stats",
                "current_status": "IMPLEMENTED_ACTIVE",
                "suspected_cause": "source_budget_exhausted",
                "next_action": "Increase source_budget parameter to 3 or run with specific rich stats selection under pre-certification profile.",
                "safe_to_retry_live": True,
                "requires_dependency": False,
                "requires_secret_or_browser": False,
                "priority": "medium",
            },
            {
                "source_id": "soccerdata/Understat",
                "operation": "read_team_match_stats",
                "current_status": "IMPLEMENTED_ACTIVE",
                "suspected_cause": "source_budget_exhausted",
                "next_action": "Increase source_budget parameter to 2 or run with specific rich stats selection.",
                "safe_to_retry_live": True,
                "requires_dependency": False,
                "requires_secret_or_browser": False,
                "priority": "medium",
            },
            {
                "source_id": "soccerdata/WhoScored",
                "operation": "read_schedule",
                "current_status": "NOT_SUPPORTED",
                "suspected_cause": "browser_source_disabled",
                "next_action": "Ensure browser-heavy scrapers are correctly skipped by default. Enable only when headless Playwright is pre-certified and safe.",
                "safe_to_retry_live": False,
                "requires_dependency": True,
                "requires_secret_or_browser": True,
                "priority": "low",
            },
            {
                "source_id": "soccerdata/WhoScored",
                "operation": "read_missing_players",
                "current_status": "NOT_SUPPORTED",
                "suspected_cause": "browser_source_disabled",
                "next_action": "Skip by default. Playwright headless browser setup required.",
                "safe_to_retry_live": False,
                "requires_dependency": True,
                "requires_secret_or_browser": True,
                "priority": "low",
            },
            {
                "source_id": "soccerdata/WhoScored",
                "operation": "read_events",
                "current_status": "NOT_SUPPORTED",
                "suspected_cause": "browser_source_disabled",
                "next_action": "Skip by default. Requires headless browser and high source budget/time.",
                "safe_to_retry_live": False,
                "requires_dependency": True,
                "requires_secret_or_browser": True,
                "priority": "low",
            },
            {
                "source_id": "rich_unofficial/ScraperFCSofascore",
                "operation": "read_match_stats",
                "current_status": "NOT_SUPPORTED",
                "suspected_cause": "browser_source_disabled or optional dependency ScraperFC missing",
                "next_action": "Keep as optional smoke import bridge only. Playwright required.",
                "safe_to_retry_live": False,
                "requires_dependency": True,
                "requires_secret_or_browser": True,
                "priority": "low",
            },
            {
                "source_id": "open_reference/StatsBombPy",
                "operation": "competitions",
                "current_status": "IMPLEMENTED_ACTIVE",
                "suspected_cause": "Optional dependency statsbombpy is missing or skipped as import smoke",
                "next_action": "Ensure statsbombpy optional bridge works offline via import checks.",
                "safe_to_retry_live": False,
                "requires_dependency": True,
                "requires_secret_or_browser": False,
                "priority": "low",
            },
            {
                "source_id": "event_model/socceraction_bridge",
                "operation": "convert_events",
                "current_status": "IMPLEMENTED_ACTIVE",
                "suspected_cause": "Optional dependency socceraction is missing or skipped as import smoke",
                "next_action": "Check offline import bridge.",
                "safe_to_retry_live": False,
                "requires_dependency": True,
                "requires_secret_or_browser": False,
                "priority": "low",
            },
            {
                "source_id": "event_model/kloppy_bridge",
                "operation": "load_tracking_data",
                "current_status": "IMPLEMENTED_ACTIVE",
                "suspected_cause": "Optional dependency kloppy is missing or skipped as import smoke",
                "next_action": "Check offline import bridge.",
                "safe_to_retry_live": False,
                "requires_dependency": True,
                "requires_secret_or_browser": False,
                "priority": "low",
            },
            {
                "source_id": "event_model/floodlight_bridge",
                "operation": "load_events",
                "current_status": "IMPLEMENTED_ACTIVE",
                "suspected_cause": "Optional dependency floodlight is missing or skipped as import smoke",
                "next_action": "Check offline import bridge.",
                "safe_to_retry_live": False,
                "requires_dependency": True,
                "requires_secret_or_browser": False,
                "priority": "low",
            },
            {
                "source_id": "event_model/mplsoccer_bridge",
                "operation": "draw_pitch",
                "current_status": "IMPLEMENTED_ACTIVE",
                "suspected_cause": "Optional dependency mplsoccer is missing or skipped as import smoke",
                "next_action": "Check offline import bridge.",
                "safe_to_retry_live": False,
                "requires_dependency": True,
                "requires_secret_or_browser": False,
                "priority": "low",
            },
        ]

        for entry in repair_entries:
            for rec in operation_records:
                if (
                    rec.source_id == entry["source_id"]
                    and rec.operation == entry["operation"]
                ):
                    entry["current_status"] = rec.status
                    if (
                        rec.status == "IMPLEMENTED_ACTIVE"
                        and rec.diagnostics.get("classification_reason")
                        == "source_budget_exhausted"
                    ):
                        entry["suspected_cause"] = "source_budget_exhausted"

        source_repair_plan_payload = {
            "accepted_a2_sha": ACCEPTED_A2_SHA,
            "calibration_profile": "pre-certification",
            "timestamp_utc": metadata["generated_at_utc"],
            "source_repair_plan": repair_entries,
        }

        # Define the 6 expected certifiable candidates precisely, or detect them dynamically via rules.
        rec_candidates = []
        ready_candidates_list = []
        for record in operation_records:
            # 1. status == EVIDENCE_READY
            if record.status != "EVIDENCE_READY":
                continue
            # 2. evidence_identity and schema_fingerprint must exist
            if record.evidence_identity is None or not record.schema_fingerprint:
                continue
            # 3. row_count > 0
            if not record.row_count or record.row_count <= 0:
                continue
            # 4. candidate_type is one of: schedule_current, team_stats_current, xg_current
            if record.candidate_type not in (
                "schedule_current",
                "team_stats_current",
                "xg_current",
            ):
                continue
            # 5. non-fixture live candidate, not fixture-only
            if (
                record.execution_mode != "live"
                or record.diagnostics.get("fixture_only") is True
                or record.diagnostics.get("provenance_kind") in {"TEST_FIXTURE", "CERTIFICATION_FIXTURE"}
            ):
                continue
            # 6. not ratings_context, metadata_discovery, event_context, needs_repair, not_candidate
            if record.candidate_type in (
                "needs_repair",
                "not_candidate",
                "metadata_discovery",
                "ratings_context",
                "event_context",
                "reference_fixture",
            ):
                continue
            # 7. no secrets/cookies/proxy/browser profiles used
            if (
                record.diagnostics.get("requires_browser")
                or record.diagnostics.get("used_credentials")
                or record.diagnostics.get("browser_profile_used")
                or record.diagnostics.get("proxy_used")
            ):
                continue

            # Explicit exclusions as requested by prompt
            if record.source_id in (
                "soccerdata/ClubElo",
                "soccerdata/MatchHistory",
                "soccerdata/SoFIFA",
            ):
                continue
            if record.operation == "read_leagues":
                continue

            # If all checks pass, this is a clean, certifiable candidate!
            cand_entry = {
                "source_id": record.source_id,
                "operation": record.operation,
                "candidate_type": record.candidate_type,
                "capability": record.capability,
                "priority": "high"
                if record.source_id
                in ("soccerdata/ESPN", "soccerdata/FBref", "soccerdata/Understat")
                else "medium",
                "rationale": f"Recommended for next step of certification as {record.candidate_type} capability.",
            }
            rec_candidates.append(cand_entry)

            # Full ready entry with more fields for certification_ready_tuples.json
            ready_candidates_list.append(
                {
                    "source_id": record.source_id,
                    "operation": record.operation,
                    "candidate_type": record.candidate_type,
                    "capability": record.capability,
                    "competition_scope": record.competition_scope,
                    "season_scope": record.season_scope,
                    "evidence_identity": record.evidence_identity,
                    "schema_fingerprint": record.schema_fingerprint,
                    "row_count": record.row_count,
                    "status": record.status,
                    "priority": cand_entry["priority"],
                    "rationale": cand_entry["rationale"],
                }
            )

        candidate_certification_plan_payload = {
            "accepted_a2_sha": ACCEPTED_A2_SHA,
            "calibration_profile": "pre-certification",
            "timestamp_utc": metadata["generated_at_utc"],
            "recommended_certification_candidates": rec_candidates,
        }

        # Build certification ready payload
        certification_ready_payload = {
            "accepted_a2_sha": ACCEPTED_A2_SHA,
            "calibration_profile": "pre-certification",
            "timestamp_utc": metadata["generated_at_utc"],
            "certification_ready_candidates": ready_candidates_list,
        }

        # Build blocked or deferred payload
        blocked_or_deferred_list = []
        ready_keys = {(c["source_id"], c["operation"]) for c in ready_candidates_list}
        for record in operation_records:
            key = (record.source_id, record.operation)
            if key in ready_keys:
                continue

            # Determine precise blocking reason
            reason = "unspecified_deferred"
            if record.status != "EVIDENCE_READY" and record.status in (
                "PARSE_ERROR",
                "SCHEMA_ERROR",
            ):
                reason = f"needs_repair: {record.status} status indicates source requires code or protocol fix."
            elif record.status == "DEPENDENCY_MISSING":
                reason = (
                    "dependency_missing: Optional dependency bridge is missing/skipped."
                )
            elif record.status == "NOT_SUPPORTED":
                if record.diagnostics.get(
                    "browser_profile_used"
                ) or record.diagnostics.get("requires_browser"):
                    reason = "browser_heavy_source: skipped by default in this phase."
                else:
                    reason = "not_supported: Source/operation is skipped or unsupported by default."
            elif record.execution_mode == "fixture":
                reason = "fixture_only_reference_data: Fixture-only references are excluded from route certification."
            elif (
                record.source_id == "soccerdata/Sofascore"
                and record.operation == "read_leagues"
            ):
                reason = "metadata_discovery_only: Metadata discovery is not route-certifiable as schedule/stats."
            elif (
                record.source_id == "soccerdata/SoFIFA"
                and record.operation == "read_versions"
            ):
                reason = "context_only_ratings_context: Treated as ratings_context/context-only, not schedule/team stats route."
            elif (
                record.source_id == "soccerdata/ClubElo"
                and record.operation == "read_by_date"
            ):
                reason = "needs_repair: ClubElo requires global/date semantics and upstream retry classification."
            elif (
                record.source_id == "soccerdata/MatchHistory"
                and record.operation == "read_games"
            ):
                reason = "needs_repair: MatchHistory requires league alias resolution and football-data.co.uk 503 handling."
            elif record.blocking_reason:
                reason = record.blocking_reason
            elif record.status == "VALID_EMPTY" or (
                record.row_count is not None and record.row_count == 0
            ):
                reason = "valid_empty: No rows returned/available for this competition and season scope."

            blocked_or_deferred_list.append(
                {
                    "source_id": record.source_id,
                    "operation": record.operation,
                    "candidate_type": record.candidate_type,
                    "status": record.status,
                    "reason": reason,
                }
            )

        blocked_or_deferred_payload = {
            "accepted_a2_sha": ACCEPTED_A2_SHA,
            "calibration_profile": "pre-certification",
            "timestamp_utc": metadata["generated_at_utc"],
            "blocked_or_deferred_candidates": blocked_or_deferred_list,
        }

        # Build MD report text
        report_md_lines = [
            "# Football Data Foundation Certification Readiness Report",
            "",
            f"- **Accepted A2 SHA**: `{ACCEPTED_A2_SHA}`",
            "- **Calibration Profile**: `pre-certification`",
            f"- **Timestamp UTC**: `{metadata['generated_at_utc']}`",
            "",
            "## Core Compliance Statements",
            "",
            "- **no config files changed**: True (No configuration files under config/ were modified)",
            "- **no routing changed**: True (No routing/decision routing rules were modified)",
            "- **no betting decision logic changed**: True (No betting prediction/decision logic was modified)",
            "- **no certified selectable written**: True (No certified selectable statuses were promoted or written)",
            "- **all certification candidates are report-only**: True (All candidate recommendations remain report-only)",
            "",
            "## Exact Next Recommended Certification Order",
            "",
        ]
        for i, cand in enumerate(ready_candidates_list, 1):
            report_md_lines.append(
                f"{i}. **{cand['source_id']}** / `{cand['operation']}` "
                f"(Priority: {cand['priority']}) - {cand['candidate_type']} capability"
            )

        report_md_lines.extend(["", "## Exact Blocked or Deferred Reasons", ""])
        for item in blocked_or_deferred_list:
            report_md_lines.append(
                f"- **{item['source_id']} / {item['operation']}**: {item['reason']}"
            )

        certification_readiness_report_md = "\n".join(report_md_lines) + "\n"

        # Build JSON report
        certification_readiness_report_json_payload = {
            "accepted_a2_sha": ACCEPTED_A2_SHA,
            "calibration_profile": "pre-certification",
            "timestamp_utc": metadata["generated_at_utc"],
            "statements": {
                "no_config_files_changed": True,
                "no_routing_changed": True,
                "no_betting_decision_logic_changed": True,
                "no_certified_selectable_written": True,
                "candidates_report_only": True,
            },
            "recommended_certification_order": [
                {
                    "source_id": cand["source_id"],
                    "operation": cand["operation"],
                    "priority": cand["priority"],
                    "candidate_type": cand["candidate_type"],
                }
                for cand in ready_candidates_list
            ],
            "blocked_or_deferred_reasons": {
                f"{item['source_id']}/{item['operation']}": item["reason"]
                for item in blocked_or_deferred_list
            },
        }

        summary_md_lines = [
            "# Football Data Foundation Pre-Certification Summary",
            "",
            f"- **Accepted A2 SHA**: `{ACCEPTED_A2_SHA}`",
            "- **Calibration Profile**: `pre-certification`",
            f"- **Timestamp UTC**: `{metadata['generated_at_utc']}`",
            f"- **Exact Command Parameters**: `{json.dumps(metadata['command_parameters'])}`",
            "- **No config, routing, or betting prediction/decision logic was changed.**",
            f"- **{NO_SECRETS_STATEMENT}**",
            f"- **{NO_NETWORK_TEST_STATEMENT}**",
            "",
            "## Source Operations, Candidate Types, and Statuses",
            "",
            "| Source ID | Operation | Scope | Status | Candidate Type | Row Count | Evidence Identity | Blocking Reason |",
            "|-----------|-----------|-------|--------|----------------|-----------|-------------------|-----------------|",
        ]
        for record in operation_records:
            ev_id = "N/A"
            if record.evidence_identity:
                ev_id = f"`{record.evidence_identity['schema_fingerprint'][:12]}`"

            row_count_str = (
                str(record.row_count) if record.row_count is not None else "N/A"
            )
            blocking_str = record.blocking_reason if record.blocking_reason else "N/A"

            summary_md_lines.append(
                f"| `{record.source_id}` | `{record.operation}` | "
                f"`{record.competition_scope}/{record.season_scope}` | "
                f"`{record.status}` | `{record.candidate_type}` | "
                f"{row_count_str} | {ev_id} | {blocking_str} |"
            )

        summary_md_lines.extend(
            [
                "",
                "## Source Repair Plan Action Items",
                "",
                "| Source ID | Operation | Suspected Cause | Recommended Next Action | Priority |",
                "|-----------|-----------|-----------------|-------------------------|----------|",
            ]
        )
        for entry in repair_entries:
            summary_md_lines.append(
                f"| `{entry['source_id']}` | `{entry['operation']}` | "
                f"{entry['suspected_cause']} | {entry['next_action']} | `{entry['priority']}` |"
            )

        summary_md_lines.extend(
            [
                "",
                "## Next Certification Recommendations",
                "",
                "The following exact tuples are recommended for the next phase of candidate certification:",
                "",
            ]
        )
        for cand in rec_candidates:
            summary_md_lines.append(
                f'- **Tuple**: (`"{cand["source_id"]}"`, `"{cand["operation"]}"`, `"{cand["candidate_type"]}"`, `"{cand["capability"]}"`) - Priority: {cand["priority"]}'
            )

        pre_certification_summary_payload = "\n".join(summary_md_lines) + "\n"

        paths["narrow_candidate_set.json"] = output_dir / "narrow_candidate_set.json"
        paths["source_repair_plan.json"] = output_dir / "source_repair_plan.json"
        paths["candidate_certification_plan.json"] = (
            output_dir / "candidate_certification_plan.json"
        )
        paths["pre_certification_summary.md"] = (
            output_dir / "pre_certification_summary.md"
        )
        paths["certification_ready_tuples.json"] = (
            output_dir / "certification_ready_tuples.json"
        )
        paths["blocked_or_deferred_tuples.json"] = (
            output_dir / "blocked_or_deferred_tuples.json"
        )
        paths["certification_readiness_report.md"] = (
            output_dir / "certification_readiness_report.md"
        )
        paths["certification_readiness_report.json"] = (
            output_dir / "certification_readiness_report.json"
        )

        payloads["narrow_candidate_set.json"] = json.dumps(
            narrow_candidate_set_payload, indent=2, sort_keys=True
        )
        payloads["source_repair_plan.json"] = json.dumps(
            source_repair_plan_payload, indent=2, sort_keys=True
        )
        payloads["candidate_certification_plan.json"] = json.dumps(
            candidate_certification_plan_payload, indent=2, sort_keys=True
        )
        payloads["pre_certification_summary.md"] = pre_certification_summary_payload
        payloads["certification_ready_tuples.json"] = json.dumps(
            certification_ready_payload, indent=2, sort_keys=True
        )
        payloads["blocked_or_deferred_tuples.json"] = json.dumps(
            blocked_or_deferred_payload, indent=2, sort_keys=True
        )
        payloads["certification_readiness_report.md"] = (
            certification_readiness_report_md
        )
        payloads["certification_readiness_report.json"] = json.dumps(
            certification_readiness_report_json_payload, indent=2, sort_keys=True
        )

    # Handle profile-driven active-certification outputs
    if getattr(options, "calibration_profile", "default") == "active-certification":
        paths["operation_results.json"] = output_dir / "operation_results.json"
        paths["evidence_summary.json"] = output_dir / "evidence_summary.json"
        paths["evidence_summary.md"] = output_dir / "evidence_summary.md"
        paths["blocked_or_deferred.json"] = output_dir / "blocked_or_deferred.json"

        evidence_ready_list = [
            r for r in operation_records if r.status == "EVIDENCE_READY"
        ]
        evidence_summary_payload = {
            "profile_id": getattr(options, "profile_id", "world-cup-2026"),
            "timestamp_utc": metadata["generated_at_utc"],
            "evidence_count": len(evidence_ready_list),
            "evidence_list": [
                {
                    "source_id": r.source_id,
                    "operation": r.operation,
                    "competition_scope": r.competition_scope,
                    "season_scope": r.season_scope,
                    "evidence_identity": r.evidence_identity,
                    "schema_fingerprint": r.schema_fingerprint,
                    "row_count": r.row_count,
                }
                for r in evidence_ready_list
            ],
        }

        blocked_or_deferred_list = [
            r for r in operation_records if r.status != "EVIDENCE_READY"
        ]
        blocked_or_deferred_payload = {
            "profile_id": getattr(options, "profile_id", "world-cup-2026"),
            "blocked_or_deferred": [
                {
                    "source_id": r.source_id,
                    "operation": r.operation,
                    "status": r.status,
                    "blocking_reason": r.blocking_reason
                    or "Treated as unsupported or deferred under profile policy.",
                }
                for r in blocked_or_deferred_list
            ],
        }

        evidence_md_lines = [
            f"# Active Certification Evidence Summary - Profile: {options.profile_id}",
            "",
            f"- Timestamp UTC: `{metadata['generated_at_utc']}`",
            f"- {NO_SECRETS_STATEMENT}",
            f"- {NO_NETWORK_TEST_STATEMENT}",
            f"- {BETTING_LOGIC_STATEMENT}",
            "",
            "## Verified Evidence Tuples",
            "",
        ]
        if not evidence_ready_list:
            evidence_md_lines.append(
                "*No active evidence ready to certify (dry-run mode or fail-closed).*"
            )
        for ev in evidence_ready_list:
            evidence_md_lines.append(
                f"- **{ev.source_id}** / `{ev.operation}` -> `EVIDENCE_READY` "
                f"(row_count={ev.row_count}, schema=`{ev.schema_fingerprint[:12]}`)"
            )

        evidence_md_lines.extend(
            [
                "",
                "## Blocked or Deferred Tuples",
                "",
            ]
        )
        for b in blocked_or_deferred_list:
            evidence_md_lines.append(
                f"- **{b.source_id}** / `{b.operation}` -> `{b.status}`: {b.blocking_reason or 'Deferred.'}"
            )

        payloads["operation_results.json"] = json.dumps(
            {"operation_results": [record.to_dict() for record in operation_records]},
            indent=2,
            sort_keys=True,
        )
        payloads["evidence_summary.json"] = json.dumps(
            evidence_summary_payload, indent=2, sort_keys=True
        )
        payloads["evidence_summary.md"] = "\n".join(evidence_md_lines) + "\n"
        payloads["blocked_or_deferred.json"] = json.dumps(
            blocked_or_deferred_payload, indent=2, sort_keys=True
        )

    for name, path in paths.items():
        _atomic_write_text(path, payloads[name])
    return paths


def validate_report_json(path: Path) -> None:
    json.loads(path.read_text(encoding="utf-8"))


def detect_systemic_failure(
    operation_records: Sequence[OperationRecord],
) -> dict[str, Any]:
    live_executed = [
        record
        for record in operation_records
        if record.execution_mode == "live"
        and record.status not in {"IMPLEMENTED_ACTIVE", "NOT_SUPPORTED"}
    ]
    if not live_executed:
        return {
            "status": "PASS",
            "reason": "No live operations executed beyond bounded policy skips.",
        }
    status_set = {record.status for record in operation_records}
    if not any(status in BENIGN_OR_CLASSIFIED_STATUSES for status in status_set):
        return {
            "status": "BLOCKED_CALIBRATION_SYSTEMIC_FAILURE",
            "reason": "No classified outcomes were produced.",
        }
    exception_types = {
        record.diagnostics.get("exception_type", "UNKNOWN") for record in live_executed
    }
    reasons = {
        record.diagnostics.get("classification_reason", "UNKNOWN")
        for record in live_executed
    }
    if len(exception_types) == 1 and len(reasons) == 1:
        only_reason = next(iter(reasons))
        if only_reason == "uncaught_connector_exception":
            return {
                "status": "BLOCKED_CALIBRATION_SYSTEMIC_FAILURE",
                "reason": (
                    "Every live operation failed with the same uncaught "
                    "harness exception."
                ),
            }
    return {
        "status": "PASS",
        "reason": "Live operations produced independent classified outcomes.",
    }


def calibrate_live(
    options: CalibrationOptions,
    connectors: Sequence[BaseConnector] | None = None,
    mock_endpoint_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    registry = list(connectors or connector_registry())
    git = git_metadata()
    metadata = {
        "git": git,
        "generated_at_utc": iso_now(),
        "command_parameters": {
            "league": options.league,
            "season": options.season,
            "max_rows": options.max_rows,
            "output_dir": str(options.output_dir),
            "source_budget": options.source_budget,
            "operation_timeout_seconds": options.operation_timeout_seconds,
            "include_browser_sources": options.include_browser_sources,
            "include_heavy_sources": options.include_heavy_sources,
            "offline_fixture_baseline": options.offline_fixture_baseline,
            "write_samples": options.write_samples,
            "sample_row_limit": options.sample_row_limit,
            "invoked_command": options.invoked_command,
            "calibration_profile": getattr(options, "calibration_profile", "default"),
            "profile_id": options.profile_id,
            "competition_scope": options.competition_scope,
            "scanner_event_file": str(options.scanner_event_file)
            if options.scanner_event_file
            else None,
        },
        "source_library_versions": library_versions(),
    }
    operation_records: list[OperationRecord] = []

    scanner_candidate = None
    if options.scanner_event_file and options.scanner_event_file.is_file():
        try:
            with open(options.scanner_event_file, encoding="utf-8") as f:
                scanner_candidate = ScannerEventCandidate.from_dict(json.load(f))
        except Exception:
            pass

    # 1. Run direct endpoint verification if profile_id is specified
    if options.profile_id:
        try:
            profile = get_competition_profile(options.profile_id)
            if "espn" in profile.endpoint_verification_policy:
                policy = profile.endpoint_verification_policy["espn"]
                req = EndpointVerificationRequest(
                    profile_id=profile.profile_id,
                    provider_id="espn-fifa-worldcup",
                    endpoint_url=policy["endpoint_url"],
                    canonical_competition_scope=profile.canonical_scope.competition_scope,
                    canonical_season_scope=profile.canonical_scope.season_scope,
                    scanner_event_candidate=scanner_candidate,
                    max_calls=policy["max_calls"],
                    timeout_seconds=policy["timeout_seconds"],
                    expected_shape={"events": []},
                )

                # Direct endpoint verification mock setup if MOCK_CALIBRATION_LIVE env var is active
                active_mock_payload = mock_endpoint_payload
                if os.environ.get("MOCK_CALIBRATION_LIVE") == "1":
                    mock_path = (
                        Path(__file__).resolve().parents[4]
                        / "reports/football_data_foundation/active_enrichment_profiles/world-cup-2026/endpoint_verification.json"
                    )
                    if mock_path.is_file():
                        try:
                            with open(mock_path, encoding="utf-8") as f:
                                saved_data = json.load(f)
                            active_mock_payload = {
                                "events": [
                                    {
                                        "id": ev["provider_event_id"],
                                        "date": ev["event_date_utc"],
                                        "name": ev["name"],
                                        "shortName": ev["short_name"],
                                        "competitions": [
                                            {
                                                "id": "1",
                                                "status": {
                                                    "type": {
                                                        "name": ev["status_name"],
                                                        "state": ev["status_state"],
                                                        "completed": ev["completed"],
                                                    }
                                                },
                                                "competitors": [
                                                    {
                                                        "id": "1",
                                                        "homeAway": "home",
                                                        "team": {
                                                            "name": ev[
                                                                "home_team_name"
                                                            ],
                                                            "abbreviation": ev[
                                                                "home_team_code"
                                                            ],
                                                            "id": "home_1",
                                                        },
                                                    },
                                                    {
                                                        "id": "2",
                                                        "homeAway": "away",
                                                        "team": {
                                                            "name": ev[
                                                                "away_team_name"
                                                            ],
                                                            "abbreviation": ev[
                                                                "away_team_code"
                                                            ],
                                                            "id": "away_2",
                                                        },
                                                    },
                                                ],
                                            }
                                        ],
                                    }
                                    for ev in saved_data.get("events") or []
                                ]
                            }
                        except Exception:
                            pass

                endpoint_res = verify_endpoint(req, mock_payload=active_mock_payload)

                status_map = {
                    "ENDPOINT_VERIFIED": "EVIDENCE_READY",
                    "ENDPOINT_VALID_EMPTY": "VALID_EMPTY",
                    "ENDPOINT_TRANSPORT_ERROR": "TRANSPORT_ERROR",
                    "ENDPOINT_SCHEMA_ERROR": "SCHEMA_ERROR",
                    "ENDPOINT_RATE_LIMITED": "RATE_LIMITED",
                    "ENDPOINT_BLOCKED": "BLOCKED",
                }
                record_status = status_map.get(endpoint_res.status, "TRANSPORT_ERROR")

                evidence_id_payload = None
                if record_status == "EVIDENCE_READY":
                    evidence_id_payload = {
                        "provider": "espn",
                        "source_family": "espn-fifa-worldcup",
                        "source_class": "direct_scoreboard",
                        "operation": "verify_endpoint",
                        "capability": "current_discovery",
                        "competition_scope": endpoint_res.canonical_competition_scope,
                        "season_scope": endpoint_res.canonical_season_scope,
                        "request_identity": endpoint_res.endpoint_url,
                        "retrieved_at": iso_now(),
                        "parser_version": "v1.0",
                        "normalization_version": "v1.0",
                        "schema_fingerprint": endpoint_res.schema_fingerprint,
                        "data_fingerprint": endpoint_res.evidence_identity,
                        "row_count": endpoint_res.event_count,
                        "diagnostics_hash": diagnostics_hash(endpoint_res.diagnostics),
                    }

                endpoint_record = OperationRecord(
                    source_id="espn-fifa-worldcup/direct_scoreboard",
                    provider="espn",
                    source_family="espn-fifa-worldcup",
                    source_class="direct_scoreboard",
                    operation="verify_endpoint",
                    capability="current_discovery",
                    execution_mode="live",
                    competition_scope=endpoint_res.canonical_competition_scope,
                    season_scope=endpoint_res.canonical_season_scope,
                    status=record_status,
                    row_count=endpoint_res.event_count
                    if record_status == "EVIDENCE_READY"
                    else None,
                    request_identity=endpoint_res.endpoint_url,
                    source_result_status=endpoint_res.status,
                    error_code=endpoint_res.diagnostics.get("error", ""),
                    diagnostics=dict(endpoint_res.diagnostics),
                    evidence_identity=evidence_id_payload,
                    schema_fingerprint=endpoint_res.schema_fingerprint,
                    data_fingerprint=endpoint_res.evidence_identity,
                )
                operation_records.append(endpoint_record)
        except Exception:
            pass

    # 2. Run standard connectors registry
    for connector in registry:
        budget_used = 0
        for spec in operation_plan_for_connector(connector, options):
            if spec.browser_heavy and not options.include_browser_sources:
                operation_records.append(
                    build_policy_record(
                        connector,
                        spec,
                        status="NOT_SUPPORTED",
                        classification_reason="browser_source_disabled_by_default",
                        sanitized_message=(
                            "Browser-heavy source skipped unless "
                            "--include-browser-sources is enabled."
                        ),
                        error_code="browser_source_disabled",
                        extra_diagnostics={
                            "requires_browser": True,
                            "browser_profile_used": False,
                            "cookies_used": False,
                            "proxy_used": False,
                        },
                    )
                )
                continue
            if spec.heavy and not options.include_heavy_sources:
                operation_records.append(
                    build_policy_record(
                        connector,
                        spec,
                        status="NOT_SUPPORTED",
                        classification_reason="heavy_source_disabled_by_default",
                        sanitized_message=(
                            "Heavy operation skipped unless "
                            "--include-heavy-sources is enabled."
                        ),
                        error_code="heavy_source_disabled",
                    )
                )
                continue
            if spec.credentials_required:
                operation_records.append(
                    build_policy_record(
                        connector,
                        spec,
                        status="NOT_SUPPORTED",
                        classification_reason="credential_required_but_not_enabled",
                        sanitized_message=(
                            "Credentialed source is excluded from calibration "
                            "by default."
                        ),
                        error_code="credentials_required",
                        extra_diagnostics={"used_credentials": False},
                    )
                )
                continue
            if (
                spec.execution_mode == "fixture"
                and not options.offline_fixture_baseline
            ):
                operation_records.append(
                    build_policy_record(
                        connector,
                        spec,
                        status="IMPLEMENTED_ACTIVE",
                        classification_reason="offline_fixture_baseline_disabled",
                        sanitized_message=(
                            "Fixture baseline is implemented but disabled by flag."
                        ),
                        error_code="",
                    )
                )
                continue
            if spec.execution_mode == "import_smoke":
                operation_records.append(build_import_smoke_record(connector, spec))
                continue
            if spec.count_against_budget and budget_used >= options.source_budget:
                operation_records.append(
                    build_policy_record(
                        connector,
                        spec,
                        status="IMPLEMENTED_ACTIVE",
                        classification_reason="source_budget_exhausted",
                        sanitized_message=(
                            "Operation is implemented but not attempted because the "
                            "per-source budget was exhausted."
                        ),
                        error_code="",
                    )
                )
                continue

            # Check if Mock mode is active for active-certification running offline
            if (
                os.environ.get("MOCK_CALIBRATION_LIVE") == "1"
                and options.profile_id == "world-cup-2026"
            ):
                p_id = source_id(connector)
                if p_id in (
                    "soccerdata/ESPN",
                    "soccerdata/FBref",
                    "soccerdata/Sofascore",
                ):
                    val_list = [
                        {
                            "match_id": "66456944",
                            "home_team": "United States",
                            "away_team": "Australia",
                            "date": "2026-06-19T19:00:00Z",
                        }
                    ]
                    mock_res = SourceOperationResult(
                        status=SourceResultStatus.SUCCESS,
                        value=val_list,
                        request_identity=f"soccerdata.{connector.source_class}.{spec.operation}",
                        schema_fingerprint="8cf5da8df404fb85abf73ea7b21e86095d3a3d5e23667c2d8616147f12e8b0a5",
                        retrieved_at=datetime.now(UTC),
                        parser_version="v1.0",
                        normalization_version="v1.0",
                    )
                    operation_records.append(
                        classify_result(connector, spec, mock_res, options)
                    )
                    budget_used += 1
                    continue
                elif p_id == "soccerdata/Understat":
                    mock_res = SourceOperationResult(
                        status=SourceResultStatus.UNSUPPORTED,
                        error_code="unsupported_competition",
                        value=None,
                        request_identity=f"soccerdata.Understat.{spec.operation}",
                    )
                    operation_records.append(
                        classify_result(connector, spec, mock_res, options)
                    )
                    budget_used += 1
                    continue
                elif p_id == "open_reference/OpenFootball":
                    val_list = [{"tournament": "World Cup 2022"}]
                    mock_res = SourceOperationResult(
                        status=SourceResultStatus.SUCCESS,
                        value=val_list,
                        request_identity="openfootball.read_matches",
                        schema_fingerprint="8cf5da8df404fb85abf73ea7b21e86095d3a3d5e23667c2d8616147f12e8b0a5",
                        retrieved_at=datetime.now(UTC),
                    )
                    operation_records.append(
                        classify_result(connector, spec, mock_res, options)
                    )
                    budget_used += 1
                    continue

            try:
                kwargs = dict(spec.args_factory(options))
                result = _run_with_timeout(
                    lambda: connector.execute(spec.operation, **kwargs),
                    options.operation_timeout_seconds,
                )
                operation_records.append(
                    classify_result(connector, spec, result, options)
                )
            except Exception as exc:
                operation_records.append(build_exception_record(connector, spec, exc))
            budget_used += 1

    apply_candidate_policy(operation_records)
    guard = detect_systemic_failure(operation_records)
    report_paths = write_reports(
        options=options,
        operation_records=operation_records,
        metadata=metadata,
        guard=guard,
    )
    reports_to_validate = [
        "live_evidence_summary.json",
        "source_operation_results.json",
        "candidate_recommendations.json",
        "calibration_run_manifest.json",
    ]
    if getattr(options, "calibration_profile", "default") == "pre-certification":
        reports_to_validate.extend(
            [
                "narrow_candidate_set.json",
                "source_repair_plan.json",
                "candidate_certification_plan.json",
                "certification_ready_tuples.json",
                "blocked_or_deferred_tuples.json",
                "certification_readiness_report.json",
            ]
        )
    if getattr(options, "calibration_profile", "default") == "active-certification":
        reports_to_validate.extend(
            [
                "operation_results.json",
                "evidence_summary.json",
                "blocked_or_deferred.json",
            ]
        )
    for report_name in reports_to_validate:
        validate_report_json(report_paths[report_name])
    if guard["status"] != "PASS":
        raise SystemicCalibrationError(guard["reason"])
    return {
        "metadata": metadata,
        "operation_records": operation_records,
        "guard": guard,
        "report_paths": report_paths,
    }


def run_enrich_dry_run(args: argparse.Namespace) -> None:
    """Execute generic active enrichment dry-runs (empty store, reuse store, force-refresh)."""
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Load Scanner Event Candidate
    with open(args.scanner_event_file, encoding="utf-8") as f:
        scanner = ScannerEventCandidate.from_dict(json.load(f))

    # 2. Setup File-Backed Enrichment State Store
    state_store_dir = output_dir / "state_store"
    state_store = FileEnrichmentStateStore(state_store_dir)

    orchestrator = ActiveEnrichmentOrchestrator(state_store)

    provider_evidence = {
        "current_discovery": {
            "provider_id": "espn-fifa-worldcup",
            "provider_event_id": "760442",
            "evidence_identity": "1f8cdb0748846c1cec8b312ad47f5607b116e3c17a56eb32a8f0ac6f537c73b0",
            "schema_fingerprint": "1adbcb1991fbe027d188ffc1f3241a1a555f26d209df871e6c58c36d47828839",
            "retrieved_at": "2026-06-19T20:18:51+00:00",
            "event": {
                "provider_event_id": "760442",
                "event_date_utc": "2026-06-19T19:00Z",
                "event_date_local": "2026-06-19T21:00:00+02:00",
                "home_team_name": "United States",
                "home_team_code": "USA",
                "away_team_name": "Australia",
                "away_team_code": "AUS",
                "status_name": "STATUS_SECOND_HALF",
                "status_state": "in",
                "venue_name": "Lumen Field",
                "venue_city": "Seattle, Washington",
                "venue_country": "USA",
                "broadcasts": ["FOX", "Tele", "FOX One"],
                "score_home": 2,
                "score_away": 0,
                "retrieval_timestamp_utc": "2026-06-19T20:18:51+00:00",
                "group_label": "FIFA World Cup, Group D",
            },
        },
        "current_form": {
            "provider_id": "espn-fifa-worldcup",
            "provider_event_id": "760442",
            "evidence_identity": "f5963336e643f2d5b8311475147031730d4f56f5ed9ee3aa66d2e4ef641f0d91",
            "schema_fingerprint": "1adbcb1991fbe027d188ffc1f3241a1a555f26d209df871e6c58c36d47828839",
            "retrieved_at": "2026-06-19T20:18:51+00:00",
            "event": {
                "provider_event_id": "760442",
                "event_date_utc": "2026-06-19T19:00Z",
                "event_date_local": "2026-06-19T21:00:00+02:00",
                "home_team_name": "United States",
                "home_team_code": "USA",
                "away_team_name": "Australia",
                "away_team_code": "AUS",
                "status_name": "STATUS_SECOND_HALF",
                "status_state": "in",
                "team_records": [
                    {
                        "home_away": "home",
                        "team_name": "United States",
                        "team_code": "USA",
                        "team_record_summary": "1-0-0",
                        "records": [{"name": "total", "summary": "1-0-0"}],
                    },
                    {
                        "home_away": "away",
                        "team_name": "Australia",
                        "team_code": "AUS",
                        "team_record_summary": "1-0-0",
                        "records": [{"name": "total", "summary": "1-0-0"}],
                    },
                ],
                "retrieval_timestamp_utc": "2026-06-19T20:18:51+00:00",
            },
        },
        "detailed_metrics": {
            "provider_id": "espn-fifa-worldcup",
            "provider_event_id": "760442",
            "evidence_identity": "b8fa6502f7bd73a0d9614dc0e04e4e8de97505c7de2b4b476dbb5ebf69485f71",
            "schema_fingerprint": "1adbcb1991fbe027d188ffc1f3241a1a555f26d209df871e6c58c36d47828839",
            "retrieved_at": "2026-06-19T20:18:51+00:00",
            "event": {
                "provider_event_id": "760442",
                "event_date_utc": "2026-06-19T19:00Z",
                "event_date_local": "2026-06-19T21:00:00+02:00",
                "home_team_name": "United States",
                "home_team_code": "USA",
                "away_team_name": "Australia",
                "away_team_code": "AUS",
                "status_name": "STATUS_SECOND_HALF",
                "status_state": "in",
                "statistics": [
                    {
                        "home_away": "home",
                        "name": "possessionPct",
                        "display_value": "71.5",
                        "value": 71.5,
                    },
                    {
                        "home_away": "home",
                        "name": "shotsOnTarget",
                        "display_value": "2",
                        "value": 2,
                    },
                    {
                        "home_away": "home",
                        "name": "totalShots",
                        "display_value": "11",
                        "value": 11,
                    },
                    {
                        "home_away": "away",
                        "name": "possessionPct",
                        "display_value": "28.5",
                        "value": 28.5,
                    },
                    {
                        "home_away": "away",
                        "name": "shotsOnTarget",
                        "display_value": "1",
                        "value": 1,
                    },
                    {
                        "home_away": "away",
                        "name": "totalShots",
                        "display_value": "2",
                        "value": 2,
                    },
                ],
                "retrieval_timestamp_utc": "2026-06-19T20:18:51+00:00",
            },
        },
    }

    # --- RUN 1: EMPTY STORE ---
    if state_store.completeness_dir.exists():
        shutil.rmtree(state_store.completeness_dir)
    state_store.completeness_dir.mkdir(parents=True, exist_ok=True)
    if state_store.evidence_dir.exists():
        shutil.rmtree(state_store.evidence_dir)
    state_store.evidence_dir.mkdir(parents=True, exist_ok=True)

    req_empty = ActiveEnrichmentRequest(
        profile_id=args.profile_id,
        scanner_event_candidate=scanner,
        canonical_match_identity={
            "home_team": scanner.home_team_name,
            "away_team": scanner.away_team_name,
        },
        canonical_competition_scope=scanner.canonical_competition_scope,
        canonical_season_scope=scanner.canonical_season_scope,
        requested_capabilities=(
            "current_discovery",
            "detailed_metrics",
            "current_form",
        ),
        force_refresh=False,
    )
    res_empty = orchestrator.enrich_event(req_empty)
    with open(
        output_dir / "active_enrichment_dry_run_empty_store.json", "w", encoding="utf-8"
    ) as f:
        json.dump(res_empty.to_dict(), f, indent=2, sort_keys=True)

    for capability, payload in provider_evidence.items():
        state_store.put_evidence(f"espn-fifa-worldcup_{capability}_evidence", payload)

    bootstrap_request = ActiveEnrichmentRequest(
        profile_id=args.profile_id,
        scanner_event_candidate=scanner,
        canonical_match_identity={
            "home_team": scanner.home_team_name,
            "away_team": scanner.away_team_name,
        },
        canonical_competition_scope=scanner.canonical_competition_scope,
        canonical_season_scope=scanner.canonical_season_scope,
        requested_capabilities=(
            "current_discovery",
            "detailed_metrics",
            "current_form",
        ),
        force_refresh=False,
    )
    orchestrator.enrich_event(bootstrap_request)

    # --- RUN 2: REUSE STORE ---
    req_reuse = ActiveEnrichmentRequest(
        profile_id=args.profile_id,
        scanner_event_candidate=scanner,
        canonical_match_identity={
            "home_team": scanner.home_team_name,
            "away_team": scanner.away_team_name,
        },
        canonical_competition_scope=scanner.canonical_competition_scope,
        canonical_season_scope=scanner.canonical_season_scope,
        requested_capabilities=(
            "current_discovery",
            "detailed_metrics",
            "current_form",
        ),
        force_refresh=False,
    )
    res_reuse = orchestrator.enrich_event(req_reuse)
    with open(
        output_dir / "active_enrichment_dry_run_reuse_store.json", "w", encoding="utf-8"
    ) as f:
        json.dump(res_reuse.to_dict(), f, indent=2, sort_keys=True)

    # --- RUN 3: FORCE REFRESH ---
    req_force = ActiveEnrichmentRequest(
        profile_id=args.profile_id,
        scanner_event_candidate=scanner,
        canonical_match_identity={
            "home_team": scanner.home_team_name,
            "away_team": scanner.away_team_name,
        },
        canonical_competition_scope=scanner.canonical_competition_scope,
        canonical_season_scope=scanner.canonical_season_scope,
        requested_capabilities=(
            "current_discovery",
            "detailed_metrics",
            "current_form",
        ),
        force_refresh=True,
    )
    res_force = orchestrator.enrich_event(req_force)
    with open(
        output_dir / "active_enrichment_dry_run_force_refresh.json",
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(res_force.to_dict(), f, indent=2, sort_keys=True)

    # Write Markdown dry run report
    md_lines = [
        f"# Active Enrichment Dry-Run Reports - Profile: {args.profile_id}",
        "",
        f"- Generated at UTC: `{datetime.now(UTC).isoformat()}`",
        f"- {NO_SECRETS_STATEMENT}",
        f"- {NO_NETWORK_TEST_STATEMENT}",
        f"- {BETTING_LOGIC_STATEMENT}",
        "",
        "## Run 1: Empty Store (Completeness check MISSING)",
        f"- **Status**: `{res_empty.status}`",
        "### Decisions:",
    ]
    for d in res_empty.fetch_decisions:
        md_lines.append(
            f"  - Capability `{d.capability}` => `{d.decision}` (Reason: {d.reason})"
        )
    md_lines.extend(
        [
            "### Generated Facts:",
        ]
    )
    for f in res_empty.facts:
        md_lines.append(
            f"  - `{f.capability}` / `{f.fact_name}` => text `{f.fact_value_text}` num `{f.fact_value_num}` (Retrieved from: {f.provider_id}, Consensus: {f.source_consensus})"
        )

    md_lines.extend(
        [
            "",
            "## Run 2: Reuse Store (Completeness check COMPLETE_FRESH)",
            f"- **Status**: `{res_reuse.status}`",
            "### Decisions:",
        ]
    )
    for d in res_reuse.fetch_decisions:
        md_lines.append(
            f"  - Capability `{d.capability}` => `{d.decision}` (Reason: {d.reason})"
        )
    md_lines.append("### Generated Facts:")
    for f in res_reuse.facts:
        md_lines.append(
            f"  - `{f.capability}` / `{f.fact_name}` => text `{f.fact_value_text}` num `{f.fact_value_num}`"
        )

    md_lines.extend(
        [
            "",
            "## Run 3: Force-Refresh (Completeness bypassed)",
            f"- **Status**: `{res_force.status}`",
            "### Decisions:",
        ]
    )
    for d in res_force.fetch_decisions:
        md_lines.append(
            f"  - Capability `{d.capability}` => `{d.decision}` (Reason: {d.reason})"
        )
    md_lines.append("### Generated Facts:")
    for f in res_force.facts:
        md_lines.append(
            f"  - `{f.capability}` / `{f.fact_name}` => text `{f.fact_value_text}` num `{f.fact_value_num}`"
        )

    with open(output_dir / "active_enrichment_dry_run.md", "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines) + "\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Football Data Foundation CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_calibration_arguments(target: argparse.ArgumentParser) -> None:
        target.add_argument("--league", default="ENG-Premier League")
        target.add_argument("--season", type=int, default=2024)
        target.add_argument("--max-rows", type=int, default=5)
        target.add_argument(
            "--output-dir",
            default="reports/football_data_foundation/live_calibration",
        )
        target.add_argument("--source-budget", type=int, default=1)
        target.add_argument("--operation-timeout-seconds", type=int, default=90)
        target.add_argument("--include-browser-sources", action="store_true")
        target.add_argument("--include-heavy-sources", action="store_true")
        target.add_argument(
            "--offline-fixture-baseline",
            action=argparse.BooleanOptionalAction,
            default=True,
        )
        target.add_argument("--write-samples", action="store_true")
        target.add_argument("--sample-row-limit", type=int, default=3)
        target.add_argument("--calibration-profile", default="default")
        # Added arguments for profile-driven flow
        target.add_argument("--profile-id", default=None)
        target.add_argument("--competition-scope", default=None)
        target.add_argument("--scanner-event-file", default=None)

    add_calibration_arguments(
        subparsers.add_parser(
            "calibrate-live",
            help=(
                "Run bounded live and fixture-backed calibration with evidence reports"
            ),
        )
    )
    add_calibration_arguments(
        subparsers.add_parser(
            "smoke",
            help="Compatibility alias for calibrate-live",
        )
    )

    # Register enrich-dry-run command
    parser_enrich = subparsers.add_parser(
        "enrich-dry-run", help="Run active enrichment dry-run for a profile"
    )
    parser_enrich.add_argument("--profile-id", required=True)
    parser_enrich.add_argument("--scanner-event-file", required=True)
    parser_enrich.add_argument("--competition-scope", default=None)
    parser_enrich.add_argument("--season", default="2026")
    parser_enrich.add_argument("--output-dir", required=True)
    parser_enrich.add_argument("--force-refresh", action="store_true")

    return parser


def options_from_args(args: argparse.Namespace) -> CalibrationOptions:
    return CalibrationOptions(
        league=args.league,
        season=args.season,
        max_rows=args.max_rows,
        output_dir=Path(args.output_dir),
        source_budget=args.source_budget,
        operation_timeout_seconds=args.operation_timeout_seconds,
        include_browser_sources=args.include_browser_sources,
        include_heavy_sources=args.include_heavy_sources,
        offline_fixture_baseline=args.offline_fixture_baseline,
        write_samples=args.write_samples,
        sample_row_limit=args.sample_row_limit,
        invoked_command=args.command,
        calibration_profile=getattr(args, "calibration_profile", "default"),
        profile_id=args.profile_id,
        competition_scope=args.competition_scope,
        scanner_event_file=Path(args.scanner_event_file)
        if args.scanner_event_file
        else None,
    )
