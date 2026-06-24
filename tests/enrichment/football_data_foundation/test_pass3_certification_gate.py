from __future__ import annotations

from pathlib import Path
from bet.enrichment.football_data_foundation.certification.final_gate import (
    certify_shadow_football_enrichment,
)
from bet.enrichment.football_data_foundation.fixture_context.loader import (
    load_fixture_context_fixture,
)
from bet.enrichment.football_data_foundation.fusion.fuser import ShadowFactFuser


def test_certification_gate_success(tmp_path: Path) -> None:
    fixture_path = Path(
        "tests/fixtures/enrichment/football_data_foundation/pass3/generic_club_match_shadow.json"
    )
    claims = load_fixture_context_fixture(fixture_path)
    summary = ShadowFactFuser().fuse(claims)

    # Let's create dummy artifact files
    art1 = tmp_path / "f1.json"
    art2 = tmp_path / "f1.md"
    art1.write_text("{}", encoding="utf-8")
    art2.write_text("Report", encoding="utf-8")

    result = certify_shadow_football_enrichment(summary, [art1, art2])

    assert result.status == "SHADOW_READY_FOR_MANUAL_REVIEW"
    assert result.selectable_for_production is False
    assert result.manual_authorization_required is True
    assert not result.blockers


def test_certification_gate_missing_artifacts(tmp_path: Path) -> None:
    fixture_path = Path(
        "tests/fixtures/enrichment/football_data_foundation/pass3/generic_club_match_shadow.json"
    )
    claims = load_fixture_context_fixture(fixture_path)
    summary = ShadowFactFuser().fuse(claims)

    # Missing artifacts
    result = certify_shadow_football_enrichment(
        summary, [tmp_path / "nonexistent.json"]
    )

    assert result.status == "SHADOW_BLOCKED_FOR_MANUAL_REVIEW"
    assert any("Artifact does not exist" in b for b in result.blockers)


def test_certification_gate_conflicts(tmp_path: Path) -> None:
    fixture_path = Path(
        "tests/fixtures/enrichment/football_data_foundation/pass3/conflicting_current_status_shadow.json"
    )
    claims = load_fixture_context_fixture(fixture_path)
    summary = ShadowFactFuser().fuse(claims)

    art1 = tmp_path / "f1.json"
    art1.write_text("{}", encoding="utf-8")

    result = certify_shadow_football_enrichment(summary, [art1])

    assert result.status == "SHADOW_BLOCKED_FOR_MANUAL_REVIEW"
    assert any("Fusion conflict in MATCH_STATUS" in b for b in result.blockers)


def test_certification_gate_missing_required_facts(tmp_path: Path) -> None:
    # Let's fuse incomplete claims (e.g. missing SCORE)
    fixture_path = Path(
        "tests/fixtures/enrichment/football_data_foundation/pass3/generic_club_match_shadow.json"
    )
    claims = list(load_fixture_context_fixture(fixture_path))

    # Exclude SCORE claim
    incomplete_claims = [c for c in claims if c.fact_type != "SCORE"]

    summary = ShadowFactFuser().fuse(incomplete_claims)

    art1 = tmp_path / "f1.json"
    art1.write_text("{}", encoding="utf-8")

    result = certify_shadow_football_enrichment(summary, [art1])

    assert result.status == "SHADOW_BLOCKED_FOR_MANUAL_REVIEW"
    assert any(
        "Required fact type missing from fusion: SCORE" in b for b in result.blockers
    )
