"""Focused repeat guard handoff tests for S6 check_48h_repeats.py."""
from __future__ import annotations

import csv
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts import check_48h_repeats
from datetime import datetime as real_datetime


class FixedRepeatGuardDatetime(real_datetime):
    @classmethod
    def now(cls, tz=None):
        base = cls(2026, 6, 26, 12, 0, 0)
        if tz is not None:
            return base.replace(tzinfo=tz)
        return base


@pytest.fixture
def ledger_empty(tmp_path: Path) -> Path:
    path = tmp_path / "picks-ledger.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["betting_day", "pick_id", "event", "sport", "market", "selection", "status"])
    return path


@pytest.fixture
def ledger_with_recent_loss(tmp_path: Path) -> Path:
    path = tmp_path / "picks-ledger.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["betting_day", "pick_id", "event", "sport", "market", "selection", "status"])
        writer.writerow(["2026-06-25", "P-101", "Norway vs France", "football", "Over 2.5", "Over 2.5", "loss"])
    return path


def test_extract_candidates_various_formats():
    # 1. List of dicts
    payload_list = [{"home_team": "A", "away_team": "B", "market": "O2.5"}]
    extracted = check_48h_repeats._extract_gate_candidates(payload_list)
    assert len(extracted) == 1
    assert extracted[0]["home_team"] == "A"

    # 2. candidates bucket
    payload_candidates = {"candidates": [{"home_team": "C", "away_team": "D"}]}
    extracted = check_48h_repeats._extract_gate_candidates(payload_candidates)
    assert len(extracted) == 1
    assert extracted[0]["home_team"] == "C"

    # 3. gate_results buckets
    payload_gate = {
        "gate_results": {
            "approved": [{"home_team": "E", "away_team": "F"}],
            "extended_pool": [{"home_team": "G", "away_team": "H"}]
        }
    }
    extracted = check_48h_repeats._extract_gate_candidates(payload_gate)
    assert len(extracted) == 2
    assert extracted[0]["home_team"] == "E"
    assert extracted[1]["home_team"] == "G"

    # 4. valuations bucket
    payload_vals = {"valuations": [{"home_team": "I", "away_team": "J"}]}
    extracted = check_48h_repeats._extract_gate_candidates(payload_vals)
    assert len(extracted) == 1
    assert extracted[0]["home_team"] == "I"

    # 5. analyses bucket
    payload_analyses = {"analyses": [{"home_team": "K", "away_team": "L"}]}
    extracted = check_48h_repeats._extract_gate_candidates(payload_analyses)
    assert len(extracted) == 1
    assert extracted[0]["home_team"] == "K"

    # 6. Nested S4/S5 payload
    payload_nested = {
        "payload": {
            "candidates": [{"home_team": "M", "away_team": "N"}]
        }
    }
    extracted = check_48h_repeats._extract_gate_candidates(payload_nested)
    assert len(extracted) == 1
    assert extracted[0]["home_team"] == "M"

    # 7. Empty list should raise ValueError
    with pytest.raises(ValueError, match="zero candidates"):
        check_48h_repeats._extract_gate_candidates([])


def test_check_repeats_rejects_protected_path(tmp_path: Path):
    repo_data_path = Path(__file__).resolve().parents[1] / "betting" / "data" / "some_input.json"

    with patch.dict(os.environ, {"BET_PIPELINE_RUNTIME_MODE": "DRY_RUN"}, clear=False), \
         patch.object(sys, "argv", ["check_48h_repeats.py", "--date", "2026-06-25", "--input", str(repo_data_path)]), \
         pytest.raises(SystemExit) as exc_info:
        check_48h_repeats.main()

    assert exc_info.value.code == 5


def test_check_repeats_empty_input_blocks(tmp_path: Path, ledger_empty: Path):
    input_file = tmp_path / "empty_input.json"
    input_file.write_text(json.dumps({"candidates": []}), encoding="utf-8")

    with patch.dict(os.environ, {"BET_PIPELINE_RUNTIME_MODE": "DRY_RUN"}, clear=False), \
         patch.object(check_48h_repeats, "_record_pipeline_start"), \
         patch.object(check_48h_repeats, "_persist_pipeline_handoff"), \
         patch.object(sys, "argv", [
             "check_48h_repeats.py",
             "--date", "2026-06-25",
             "--input", str(input_file),
             "--output", str(tmp_path / "out.json"),
             "--ledger", str(ledger_empty)
         ]), \
         pytest.raises(SystemExit) as exc_info:
        check_48h_repeats.main()

    assert exc_info.value.code == 5


def test_check_repeats_repeat_loss_conflict_blocks(tmp_path: Path, ledger_with_recent_loss: Path):
    input_file = tmp_path / "candidates.json"
    input_file.write_text(json.dumps({
        "candidates": [
            {
                "fixture_id": 1,
                "sport": "football",
                "home_team": "Norway",
                "away_team": "France",
                "market": "Over 2.5",
                "best_market": {"name": "Over 2.5"}
            }
        ]
    }), encoding="utf-8")

    # We mock _persist_pipeline_handoff and _record_pipeline_start as they call DB
    with patch.dict(os.environ, {"BET_PIPELINE_RUNTIME_MODE": "DRY_RUN"}, clear=False), \
         patch.object(check_48h_repeats, "_record_pipeline_start"), \
         patch.object(check_48h_repeats, "_persist_pipeline_handoff"), \
         patch.object(check_48h_repeats, "datetime", FixedRepeatGuardDatetime), \
         patch.object(sys, "argv", [
             "check_48h_repeats.py",
             "--date", "2026-06-25",
             "--input", str(input_file),
             "--output", str(tmp_path / "out.json"),
             "--ledger", str(ledger_with_recent_loss)
         ]), \
         pytest.raises(SystemExit) as exc_info:
        check_48h_repeats.main()

    assert exc_info.value.code == 1


def test_check_repeats_pass_with_zero_losses(tmp_path: Path, ledger_empty: Path):
    input_file = tmp_path / "candidates.json"
    input_file.write_text(json.dumps({
        "candidates": [
            {
                "fixture_id": 1,
                "sport": "football",
                "home_team": "Norway",
                "away_team": "France",
                "market": "Over 2.5",
                "best_market": {"name": "Over 2.5"}
            }
        ]
    }), encoding="utf-8")

    with patch.dict(os.environ, {"BET_PIPELINE_RUNTIME_MODE": "DRY_RUN"}, clear=False), \
         patch.object(check_48h_repeats, "_record_pipeline_start"), \
         patch.object(check_48h_repeats, "_persist_pipeline_handoff"), \
         patch.object(sys, "argv", [
             "check_48h_repeats.py",
             "--date", "2026-06-25",
             "--input", str(input_file),
             "--output", str(tmp_path / "out.json"),
             "--ledger", str(ledger_empty)
         ]), \
         pytest.raises(SystemExit) as exc_info:
        check_48h_repeats.main()

    assert exc_info.value.code == 0


def test_load_recent_losses_uses_repeat_guard_clock_deterministically(tmp_path: Path, ledger_with_recent_loss: Path):
    with patch.object(check_48h_repeats, "datetime", FixedRepeatGuardDatetime):
        losses = check_48h_repeats.load_recent_losses(ledger_with_recent_loss, hours=48)
        assert len(losses) == 1
        assert losses[0]["pick_id"] == "P-101"

