from __future__ import annotations

import json
from pathlib import Path

import pytest

from bet.enrichment.football_data_foundation.certification.final_gate import (
    certify_shadow_football_enrichment,
)
from bet.enrichment.football_data_foundation.fixture_context.loader import (
    load_fixture_context_fixture,
)
from bet.enrichment.football_data_foundation.fusion.fuser import ShadowFactFuser
from bet.enrichment.football_data_foundation.shadow_artifacts.writer import (
    ShadowArtifactWriter,
    write_shadow_fusion_artifacts,
)


def test_artifact_json_and_markdown_properties(tmp_path: Path) -> None:
    fixture_path = Path(
        "tests/fixtures/enrichment/football_data_foundation/master_final/generic_club_shadow_fixture.json"
    )
    claims = load_fixture_context_fixture(fixture_path)
    summary = ShadowFactFuser().fuse(claims)

    json_path, md_path = write_shadow_fusion_artifacts(
        summary, tmp_path, "generic_club_match"
    )

    # Assert JSON property requirements
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert "fused_facts" in data
    for fact in data["fused_facts"]:
        assert "identity_key" in fact
        assert "primary_source_key" in fact
        assert "supporting_source_keys" in fact
        assert "confidence" in fact
        assert fact["selectable_for_production"] is False

    # Assert Markdown property requirements
    md_text = md_path.read_text(encoding="utf-8")
    assert "Identity Key" in md_text
    assert "Primary Source" in md_text
    assert "Supporting Sources" in md_text
    assert "Confidence" in md_text
    assert "Selectable for Production: False" in md_text


def test_artifact_writer_rejects_forbidden_markers(tmp_path: Path) -> None:
    writer = ShadowArtifactWriter()

    # Rejects api_key, secret, token, raw_payload, response_body, PRODUCTION_READY
    with pytest.raises(ValueError, match="forbidden production marker"):
        writer.write_text(
            tmp_path / "f1.txt", "This system status is PRODUCTION_READY now."
        )

    with pytest.raises(ValueError, match="secret-like marker"):
        writer.write_json(tmp_path / "f2.json", {"SPORTDB_API_KEY": "secret-val"})


def test_certification_blocks_conflict_and_missing_facts(tmp_path: Path) -> None:
    # 1. Clean run -> SHADOW_READY_FOR_MANUAL_REVIEW
    fixture_path = Path(
        "tests/fixtures/enrichment/football_data_foundation/master_final/generic_club_shadow_fixture.json"
    )
    claims = load_fixture_context_fixture(fixture_path)
    summary_clean = ShadowFactFuser().fuse(claims)

    json_path, md_path = write_shadow_fusion_artifacts(
        summary_clean, tmp_path, "generic_club_match"
    )

    result_clean = certify_shadow_football_enrichment(
        summary_clean, [json_path, md_path]
    )
    assert result_clean.status == "SHADOW_READY_FOR_MANUAL_REVIEW"
    assert result_clean.selectable_for_production is False
    assert result_clean.manual_authorization_required is True
    assert not result_clean.blockers

    # 2. Conflicting run -> SHADOW_BLOCKED_FOR_MANUAL_REVIEW
    conflict_path = Path(
        "tests/fixtures/enrichment/football_data_foundation/master_final/current_score_conflict_fixture.json"
    )
    claims_conflict = load_fixture_context_fixture(conflict_path)
    summary_conflict = ShadowFactFuser().fuse(claims_conflict)

    # We write conflict summary to dummy artifact
    # Wait, the summary contains conflicts, let's write it to a clean path
    json_path_conf, md_path_conf = write_shadow_fusion_artifacts(
        summary_conflict, tmp_path, "conflict_match"
    )

    result_conflict = certify_shadow_football_enrichment(
        summary_conflict, [json_path_conf, md_path_conf]
    )
    assert result_conflict.status == "SHADOW_BLOCKED_FOR_MANUAL_REVIEW"
    assert any("Fusion conflict in SCORE" in b for b in result_conflict.blockers)

    # 3. Missing required facts -> SHADOW_BLOCKED_FOR_MANUAL_REVIEW
    missing_path = Path(
        "tests/fixtures/enrichment/football_data_foundation/master_final/missing_required_fact_fixture.json"
    )
    claims_missing = load_fixture_context_fixture(missing_path)
    summary_missing = ShadowFactFuser().fuse(claims_missing)

    json_path_miss, md_path_miss = write_shadow_fusion_artifacts(
        summary_missing, tmp_path, "missing_match"
    )

    result_missing = certify_shadow_football_enrichment(
        summary_missing, [json_path_miss, md_path_miss]
    )
    assert result_missing.status == "SHADOW_BLOCKED_FOR_MANUAL_REVIEW"
    assert any(
        "Required fact type missing from fusion: SCORE" in b
        for b in result_missing.blockers
    )
