"""S1e event-universe and end-to-end accounting contracts."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from bet.pipeline.event_accounting import (
    ACCOUNTING_BOUNDARY_STEPS,
    EventAccountingError,
    EventAccountingLedger,
    deduplicate_events,
    canonical_event_id,
)
from scripts.pipeline_steps import s1e_event_ledger

DAY = "2026-07-13"
RUN_ID = "event-accounting-test"


def _events() -> list[dict]:
    return [
        {"fixture_id": "football-1", "sport": "football", "competition": "test-league", "home_team": "A", "away_team": "B", "kickoff": "2026-07-13T12:00:00Z"},
        {"fixture_id": "tennis-1", "sport": "tennis", "competition": "test-league", "home_team": "C", "away_team": "D", "kickoff": "2026-07-13T14:00:00Z"},
    ]


def _env(tmp_path: Path) -> dict[str, str]:
    root = tmp_path / "run"
    return {
        "BET_PIPELINE_RUNTIME_MODE": "DRY_RUN",
        "BET_PIPELINE_BETTING_DAY": DAY,
        "BET_PIPELINE_RUN_ID": RUN_ID,
        "BET_PIPELINE_RUN_ROOT": str(root),
        "BET_PIPELINE_DATA_DIR": str(root / "data"),
        "BET_PIPELINE_COUPON_DIR": str(root / "coupons"),
        "BET_PIPELINE_ARTIFACT_DIR": str(root / "artifacts"),
    }


def _canonical_evidence(env: dict[str, str], step: str) -> Path:
    return Path(env["BET_PIPELINE_RUN_ROOT"]) / "pipeline_runs" / DAY / RUN_ID / "artifacts" / f"{step}.json"


def _seed_s1(env: dict[str, str], events: list[dict], *, source_root: Path | None = None, day: str = DAY) -> None:
    root = Path(env["BET_PIPELINE_RUN_ROOT"])
    source = (source_root or root) / "data/market_matrix.json"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(json.dumps({"events": events}), encoding="utf-8")
    evidence = _canonical_evidence(env, "S1")
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text(json.dumps({
        "schema_version": 1,
        "artifact_type": "SCRIPT_EVIDENCE",
        "step_id": "S1",
        "status": "PASS",
        "betting_day": day,
        "run_id": RUN_ID,
        "payload": {"market_matrix_path": str(source)},
    }), encoding="utf-8")


def _run_s1e(env: dict[str, str]) -> int:
    argv = ["s1e_event_ledger.py", "--date", DAY, "--run-id", RUN_ID, "--runtime-mode", "DRY_RUN"]
    with patch.dict(os.environ, env, clear=False), patch.object(sys, "argv", argv):
        with pytest.raises(SystemExit) as exc:
            s1e_event_ledger.main()
    return int(exc.value.code)


def test_s1e_materializes_identity_deduplicated_multi_sport_universe(tmp_path: Path):
    env = _env(tmp_path)
    events = _events() + [_events()[0]]
    _seed_s1(env, events)
    assert _run_s1e(env) == 0
    evidence = json.loads(_canonical_evidence(env, "S1e").read_text())
    universe = json.loads(Path(evidence["payload"]["s1e_json_output"]).read_text())
    assert universe["after_dedup_count"] == 2
    assert len(set(universe["canonical_event_ids"])) == 2
    assert len(universe["event_records"]) == 2
    assert {record["terminal_status"] for record in universe["event_records"]} == {"CONTINUE"}
    assert universe["source_s1_sha256"]
    ledger_payload = json.loads((Path(env["BET_PIPELINE_RUN_ROOT"]) / "event_accounting_ledger.json").read_text())
    assert ledger_payload["events_with_terminal_status"] == 2
    assert ledger_payload["unaccounted_event_ids"] == []


def test_s1e_accepts_zero_event_universe_after_discovery_attempt(tmp_path: Path):
    env = _env(tmp_path)
    _seed_s1(env, [])
    assert _run_s1e(env) == 0
    evidence = json.loads(_canonical_evidence(env, "S1e").read_text())
    universe = json.loads(Path(evidence["payload"]["s1e_json_output"]).read_text())
    assert universe["zero_event_universe"] is True
    assert evidence["payload"]["outcome"] == "NO_ACTION_TERMINAL"


def test_s1e_rejects_cross_run_and_wrong_day_binding(tmp_path: Path):
    env = _env(tmp_path)
    _seed_s1(env, _events(), source_root=tmp_path / "other-run")
    assert _run_s1e(env) == 5
    wrong_day_env = _env(tmp_path / "wrong-day")
    _seed_s1(wrong_day_env, _events(), day="2026-07-12")
    assert _run_s1e(wrong_day_env) == 5


def _initialized_ledger(tmp_path: Path, events: list[dict]) -> EventAccountingLedger:
    root = tmp_path / "run"
    root.mkdir(parents=True)
    normalized = deduplicate_events(events)
    universe = root / "universe.json"
    universe.write_text(json.dumps({
        "schema_version": 1,
        "artifact_type": "S1E_EVENT_UNIVERSE_LEDGER",
        "betting_day": DAY,
        "run_id": RUN_ID,
        "events": normalized,
    }), encoding="utf-8")
    return EventAccountingLedger.initialize(root, universe, betting_day=DAY, run_id=RUN_ID)


def test_every_boundary_accounts_for_every_event_with_missing_tips_and_odds_explicit(tmp_path: Path):
    events = _events()
    ledger = _initialized_ledger(tmp_path, events)
    evt_ids = [canonical_event_id(e) for e in events]
    records = [
        {"canonical_event_id": evt_ids[0], "terminal_status": "TIPSTER_MISSING_EXPLICIT"},
        {"canonical_event_id": evt_ids[1], "terminal_status": "PRICE_PENDING_EXPLICIT"},
    ]
    for step in ACCOUNTING_BOUNDARY_STEPS:
        payload = ledger.record_boundary(step, records=records)
        assert payload["after_dedup_count"] == payload["events_with_terminal_status"] == 2
        assert payload["unaccounted_event_ids"] == []
    assert "TIPSTER_MISSING_EXPLICIT" in str(payload["boundaries"])
    assert "PRICE_PENDING_EXPLICIT" in str(payload["boundaries"])


def test_boundary_cannot_fabricate_default_statuses(tmp_path: Path):
    ledger = _initialized_ledger(tmp_path, _events())
    with pytest.raises(EventAccountingError, match="EVENT_BOUNDARY_RECORDS_MISSING"):
        ledger.record_boundary("S2", records=None)


def test_event_loss_and_unknown_event_fail_closed(tmp_path: Path):
    events = _events()
    ledger = _initialized_ledger(tmp_path, events)
    evt_ids = [canonical_event_id(e) for e in events]
    with pytest.raises(EventAccountingError, match="EVENT_BOUNDARY_LOSS"):
        ledger.record_boundary(
            "S2",
            records=[{"canonical_event_id": evt_ids[0], "terminal_status": "TIPSTER_MISSING"}],
        )
    with pytest.raises(EventAccountingError, match="UNKNOWN_EVENT"):
        ledger.record_boundary(
            "S2",
            records=[
                {"canonical_event_id": evt_ids[0], "terminal_status": "PASS"},
                {"canonical_event_id": "evt-unknown-123", "terminal_status": "PASS"},
            ],
        )


def test_duplicate_event_records_fail_closed(tmp_path: Path):
    events = _events()
    ledger = _initialized_ledger(tmp_path, events)
    evt_ids = [canonical_event_id(e) for e in events]
    with pytest.raises(EventAccountingError, match="EVENT_BOUNDARY_DUPLICATE_EVENT"):
        ledger.record_boundary(
            "S2",
            records=[
                {"canonical_event_id": evt_ids[0], "terminal_status": "PASS"},
                {"canonical_event_id": evt_ids[0], "terminal_status": "PASS"},
            ],
        )


def test_strict_loader_adversarial_matrix(tmp_path: Path):
    from bet.pipeline.integration_artifacts import strict_validate_step_output
    run_root = tmp_path / "run"
    run_root.mkdir()
    data_dir = run_root / "data"
    data_dir.mkdir()

    betting_day = "2026-07-16"
    run_id = "prod-run"

    # Create valid S1e universe file
    s1e_file = data_dir / f"{betting_day}_s1e_event_universe.json"
    s1e_file.write_text(json.dumps({
        "artifact_type": "S1E_EVENT_UNIVERSE_LEDGER",
        "canonical_event_ids": ["evt-1", "evt-2"],
        "events": [],
    }))

    # 1. Missing output
    missing_path = run_root / "nonexistent.json"
    with pytest.raises(FileNotFoundError, match="STEP_OUTPUT_MISSING"):
        strict_validate_step_output(
            step_id="S3",
            output_path=missing_path,
            output_data={},
            run_root=run_root,
            betting_day=betting_day,
            run_id=run_id,
            expected_artifact_type="S3_DEEP_STATS",
        )

    # 2. Outside run path
    outside_path = tmp_path / "outside.json"
    outside_path.write_text("{}")
    with pytest.raises(ValueError, match="STEP_OUTPUT_OUTSIDE_RUN"):
        strict_validate_step_output(
            step_id="S3",
            output_path=outside_path,
            output_data={},
            run_root=run_root,
            betting_day=betting_day,
            run_id=run_id,
            expected_artifact_type="S3_DEEP_STATS",
        )

    # 3. Symlink escape
    symlink_path = run_root / "symlink.json"
    symlink_path.symlink_to(s1e_file)
    with pytest.raises(ValueError, match="STEP_OUTPUT_OUTSIDE_RUN"):
        strict_validate_step_output(
            step_id="S3",
            output_path=symlink_path,
            output_data={},
            run_root=run_root,
            betting_day=betting_day,
            run_id=run_id,
            expected_artifact_type="S3_DEEP_STATS",
        )

    # 4. Empty file
    empty_path = run_root / "empty.json"
    empty_path.write_text("")
    with pytest.raises(ValueError, match="STEP_OUTPUT_MISSING"):
        strict_validate_step_output(
            step_id="S3",
            output_path=empty_path,
            output_data={},
            run_root=run_root,
            betting_day=betting_day,
            run_id=run_id,
            expected_artifact_type="S3_DEEP_STATS",
        )

    # 5. Wrong artifact type
    valid_file = run_root / "valid.json"
    valid_file.write_text("{}")
    with pytest.raises(ValueError, match="STEP_TYPE_MISMATCH"):
        strict_validate_step_output(
            step_id="S3",
            output_path=valid_file,
            output_data={"artifact_type": "WRONG_TYPE"},
            run_root=run_root,
            betting_day=betting_day,
            run_id=run_id,
            expected_artifact_type="S3_DEEP_STATS",
        )

    # 6. Wrong betting day or run ID
    with pytest.raises(ValueError, match="STEP_DAY_MISMATCH"):
        strict_validate_step_output(
            step_id="S3",
            output_path=valid_file,
            output_data={"artifact_type": "S3_DEEP_STATS", "betting_day": "wrong-day", "run_id": run_id},
            run_root=run_root,
            betting_day=betting_day,
            run_id=run_id,
            expected_artifact_type="S3_DEEP_STATS",
        )

    # 7. Missing event_records
    with pytest.raises(ValueError, match="EVENT_BOUNDARY_RECORDS_MISSING"):
        strict_validate_step_output(
            step_id="S3",
            output_path=valid_file,
            output_data={"artifact_type": "S3_DEEP_STATS", "betting_day": betting_day, "run_id": run_id},
            run_root=run_root,
            betting_day=betting_day,
            run_id=run_id,
            expected_artifact_type="S3_DEEP_STATS",
        )

    # 8. Duplicate event
    with pytest.raises(ValueError, match="EVENT_BOUNDARY_DUPLICATE_EVENT"):
        strict_validate_step_output(
            step_id="S3",
            output_path=valid_file,
            output_data={
                "artifact_type": "S3_DEEP_STATS",
                "betting_day": betting_day,
                "run_id": run_id,
                "event_records": [
                    {"canonical_event_id": "evt-1", "terminal_status": "CONTINUE"},
                    {"canonical_event_id": "evt-1", "terminal_status": "CONTINUE"},
                ]
            },
            run_root=run_root,
            betting_day=betting_day,
            run_id=run_id,
            expected_artifact_type="S3_DEEP_STATS",
        )

    # 9. Unknown/extra event
    with pytest.raises(ValueError, match="EVENT_BOUNDARY_UNKNOWN_EVENT"):
        strict_validate_step_output(
            step_id="S3",
            output_path=valid_file,
            output_data={
                "artifact_type": "S3_DEEP_STATS",
                "betting_day": betting_day,
                "run_id": run_id,
                "event_records": [
                    {"canonical_event_id": "evt-1", "terminal_status": "CONTINUE"},
                    {"canonical_event_id": "evt-2", "terminal_status": "CONTINUE"},
                    {"canonical_event_id": "evt-unknown", "terminal_status": "CONTINUE"},
                ]
            },
            run_root=run_root,
            betting_day=betting_day,
            run_id=run_id,
            expected_artifact_type="S3_DEEP_STATS",
        )

    # 10. Loss / missing event
    with pytest.raises(ValueError, match="EVENT_BOUNDARY_LOSS"):
        strict_validate_step_output(
            step_id="S3",
            output_path=valid_file,
            output_data={
                "artifact_type": "S3_DEEP_STATS",
                "betting_day": betting_day,
                "run_id": run_id,
                "event_records": [
                    {"canonical_event_id": "evt-1", "terminal_status": "CONTINUE"},
                ]
            },
            run_root=run_root,
            betting_day=betting_day,
            run_id=run_id,
            expected_artifact_type="S3_DEEP_STATS",
        )

    # 11. Invalid terminal status
    with pytest.raises(ValueError, match="EVENT_BOUNDARY_RECORD_INVALID"):
        strict_validate_step_output(
            step_id="S3",
            output_path=valid_file,
            output_data={
                "artifact_type": "S3_DEEP_STATS",
                "betting_day": betting_day,
                "run_id": run_id,
                "event_records": [
                    {"canonical_event_id": "evt-1", "terminal_status": "INVALID_STATUS"},
                    {"canonical_event_id": "evt-2", "terminal_status": "CONTINUE"},
                ]
            },
            run_root=run_root,
            betting_day=betting_day,
            run_id=run_id,
            expected_artifact_type="S3_DEEP_STATS",
        )

    # 12. Proof that no fixed event ID exists in production paths
    fixed_id = "evt_649a5f6cc3964ae76d3d614b517f2a82"
    with pytest.raises(ValueError, match="EVENT_BOUNDARY_UNKNOWN_EVENT"):
        strict_validate_step_output(
            step_id="S3",
            output_path=valid_file,
            output_data={
                "artifact_type": "S3_DEEP_STATS",
                "betting_day": betting_day,
                "run_id": run_id,
                "event_records": [
                    {"canonical_event_id": "evt-1", "terminal_status": "CONTINUE"},
                    {"canonical_event_id": "evt-2", "terminal_status": "CONTINUE"},
                    {"canonical_event_id": fixed_id, "terminal_status": "CONTINUE"},
                ]
            },
            run_root=run_root,
            betting_day=betting_day,
            run_id=run_id,
            expected_artifact_type="S3_DEEP_STATS",
        )
