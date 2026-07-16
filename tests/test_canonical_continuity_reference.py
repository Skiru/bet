from __future__ import annotations

import hashlib
import json
import multiprocessing
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from bet.pipeline.artifact_io import (
    ArtifactPublishError,
    publish_immutable_json_blob,
)
from bet.pipeline.canonical_continuity import (
    ContinuityContractError,
    bind_candidate_identity,
    validate_exact_partition,
)
from bet.pipeline.command_registry import CommandRequestError, resolve_command_request
from bet.pipeline.hard_approval_gate import evaluate_s7_hard_gate
from bet.pipeline.live_fixture_audit import LiveFixtureAudit
from bet.pipeline.run_coordination import ResumeLedger, redact_sensitive_text
from bet.pipeline.runtime_paths import resolve_run_root
from scripts.check_48h_repeats import load_recent_losses_snapshot


DAY = "2026-07-15"
RUN_ID = "run-reference"
RUN_AS_OF = "2026-07-15T10:00:00Z"


def _candidate(*, kickoff: str = "2026-07-15T18:00:00Z", selection: str = "Over", line: float = 2.5) -> dict:
    raw = {
        "sport": "football",
        "competition": "Reference League",
        "home_team": "Alpha FC",
        "away_team": "Beta SC",
        "kickoff": kickoff,
        "market_family": "GOALS_TOTALS",
        "market_type": "Match goals",
        "selection": selection,
        "direction": selection,
        "line": line,
        "period": "full_time",
        "analytical_status": "ANALYTICAL_READY",
        "pricing_status": "PRICED",
        "odds_decimal": 1.91,
        "probability_as_of": "2026-07-15T09:30:00Z",
        "context_checks": {
            name: {
                "status": "CLEAR",
                "as_of_utc": "2026-07-15T09:30:00Z",
                "source_refs": [f"source:{name}"],
            }
            for name in (
                "injuries_lineups",
                "motivation_tournament_context",
                "travel_fatigue",
                "morale_recent_form",
                "upset_volatility_risk",
            )
        },
        "risk_flags": [],
        "counter_evidence": [],
    }
    bound = bind_candidate_identity(raw)
    bound["fixture_verification"] = {
        "status": "LIVE_FIXTURE_VERIFIED_NOT_STARTED",
        "source": "provider-fixture-snapshot",
        "verified_at_utc": "2026-07-15T09:45:00Z",
        "canonical_event_id": bound["canonical_event_id"],
    }
    return bound


def _s6(candidate: dict, *, accepted: bool = True) -> dict:
    source_s5 = Path(__file__).resolve()
    source_s5_sha = hashlib.sha256(source_s5.read_bytes()).hexdigest()
    record = {
        "candidate_id": candidate["selection_id"],
        "decision": "ACCEPTED" if accepted else "REJECTED",
        "reason_codes": [] if accepted else ["PORTFOLIO_CONCENTRATION"],
        "original_candidate": candidate,
    }
    return {
        "schema_version": 2,
        "artifact_type": "S6_PORTFOLIO_REPEAT_GUARD_V2",
        "status": "PASS",
        "concrete_status": "READY_FOR_S7" if accepted else "NO_ACTION_TERMINAL",
        "betting_day": DAY,
        "run_id": RUN_ID,
        "source_step": "S5",
        "source_s5_path": str(source_s5),
        "source_s5_sha256": source_s5_sha,
        "worker_contract_version": "1.0",
        "run_as_of_utc": RUN_AS_OF,
        "validated_inputs": {
            "s5_hash": source_s5_sha,
            "history_hash": "1" * 64,
            "policy_hash": "2" * 64,
        },
        "input_candidate_count": 1,
        "accepted": [record] if accepted else [],
        "repeat_rejected": [],
        "duplicate_rejected": [],
        "conflict_rejected": [],
        "correlation_rejected": [],
        "concentration_rejected": [] if accepted else [record],
        "invalid_input": [],
    }


def _exclusive_writer(run_root: str, target: str, payload: dict, barrier, queue) -> None:
    barrier.wait()
    try:
        receipt = publish_immutable_json_blob(
            run_root=Path(run_root), target=Path(target), payload=payload
        )
        queue.put(("reuse" if receipt.already_present else "create", payload["writer"]))
    except ArtifactPublishError as exc:
        queue.put((exc.code, payload["writer"]))


def test_identity_distinguishes_kickoff_selection_and_numeric_line() -> None:
    first = _candidate()
    later = _candidate(kickoff="2026-07-15T21:00:00Z")
    under = _candidate(selection="Under")
    equivalent_line = _candidate(line=2.500)
    assert first["canonical_event_id"] != later["canonical_event_id"]
    assert first["selection_id"] != under["selection_id"]
    assert first["selection_id"] == equivalent_line["selection_id"]


def test_existing_canonical_identity_is_verified_not_trusted() -> None:
    candidate = _candidate()
    candidate["canonical_event_id"] = "evt_forged"
    with pytest.raises(ContinuityContractError, match="CANONICAL_EVENT_ID_MISMATCH"):
        bind_candidate_identity(candidate)


def test_partition_rejects_missing_overlap_and_unexpected_ids() -> None:
    first = _candidate()
    second = _candidate(selection="Under")
    with pytest.raises(ContinuityContractError, match="CANDIDATE_PARTITION_MISMATCH"):
        validate_exact_partition(
            [first, second], {"approved": [first], "rejected": [first]}
        )


def test_hard_gate_preserves_selection_and_removes_execution_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BET_PIPELINE_RUN_AS_OF_UTC", RUN_AS_OF)
    candidate = _candidate()
    candidate["stake"] = 100
    source = tmp_path / "s6.json"
    source.write_text(json.dumps(_s6(candidate)), encoding="utf-8")
    result = evaluate_s7_hard_gate(
        _s6(candidate), source_s6_path=source, betting_day=DAY, run_id=RUN_ID
    )
    approved = result["priced_approved"][0]
    assert approved["selection"] == "Over"
    assert approved["selection_id"] == candidate["selection_id"]
    assert "stake" not in approved
    assert result["outcome"] == "READY_FOR_PRICED_REVIEW"
    assert result["accounting"]["terminal_count"] == 1


def test_hard_gate_all_rejected_is_valid_no_action(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BET_PIPELINE_RUN_AS_OF_UTC", RUN_AS_OF)
    candidate = _candidate()
    candidate["context_checks"]["travel_fatigue"]["status"] = "BLOCK"
    source = tmp_path / "s6.json"
    source.write_text(json.dumps(_s6(candidate)), encoding="utf-8")
    result = evaluate_s7_hard_gate(
        _s6(candidate), source_s6_path=source, betting_day=DAY, run_id=RUN_ID
    )
    assert result["status"] == "PASS"
    assert result["outcome"] == "NO_ACTION_TERMINAL"
    assert result["rejected"][0]["candidate_id"] == candidate["selection_id"]


def test_hard_gate_blocks_tampered_source_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BET_PIPELINE_RUN_AS_OF_UTC", RUN_AS_OF)
    candidate = _candidate()
    source = tmp_path / "s6.json"
    source.write_text(json.dumps(_s6(candidate, accepted=False)), encoding="utf-8")
    with pytest.raises(ContinuityContractError, match="S6_HASH_CHANGED_DURING_READ"):
        evaluate_s7_hard_gate(
            _s6(candidate), source_s6_path=source, betting_day=DAY, run_id=RUN_ID
        )


def test_fixture_audit_uses_warsaw_day_and_requires_source_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BET_PIPELINE_RUN_AS_OF_UTC", "2026-03-28T22:00:00Z")
    candidate = _candidate(kickoff="2026-03-28T23:30:00Z")
    candidate["probability_as_of"] = "2026-03-28T21:30:00Z"
    candidate["fixture_verification"]["verified_at_utc"] = "2026-03-28T21:45:00Z"
    assert LiveFixtureAudit("2026-03-29").audit_candidate(candidate)[0] == "LIVE_FIXTURE_VERIFIED_NOT_STARTED"
    candidate.pop("fixture_verification")
    assert LiveFixtureAudit("2026-03-29").audit_candidate(candidate)[0] == "REJECTED_UNVERIFIED_FIXTURE_IDENTITY"


def test_history_window_is_exactly_start_inclusive_asof_exclusive(tmp_path: Path) -> None:
    as_of = datetime(2026, 7, 15, 10, tzinfo=UTC)
    start = as_of - timedelta(hours=48)
    ledger = tmp_path / "ledger.csv"
    ledger.write_text(
        "betting_day,pick_id,event,sport,market,selection,status,settled_at_utc\n"
        f"2026-07-13,start,A vs B,football,total,Over,loss,{start.isoformat()}\n"
        f"2026-07-15,end,A vs B,football,total,Over,loss,{as_of.isoformat()}\n",
        encoding="utf-8",
    )
    snapshot = load_recent_losses_snapshot(ledger, as_of=as_of)
    assert [record["pick_id"] for record in snapshot["records"]] == ["start"]


def test_immutable_publication_real_32_process_race(tmp_path: Path) -> None:
    run_root = tmp_path / DAY / RUN_ID
    run_root.mkdir(parents=True)
    target = run_root / "data" / "snapshot.json"
    context = multiprocessing.get_context("spawn")
    barrier = context.Barrier(32)
    queue = context.Queue()
    processes = [
        context.Process(
            target=_exclusive_writer,
            args=(str(run_root), str(target), {"writer": index}, barrier, queue),
        )
        for index in range(32)
    ]
    for process in processes:
        process.start()
    results = [queue.get(timeout=30) for _ in processes]
    for process in processes:
        process.join(timeout=30)
        assert process.exitcode == 0
    assert sum(kind == "create" for kind, _ in results) == 1
    assert sum(kind == "ARTIFACT_IMMUTABLE_CONFLICT" for kind, _ in results) == 31
    winning_writer = json.loads(target.read_text(encoding="utf-8"))["writer"]
    assert ("create", winning_writer) in results


@pytest.mark.parametrize(
    ("day", "run_id"),
    [("../../escape", "run"), (DAY, "/tmp/absolute"), (DAY, "../escape")],
)
def test_run_identifiers_block_traversal_before_creation(
    tmp_path: Path, day: str, run_id: str
) -> None:
    with pytest.raises(ValueError):
        resolve_run_root(day, run_id, tmp_path)


def test_resume_ledger_records_resolution_of_nonterminal_attempt(tmp_path: Path) -> None:
    run_root = tmp_path / DAY / RUN_ID
    run_root.mkdir(parents=True)
    ledger = ResumeLedger(
        run_root,
        run_id=RUN_ID,
        betting_day=DAY,
        main_sha="a" * 40,
        manifest_sha="b" * 64,
        run_as_of_utc=RUN_AS_OF,
    )
    blocked = ledger.append(
        step_id="S5",
        status="COMMAND_REQUEST_UNRESOLVED",
        command_request={"command_id": "WAIT_FOR_RATE_LIMIT", "parameters": {"seconds": 1}},
        input_hashes={"manifest": "b" * 64},
        output_hashes={},
    )
    passed = ledger.append(
        step_id="S5",
        status="PASS",
        command_request={"command_id": "WAIT_FOR_RATE_LIMIT", "parameters": {"seconds": 1}},
        input_hashes={"manifest": "b" * 64},
        output_hashes={"artifact": "c" * 64},
    )
    assert passed["resolution_of_attempt_id"] == blocked["attempt_id"]
    assert ledger._load()["unresolved_command_request"] is False


def test_command_registry_rejects_python_and_bounds_wait() -> None:
    with pytest.raises(CommandRequestError):
        resolve_command_request({"argv": ["python", "-c", "print('unsafe')"]})
    command = resolve_command_request(
        {"command_id": "WAIT_FOR_RATE_LIMIT", "parameters": {"seconds": 2}}
    )
    assert command.argv == ["/bin/sleep", "2"]
    with pytest.raises(CommandRequestError):
        resolve_command_request(
            {"command_id": "WAIT_FOR_RATE_LIMIT", "parameters": {"seconds": 31}}
        )


def test_output_redaction_and_bounding() -> None:
    secret = "super-secret-value"
    output = redact_sensitive_text(secret + "x" * 100, {"API_KEY": secret}, max_chars=20)
    assert secret not in output
    assert "OUTPUT_TRUNCATED" in output


def test_s6_worker_no_action_returns_process_success(tmp_path: Path) -> None:
    run_root = tmp_path / DAY / RUN_ID
    data = run_root / "data"
    artifacts = run_root / "artifacts"
    data.mkdir(parents=True)
    artifacts.mkdir()
    candidate = _candidate()
    s5 = artifacts / "S5.json"
    s5.write_text(json.dumps({"payload": {"candidates": [candidate]}}), encoding="utf-8")
    history = data / "history.json"
    records: list[dict] = []
    history.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "artifact_type": "S6_HISTORY_SNAPSHOT_V1",
                "as_of_utc": RUN_AS_OF,
                "lookback_start_utc": "2026-07-13T10:00:00Z",
                "boundary_policy": "[lookback_start_utc,as_of_utc)",
                "source_identity": "test-ledger",
                "opened_read_only": True,
                "query_version": "2.0",
                "policy_version": "test",
                "records": records,
                "row_count": 0,
                "snapshot_sha256": hashlib.sha256(json.dumps(records, sort_keys=True).encode()).hexdigest(),
            }
        ),
        encoding="utf-8",
    )
    policy = data / "policy.json"
    policy.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "policy_version": "test",
                "repeat_loss_lookback_hours": 48,
                "duplicate_signal_enabled": True,
                "same_event_conflict_enabled": True,
                "correlation_group_limit_enabled": True,
                "correlation_group_max_accepted": 3,
                "concentration_enabled": True,
                "per_event_limit": 0,
                "per_team_limit": 2,
                "per_competition_limit": 2,
                "per_sport_limit": 2,
            }
        ),
        encoding="utf-8",
    )
    output = data / "s6.json"
    file_hash = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    command = [
        sys.executable,
        str(Path(__file__).resolve().parents[1] / "scripts" / "check_48h_repeats.py"),
        "--date", DAY,
        "--run-id", RUN_ID,
        "--run-as-of-utc", RUN_AS_OF,
        "--validated-s5", str(s5),
        "--validated-s5-sha256", file_hash(s5),
        "--history-snapshot", str(history),
        "--history-snapshot-sha256", file_hash(history),
        "--policy-snapshot", str(policy),
        "--policy-snapshot-sha256", file_hash(policy),
        "--output", str(output),
        "--worker-contract-version", "1.0",
    ]
    env = os.environ.copy()
    env["BET_PIPELINE_RUN_ROOT"] = str(run_root)
    result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(output.read_text(encoding="utf-8"))["concrete_status"] == "NO_ACTION_TERMINAL"
