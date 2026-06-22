from __future__ import annotations

import json
import pytest
from pathlib import Path
from bet.enrichment.football_data_foundation.fixture_context.loader import load_fixture_context_fixture
from bet.enrichment.football_data_foundation.fusion.fuser import ShadowFactFuser
from bet.enrichment.football_data_foundation.shadow_artifacts.writer import (
    ShadowArtifactWriter,
    write_shadow_fusion_artifacts,
)


def test_shadow_artifacts_writer_success(tmp_path: Path) -> None:
    fixture_path = Path("tests/fixtures/enrichment/football_data_foundation/pass3/generic_club_match_shadow.json")
    claims = load_fixture_context_fixture(fixture_path)
    summary = ShadowFactFuser().fuse(claims)
    
    json_path, md_path = write_shadow_fusion_artifacts(summary, tmp_path, "generic_club_match")
    
    assert json_path.exists()
    assert md_path.exists()
    
    # Check deterministic sorted keys in JSON
    json_text = json_path.read_text(encoding="utf-8")
    parsed = json.loads(json_text)
    assert parsed["run_id"] == summary.run_id
    assert parsed["manual_authorization_required"] is True
    assert parsed["selectable_for_production"] is False
    
    # Check Markdown formatting
    md_text = md_path.read_text(encoding="utf-8")
    assert "Fixture Slug: generic_club_match" in md_text
    assert f"Run ID: {summary.run_id}" in md_text
    assert "Manual Authorization Required: True" in md_text


def test_shadow_artifacts_writer_blocks_forbidden_keys(tmp_path: Path) -> None:
    writer = ShadowArtifactWriter()
    
    # Blocks secret markers
    with pytest.raises(ValueError, match="secret-like marker"):
        writer.write_json(tmp_path / "secret.json", {"api_key": "some-value"})
        
    with pytest.raises(ValueError, match="secret-like marker"):
        writer.write_text(tmp_path / "secret.md", "Authorization: Bearer xyz")
        
    # Blocks raw payload markers
    with pytest.raises(ValueError, match="raw-payload-like marker"):
        writer.write_json(tmp_path / "raw.json", {"raw_payload": "some-raw-data"})
        
    with pytest.raises(ValueError, match="raw-payload-like marker"):
        writer.write_text(tmp_path / "raw.md", "This has response_body content here.")


def test_shadow_artifacts_writer_blocks_betting_data(tmp_path: Path) -> None:
    writer = ShadowArtifactWriter()
    
    # Blocks writing to betting/data
    bad_path = Path("betting/data/test.json")
    with pytest.raises(ValueError, match="shadow writer must never write to betting/data"):
        writer.write_json(bad_path, {"test": 1})

# Line-endings normalization proof
