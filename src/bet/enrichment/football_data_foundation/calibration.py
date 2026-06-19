from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.metadata
import json
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

ACCEPTED_FOUNDATION_SHA = "c0aa63231cdb80aa0698bae30567b6df4a7c6d40"
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

    return {
        "branch": _git("branch", "--show-current"),
        "upstream": _git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"),
        "head": _git("rev-parse", "HEAD"),
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
                competition_scope=live_competition_scope,
                season_scope=live_season_scope,
                execution_mode="live",
                args_factory=lambda _opts: {
                    "date": _season_context_date(options.season),
                    "scope": "league-season",
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
                competition_scope=live_competition_scope,
                season_scope=live_season_scope,
                execution_mode="live",
                args_factory=lambda _opts: {
                    "init_kwargs": dict(default_init_kwargs),
                    "scope": "league-season",
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
                        (
                            fixture_root()
                            / "rich_probes/fotmob_matches.json"
                        ).read_text(encoding="utf-8")
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
                        (
                            fixture_root()
                            / "rich_probes/sofascore_stats.json"
                        ).read_text(encoding="utf-8")
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


def apply_candidate_policy(records: list[OperationRecord]) -> None:
    additive_only = {"additive_schema_drift", "fixture-baseline", "league-season"}
    for record in records:
        if record.status not in {"EVIDENCE_READY", "PARTIAL"}:
            record.candidate_for_future_selectable_candidate = False
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
        "calibration_run_manifest.json": json.dumps(
            manifest, indent=2, sort_keys=True
        ),
    }
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
        },
        "source_library_versions": library_versions(),
    }
    operation_records: list[OperationRecord] = []
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
    for report_name in (
        "live_evidence_summary.json",
        "source_operation_results.json",
        "candidate_recommendations.json",
        "calibration_run_manifest.json",
    ):
        validate_report_json(report_paths[report_name])
    if guard["status"] != "PASS":
        raise SystemicCalibrationError(guard["reason"])
    return {
        "metadata": metadata,
        "operation_records": operation_records,
        "guard": guard,
        "report_paths": report_paths,
    }


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

    add_calibration_arguments(
        subparsers.add_parser(
            "calibrate-live",
            help=(
                "Run bounded live and fixture-backed calibration with evidence "
                "reports"
            ),
        )
    )
    add_calibration_arguments(
        subparsers.add_parser(
            "smoke",
            help="Compatibility alias for calibrate-live",
        )
    )
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
    )
