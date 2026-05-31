"""Tests for StructuredOutput."""

import json
from pathlib import Path

import pytest

from bet.pipeline.structured_output import StructuredOutput


@pytest.fixture(autouse=True)
def use_tmp_data(tmp_path, monkeypatch):
    """Redirect DATA_DIR to tmp."""
    import bet.pipeline.structured_output as mod
    monkeypatch.setattr(mod, "DATA_DIR", tmp_path)
    return tmp_path


def test_basic_write(use_tmp_data):
    out = StructuredOutput(step="S3", date="2026-05-30")
    out.add_candidate(fixture_id=123, data={"sport": "football", "market": "corners"})
    out.add_candidate(fixture_id=456, data={"sport": "tennis", "market": "games"})
    path = out.finalize(summary={"total": 2, "with_data": 2})

    assert path.exists()
    data = json.loads(path.read_text())
    assert data["step"] == "S3"
    assert data["date"] == "2026-05-30"
    assert len(data["candidates"]) == 2
    assert data["candidates"][0]["fixture_id"] == 123
    assert data["summary"]["total"] == 2


def test_load_roundtrip(use_tmp_data):
    out = StructuredOutput(step="S7", date="2026-05-30")
    out.add_candidate(fixture_id=1, data={"gate_score": 15})
    out.finalize(summary={"approved": 1})

    loaded = StructuredOutput.load("S7", "2026-05-30")
    assert loaded["step"] == "S7"
    assert loaded["candidates"][0]["gate_score"] == 15


def test_load_missing_raises(use_tmp_data):
    with pytest.raises(FileNotFoundError, match="No structured output"):
        StructuredOutput.load("S99", "2026-01-01")


def test_envelope_fields(use_tmp_data):
    out = StructuredOutput(step="S1e", date="2026-06-01")
    path = out.finalize()
    data = json.loads(path.read_text())
    assert "generated_at" in data
    assert data["candidates"] == []
    assert data["summary"] == {}


def test_filename_convention(use_tmp_data):
    out = StructuredOutput(step="S2.9", date="2026-05-30")
    path = out.finalize()
    assert path.name == "2026-05-30_s2.9_structured.json"


def test_path_traversal_rejected():
    """Date with path separators must be rejected (security)."""
    with pytest.raises(ValueError, match="Invalid date"):
        StructuredOutput(step="S3", date="../../etc")


def test_empty_summary_preserved(use_tmp_data):
    """Empty dict summary should be stored (not treated as falsy)."""
    out = StructuredOutput(step="S1", date="2026-06-01")
    out.finalize(summary={})
    loaded = StructuredOutput.load("S1", "2026-06-01")
    assert loaded["summary"] == {}
