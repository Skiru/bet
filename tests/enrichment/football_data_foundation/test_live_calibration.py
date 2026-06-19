from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from bet.enrichment.football_data_foundation import cli
from bet.enrichment.football_data_foundation.calibration import (
    ACCEPTED_FOUNDATION_SHA,
    BETTING_LOGIC_STATEMENT,
    NO_SECRETS_STATEMENT,
    CalibrationOperationSpec,
    CalibrationOptions,
    OperationRecord,
    apply_candidate_policy,
    build_parser,
    calibrate_live,
)
from bet.enrichment.football_data_foundation.connector_kernel import BaseConnector
from bet.integration.source_result import SourceOperationResult, SourceResultStatus

REPO_ROOT = Path(__file__).resolve().parents[3]


class FakeConnector(BaseConnector):
    def __init__(
        self,
        *,
        provider: str,
        source_family: str,
        source_class: str,
        execute_impl: Any,
    ) -> None:
        self.provider = provider
        self.source_family = source_family
        self.source_class = source_class
        self.supported_operations = ()
        self.supported_capabilities = ()
        self.access_requirements = ()
        self.dependency_requirements = ()
        self.transport_type = "test"
        self.pagination_model = "test"
        self.cache_policy = "test"
        self.state_model = "test"
        self.evidence_policy = "test"
        self.drift_policy = "test"
        self._execute_impl = execute_impl

    def execute(self, operation: str, **kwargs: Any) -> SourceOperationResult[Any]:
        return self._execute_impl(operation, **kwargs)


def make_options(tmp_path: Path) -> CalibrationOptions:
    return CalibrationOptions(
        league="ENG-Premier League",
        season=2024,
        max_rows=5,
        output_dir=tmp_path / "live_calibration",
        source_budget=1,
        operation_timeout_seconds=5,
    )


def patch_common_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "bet.enrichment.football_data_foundation.calibration.git_metadata",
        lambda cwd=None: {
            "branch": "feat/multisport-enrichment-v1",
            "upstream": "origin/feat/multisport-enrichment-v1",
            "head": ACCEPTED_FOUNDATION_SHA,
        },
    )
    monkeypatch.setattr(
        "bet.enrichment.football_data_foundation.calibration.library_versions",
        lambda: {"soccerdata": "test-version"},
    )
    monkeypatch.setattr(
        "bet.enrichment.football_data_foundation.calibration.iso_now",
        lambda: "2026-06-19T00:00:00+00:00",
    )


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_calibrate_live_writes_all_reports_with_mocked_connectors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    patch_common_metadata(monkeypatch)

    connector = FakeConnector(
        provider="fake",
        source_family="test",
        source_class="LiveSource",
        execute_impl=lambda operation, **kwargs: SourceOperationResult(
            status=SourceResultStatus.SUCCESS,
            value=[{"team": "Arsenal", "goals": 2}],
            provider="fake",
            operation=operation,
            request_identity="fake.live.read_schedule",
            parser_version="parser-v1",
            normalization_version="norm-v1",
            schema_fingerprint="schema-1",
            parser_diagnostics={"scope": "league-season"},
        ),
    )
    monkeypatch.setattr(
        "bet.enrichment.football_data_foundation.calibration.operation_plan_for_connector",
        lambda _connector, _options: [
            CalibrationOperationSpec(
                operation="read_schedule",
                capability="current_discovery",
                competition_scope="ENG-Premier League",
                season_scope="2024",
                execution_mode="live",
            )
        ],
    )

    result = calibrate_live(make_options(tmp_path), connectors=[connector])

    report_dir = make_options(tmp_path).output_dir
    expected_reports = {
        "live_evidence_summary.json",
        "live_evidence_summary.md",
        "source_operation_results.json",
        "candidate_recommendations.json",
        "calibration_run_manifest.json",
    }
    assert {path.name for path in result["report_paths"].values()} == expected_reports
    for report_name in expected_reports:
        assert (report_dir / report_name).exists()

    summary = read_json(report_dir / "live_evidence_summary.json")
    assert summary["accepted_foundation_sha"] == ACCEPTED_FOUNDATION_SHA
    assert (
        summary["statements"]["betting_decision_logic_unchanged"]
        == BETTING_LOGIC_STATEMENT
    )
    assert (
        summary["statements"]["no_secrets_cookies_proxy_browser_profiles"]
        == NO_SECRETS_STATEMENT
    )
    operation = summary["operation_results"][0]
    assert operation["status"] == "EVIDENCE_READY"
    assert operation["evidence_identity"]["schema_fingerprint"] == "schema-1"
    assert "sample_rows" not in operation


def test_smoke_alias_delegates_to_calibration_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_calibrate(options: CalibrationOptions) -> dict[str, Any]:
        captured["options"] = options
        return {}

    monkeypatch.setattr(cli, "calibrate_live", fake_calibrate)
    cli.main(["smoke", "--league", "ENG-Premier League", "--season", "2024"])
    assert captured["options"].invoked_command == "smoke"


def test_one_failing_source_does_not_fail_whole_calibration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    patch_common_metadata(monkeypatch)
    success_connector = FakeConnector(
        provider="fake",
        source_family="test",
        source_class="SuccessSource",
        execute_impl=lambda operation, **kwargs: SourceOperationResult(
            status=SourceResultStatus.SUCCESS,
            value=[{"value": 1}],
            operation=operation,
            request_identity="success.identity",
            parser_version="parser-v1",
            normalization_version="norm-v1",
            schema_fingerprint="schema-1",
            parser_diagnostics={"scope": "league-season"},
        ),
    )
    failing_connector = FakeConnector(
        provider="fake",
        source_family="test",
        source_class="FailingSource",
        execute_impl=lambda operation, **kwargs: (_ for _ in ()).throw(
            RuntimeError("boom")
        ),
    )
    plans = {
        "test/SuccessSource": [
            CalibrationOperationSpec(
                operation="ok",
                capability="current_discovery",
                competition_scope="ENG-Premier League",
                season_scope="2024",
                execution_mode="live",
            )
        ],
        "test/FailingSource": [
            CalibrationOperationSpec(
                operation="fail",
                capability="current_discovery",
                competition_scope="ENG-Premier League",
                season_scope="2024",
                execution_mode="live",
            )
        ],
    }
    monkeypatch.setattr(
        "bet.enrichment.football_data_foundation.calibration.operation_plan_for_connector",
        lambda connector, _options: plans[
            f"{connector.source_family}/{connector.source_class}"
        ],
    )

    result = calibrate_live(
        make_options(tmp_path), connectors=[success_connector, failing_connector]
    )

    statuses = {
        record.source_class: record.status
        for record in result["operation_records"]
    }
    assert statuses == {
        "SuccessSource": "EVIDENCE_READY",
        "FailingSource": "PARSE_ERROR",
    }
    assert result["guard"]["status"] == "PASS"


def test_systemic_harness_failure_is_detected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    patch_common_metadata(monkeypatch)
    connectors = [
        FakeConnector(
            provider="fake",
            source_family="test",
            source_class=name,
            execute_impl=lambda operation, **kwargs: (_ for _ in ()).throw(
                RuntimeError("boom")
            ),
        )
        for name in ("A", "B")
    ]
    monkeypatch.setattr(
        "bet.enrichment.football_data_foundation.calibration.operation_plan_for_connector",
        lambda _connector, _options: [
            CalibrationOperationSpec(
                operation="fail",
                capability="current_discovery",
                competition_scope="ENG-Premier League",
                season_scope="2024",
                execution_mode="live",
            )
        ],
    )

    with pytest.raises(Exception, match="same uncaught harness exception"):
        calibrate_live(make_options(tmp_path), connectors=connectors)

    report = read_json(
        make_options(tmp_path).output_dir / "calibration_run_manifest.json"
    )
    assert (
        report["systemic_failure_guard"]["status"]
        == "BLOCKED_CALIBRATION_SYSTEMIC_FAILURE"
    )


def test_default_flags_skip_browser_and_heavy_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    patch_common_metadata(monkeypatch)
    connector = FakeConnector(
        provider="fake",
        source_family="test",
        source_class="GuardedSource",
        execute_impl=lambda operation, **kwargs: pytest.fail("execute should not run"),
    )
    monkeypatch.setattr(
        "bet.enrichment.football_data_foundation.calibration.operation_plan_for_connector",
        lambda _connector, _options: [
            CalibrationOperationSpec(
                operation="browser_op",
                capability="current_discovery",
                competition_scope="ENG-Premier League",
                season_scope="2024",
                execution_mode="live",
                browser_heavy=True,
            ),
            CalibrationOperationSpec(
                operation="heavy_op",
                capability="fixture_team_statistics",
                competition_scope="ENG-Premier League",
                season_scope="2024",
                execution_mode="live",
                heavy=True,
            ),
        ],
    )

    result = calibrate_live(make_options(tmp_path), connectors=[connector])
    statuses = [record.status for record in result["operation_records"]]
    reasons = [
        record.diagnostics["classification_reason"]
        for record in result["operation_records"]
    ]
    assert statuses == ["NOT_SUPPORTED", "NOT_SUPPORTED"]
    assert reasons == [
        "browser_source_disabled_by_default",
        "heavy_source_disabled_by_default",
    ]


def test_optional_missing_dependency_produces_dependency_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    patch_common_metadata(monkeypatch)
    connector = FakeConnector(
        provider="fake",
        source_family="test",
        source_class="OptionalBridge",
        execute_impl=lambda operation, **kwargs: pytest.fail("execute should not run"),
    )
    monkeypatch.setattr(
        "bet.enrichment.football_data_foundation.calibration.operation_plan_for_connector",
        lambda _connector, _options: [
            CalibrationOperationSpec(
                operation="import_probe",
                capability="canonical_event_team_identity",
                competition_scope="global",
                season_scope="global",
                execution_mode="import_smoke",
                dependency_name="missing_optional_dependency_xyz",
                import_target="missing_optional_dependency_xyz",
                count_against_budget=False,
            )
        ],
    )

    result = calibrate_live(make_options(tmp_path), connectors=[connector])
    record = result["operation_records"][0]
    assert record.status == "DEPENDENCY_MISSING"
    assert record.diagnostics["dependency"] == "missing_optional_dependency_xyz"


def test_candidate_policy_blocks_fixture_only_and_missing_evidence() -> None:
    fixture_record = OperationRecord(
        source_id="test/Fixture",
        provider="fake",
        source_family="test",
        source_class="Fixture",
        operation="read_matches",
        capability="current_discovery",
        execution_mode="fixture",
        competition_scope="fixture",
        season_scope="fixture",
        status="EVIDENCE_READY",
        row_count=1,
        request_identity="fixture.identity",
        source_result_status="SUCCESS",
        error_code="",
        diagnostics={"scope": "fixture-baseline"},
        evidence_identity={"schema_fingerprint": "schema-1"},
        schema_fingerprint="schema-1",
        data_fingerprint="data-1",
    )
    missing_evidence_record = OperationRecord(
        source_id="test/NoEvidence",
        provider="fake",
        source_family="test",
        source_class="NoEvidence",
        operation="read_schedule",
        capability="current_discovery",
        execution_mode="live",
        competition_scope="ENG-Premier League",
        season_scope="2024",
        status="EVIDENCE_READY",
        row_count=1,
        request_identity="live.identity",
        source_result_status="SUCCESS",
        error_code="",
        diagnostics={"scope": "league-season"},
        evidence_identity=None,
        schema_fingerprint="",
        data_fingerprint="",
    )

    apply_candidate_policy([fixture_record, missing_evidence_record])

    assert fixture_record.candidate_for_future_selectable_candidate is False
    assert fixture_record.blocking_reason == "fixture_only_reference_data"
    assert missing_evidence_record.candidate_for_future_selectable_candidate is False
    assert (
        missing_evidence_record.blocking_reason
        == "evidence_identity_or_schema_missing"
    )


def test_reports_do_not_mutate_config_or_emit_certified_selectable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    patch_common_metadata(monkeypatch)
    routing_path = REPO_ROOT / "config/football_routing.yaml"
    capability_path = REPO_ROOT / "config/provider_capability_matrix.json"
    routing_before = routing_path.read_text(encoding="utf-8")
    capability_before = capability_path.read_text(encoding="utf-8")

    connector = FakeConnector(
        provider="fake",
        source_family="test",
        source_class="LiveSource",
        execute_impl=lambda operation, **kwargs: SourceOperationResult(
            status=SourceResultStatus.SUCCESS,
            value=[{"team": "Arsenal"}],
            operation=operation,
            request_identity="fake.identity",
            parser_version="parser-v1",
            normalization_version="norm-v1",
            schema_fingerprint="schema-1",
            parser_diagnostics={"scope": "league-season"},
        ),
    )
    monkeypatch.setattr(
        "bet.enrichment.football_data_foundation.calibration.operation_plan_for_connector",
        lambda _connector, _options: [
            CalibrationOperationSpec(
                operation="read_schedule",
                capability="current_discovery",
                competition_scope="ENG-Premier League",
                season_scope="2024",
                execution_mode="live",
            )
        ],
    )

    calibrate_live(make_options(tmp_path), connectors=[connector])

    assert routing_path.read_text(encoding="utf-8") == routing_before
    assert capability_path.read_text(encoding="utf-8") == capability_before
    for report_path in make_options(tmp_path).output_dir.iterdir():
        content = report_path.read_text(encoding="utf-8")
        assert "CERTIFIED_SELECTABLE" not in content
        assert "SELECTABLE_CANDIDATE" not in content


def test_parser_defaults_match_safe_command_shape() -> None:
    parser = build_parser()
    args = parser.parse_args(["calibrate-live"])
    assert args.include_browser_sources is False
    assert args.include_heavy_sources is False
    assert args.offline_fixture_baseline is True
    assert args.write_samples is False
    assert args.sample_row_limit == 3
