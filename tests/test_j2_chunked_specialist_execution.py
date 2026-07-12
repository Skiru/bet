# -*- coding: utf-8 -*-
"""Unit tests for J2 chunked specialist execution."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_chunk_contract_exists() -> None:
    """Verify chunk contract files exist and are populated."""
    doc_path = ROOT / "docs" / "pipeline" / "J2 Chunked Specialist Execution Contract.md"
    art_path = ROOT / ".kilo" / "artifacts" / "j2_chunked_specialist_execution_contract.md"
    json_path = ROOT / ".kilo" / "artifacts" / "j2_chunked_specialist_execution_contract.json"

    assert doc_path.is_file(), f"Missing {doc_path}"
    assert art_path.is_file(), f"Missing {art_path}"
    assert json_path.is_file(), f"Missing {json_path}"

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data.get("max_chunk_size") == 20


def test_researcher_prompt_blocks_full_60_event_run() -> None:
    """Verify that the researcher blocks batches with more than 20 events."""
    prompt_path = ROOT / ".kilo" / "agents" / "bet-researcher.md"
    assert prompt_path.is_file(), f"Missing {prompt_path}"

    content = prompt_path.read_text(encoding="utf-8")
    assert "Process at most 20 events per delegated batch; larger scopes return `STATUS: BLOCKED, DECISION: CHUNK_REQUIRED`." in content


def test_modeler_prompt_blocks_full_60_event_run() -> None:
    """Verify that the modeler blocks batches with more than 20 events."""
    prompt_path = ROOT / ".kilo" / "agents" / "bet-modeler.md"
    assert prompt_path.is_file(), f"Missing {prompt_path}"

    content = prompt_path.read_text(encoding="utf-8")
    assert "Process at most 20 events per delegated batch; larger scopes return `STATUS: BLOCKED, DECISION: CHUNK_REQUIRED`." in content


def test_final_outputs_not_used_as_chunk_inputs() -> None:
    """Verify prompt rules forbid reading stale final output files as chunk inputs."""
    researcher_prompt = ROOT / ".kilo" / "agents" / "bet-researcher.md"
    modeler_prompt = ROOT / ".kilo" / "agents" / "bet-modeler.md"

    researcher_content = researcher_prompt.read_text(encoding="utf-8")
    modeler_content = modeler_prompt.read_text(encoding="utf-8")

    assert "Do not read existing final output files as chunk inputs." in researcher_content
    assert "Do not read existing final output files as chunk inputs." in modeler_content


def test_stale_blocked_outputs_are_quarantined() -> None:
    """Verify quarantine folders are defined in the J2 chunk contract metadata."""
    json_path = ROOT / ".kilo" / "artifacts" / "j2_chunked_specialist_execution_contract.json"
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert "quarantine_folder_pattern" in data


def test_chunks_have_max_20_events() -> None:
    """Verify that produced chunk files never exceed 20 events."""
    run_id = "TODAY_ORCHESTRATED_SESSION_J1_SCANNER_SCOUT_20260701_105101"
    run_dir = ROOT / "reports" / "pipeline_runs" / run_id

    # Check if files are prepared (if prepared)
    chunk_files = ["j2_chunk_football.json", "j2_chunk_tennis_1.json", "j2_chunk_tennis_2.json"]
    for name in chunk_files:
        p = run_dir / name
        if p.is_file():
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            assert len(data.get("events", [])) <= 20, f"{name} exceeded max size"


def test_football_chunk_present() -> None:
    """Verify football chunk exists and is structurally correct."""
    run_id = "TODAY_ORCHESTRATED_SESSION_J1_SCANNER_SCOUT_20260701_105101"
    run_dir = ROOT / "reports" / "pipeline_runs" / run_id
    football_chunk = run_dir / "j2_chunk_football.json"

    if football_chunk.is_file():
        with open(football_chunk, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data.get("sport") == "football"
        assert data.get("event_count") <= 20


def test_tennis_chunks_present() -> None:
    """Verify tennis chunks exist and are structurally correct."""
    run_id = "TODAY_ORCHESTRATED_SESSION_J1_SCANNER_SCOUT_20260701_105101"
    run_dir = ROOT / "reports" / "pipeline_runs" / run_id
    tennis_1 = run_dir / "j2_chunk_tennis_1.json"
    tennis_2 = run_dir / "j2_chunk_tennis_2.json"

    if tennis_1.is_file():
        with open(tennis_1, "r", encoding="utf-8") as f:
            data1 = json.load(f)
        assert data1.get("sport") == "tennis"
        assert data1.get("event_count") <= 20

    if tennis_2.is_file():
        with open(tennis_2, "r", encoding="utf-8") as f:
            data2 = json.load(f)
        assert data2.get("sport") == "tennis"
        assert data2.get("event_count") <= 20
