"""S1e event-universe and end-to-end accounting contracts."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from bet.pipeline.event_accounting import (
    BOUNDARY_DEFAULT_STATUS,
    EventAccountingError,
    EventAccountingLedger,
    deduplicate_events,
)
from scripts.pipeline_steps import s1e_event_ledger

DAY = "2026-07-13"
RUN_ID = "event-accounting-test"


def _events() -> list[dict]:
    return [
        {"fixture_id": "football-1", "sport": "football", "home_team": "A", "away_team": "B", "kickoff": "2026-07-13T12:00:00Z"},
        {"fixture_id": "tennis-1", "sport": "tennis", "home_team": "C", "away_team": "D", "kickoff": "2026-07-13T14:00:00Z"},
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
    assert universe["source_s1_sha256"]


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
    ledger = _initialized_ledger(tmp_path, _events())
    for step, status in BOUNDARY_DEFAULT_STATUS.items():
        payload = ledger.record_boundary(step, default_status=status)
        assert payload["after_dedup_count"] == payload["events_with_terminal_status"] == 2
        assert payload["unaccounted_event_ids"] == []
    assert "TIPSTER_EVIDENCE_RECORDED_OR_MISSING_EXPLICIT" in str(payload["boundaries"])
    assert "PRICED_OR_PRICE_PENDING" in str(payload["boundaries"])


def test_event_loss_and_unknown_event_fail_closed(tmp_path: Path):
    ledger = _initialized_ledger(tmp_path, _events())
    with pytest.raises(EventAccountingError, match="EVENT_BOUNDARY_LOSS"):
        ledger.record_boundary(
            "S2",
            records=[{"canonical_event_id": "football-1", "terminal_status": "TIPSTER_MISSING"}],
            default_status="unused",
        )
    with pytest.raises(EventAccountingError, match="UNKNOWN_EVENT"):
        ledger.record_boundary(
            "S2",
            records=[
                {"canonical_event_id": "football-1", "terminal_status": "PASS"},
                {"canonical_event_id": "unknown", "terminal_status": "PASS"},
            ],
            default_status="unused",
        )


def test_one_event_with_multiple_markets_is_one_fixture_account(tmp_path: Path):
    ledger = _initialized_ledger(tmp_path, [_events()[0]])
    payload = ledger.record_boundary(
        "S8",
        records=[
            {"canonical_event_id": "football-1", "terminal_status": "MARKET_A_QUOTE_CARD"},
            {"canonical_event_id": "football-1", "terminal_status": "MARKET_B_QUOTE_CARD"},
        ],
        default_status="unused",
    )
    assert payload["after_dedup_count"] == payload["events_with_terminal_status"] == 1
    assert len(payload["boundaries"]["S8"]["football-1"]["terminal_statuses"]) == 2
