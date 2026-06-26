"""Focused S7b child-script evidence tests."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

import scripts.validate_betclic_markets as validate_betclic_markets


class _FakeResult:
    def __init__(self, event_name: str = "Alpha vs Beta"):
        self.event_name = event_name

    def to_dict(self) -> dict:
        return {"event_name": self.event_name}


class _PassChecker:
    def __init__(self, betting_date: str, db_conn=None):
        self.results = [_FakeResult()]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def scan_all_sports(self, sports=None, max_events_per_sport=0):
        return None

    def save_to_db(self):
        raise AssertionError("save_to_db should not run in non-production")

    def build_summary(self):
        return {
            "total_events": 1,
            "with_statistics_tab": 1,
            "without_statistics_tab": 0,
            "competitions_with_stats": [],
            "competitions_without_stats": [],
        }

    def validate_picks(self, picks):
        return [{**pick, "betclic_available": True, "betclic_note": "ok", "betclic_open_markets": 5} for pick in picks]


def _runtime_environ(tmp_path: Path, mode: str = "LIVE_SHADOW") -> dict[str, str]:
    run_root = Path("/tmp") / f"bet-s7b-script-{tmp_path.name}"
    env = {
        "BET_PIPELINE_RUNTIME_MODE": mode,
        "BET_PIPELINE_BETTING_DAY": "2026-06-25",
        "BET_PIPELINE_RUN_ID": "run-s7b-script",
        "BET_PIPELINE_RUN_ROOT": str(run_root),
        "BET_PIPELINE_DATA_DIR": str(run_root / "data"),
        "BET_PIPELINE_COUPON_DIR": str(run_root / "coupons"),
        "BET_PIPELINE_ARTIFACT_DIR": str(run_root / "artifacts"),
    }
    if mode == "LIVE_SHADOW":
        env["BET_PIPELINE_LIVE_ACK"] = "I_UNDERSTAND_LIVE_PROVIDER_CALLS"
    return env


def _canonical_evidence_path(environ: dict[str, str]) -> Path:
    return (
        Path(environ["BET_PIPELINE_RUN_ROOT"])
        / "pipeline_runs"
        / environ["BET_PIPELINE_BETTING_DAY"]
        / environ["BET_PIPELINE_RUN_ID"]
        / "artifacts"
        / "S7b.json"
    )


def _write_gate_input(tmp_path: Path) -> Path:
    input_path = tmp_path / "s7_input.json"
    input_path.write_text(
        json.dumps(
            {
                "gate_results": {
                    "approved": [
                        {
                            "sport": "football",
                            "home_team": "Alpha",
                            "away_team": "Beta",
                            "best_market": {"name": "Over 2.5", "market_type": "goals_total", "direction": "OVER"},
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    return input_path


def test_validate_betclic_markets_accepts_explicit_input_and_passes(tmp_path: Path):
    environ = _runtime_environ(tmp_path, mode="LIVE_SHADOW")
    input_path = _write_gate_input(tmp_path)
    argv = ["validate_betclic_markets.py", "--date", "2026-06-25", "--input", str(input_path), "--allow-live-network", "--no-db"]

    with patch.dict(os.environ, environ, clear=False), patch.object(sys, "argv", argv), patch.object(validate_betclic_markets, "BetclicMarketChecker", _PassChecker):
        with pytest.raises(SystemExit) as exc_info:
            validate_betclic_markets.main()

    assert exc_info.value.code == 0
    output_path = Path(environ["BET_PIPELINE_DATA_DIR"]) / "betclic_market_validation_2026-06-25.json"
    assert output_path.exists()
    evidence = json.loads(_canonical_evidence_path(environ).read_text(encoding="utf-8"))
    assert evidence["status"] == "PASS"
    assert evidence["payload"]["s7b_input_path"] == str(input_path)
    assert evidence["payload"]["s7b_json_output"] == str(output_path)
    assert evidence["payload"]["checked_market_count"] == 1
    assert evidence["payload"]["available_market_count"] == 1
    assert evidence["payload"]["unavailable_market_count"] == 0
    assert evidence["payload"]["validation_status"] == "PASS"


def test_validate_betclic_markets_blocks_without_live_scan_permission(tmp_path: Path):
    environ = _runtime_environ(tmp_path, mode="DRY_RUN")
    input_path = _write_gate_input(tmp_path)
    argv = ["validate_betclic_markets.py", "--date", "2026-06-25", "--input", str(input_path), "--no-db"]

    with patch.dict(os.environ, environ, clear=False), patch.object(sys, "argv", argv), patch.object(validate_betclic_markets, "BetclicMarketChecker", _PassChecker):
        with pytest.raises(SystemExit) as exc_info:
            validate_betclic_markets.main()

    assert exc_info.value.code == 2
    evidence = json.loads(_canonical_evidence_path(environ).read_text(encoding="utf-8"))
    assert evidence["status"] == "BLOCK"
    assert evidence["payload"]["validation_status"] == "BLOCK"


def test_validate_betclic_markets_rejects_protected_output_path(tmp_path: Path):
    environ = _runtime_environ(tmp_path, mode="DRY_RUN")
    environ["BET_PIPELINE_DATA_DIR"] = str(Path(__file__).resolve().parents[1] / "betting" / "data")
    input_path = _write_gate_input(tmp_path)
    argv = ["validate_betclic_markets.py", "--date", "2026-06-25", "--input", str(input_path), "--no-db"]

    with patch.dict(os.environ, environ, clear=False), patch.object(sys, "argv", argv):
        with pytest.raises(SystemExit) as exc_info:
            validate_betclic_markets.main()

    assert exc_info.value.code == 5
