from __future__ import annotations

from pathlib import Path

from bet.enrichment.football_data_foundation.certification.final_gate import (
    certify_shadow_football_enrichment,
)
from bet.enrichment.football_data_foundation.fixture_context.loader import (
    load_fixture_context_fixture,
)
from bet.enrichment.football_data_foundation.fusion.fuser import ShadowFactFuser
from bet.enrichment.football_data_foundation.shadow_artifacts.writer import (
    write_shadow_fusion_artifacts,
)


def test_canary_pipeline_offline(tmp_path: Path) -> None:
    # 1. World Cup 2026 canary scenario (offline)
    wc_path = Path(
        "tests/fixtures/enrichment/football_data_foundation/master_final/worldcup_2026_shadow_fixture.json"
    )
    wc_claims = load_fixture_context_fixture(wc_path)

    wc_summary = ShadowFactFuser().fuse(wc_claims)
    assert wc_summary is not None
    assert not wc_summary.conflicts
    assert wc_summary.selectable_for_production is False
    assert wc_summary.manual_authorization_required is True

    json_path_wc, md_path_wc = write_shadow_fusion_artifacts(
        wc_summary, tmp_path, "worldcup_2026_canary"
    )

    wc_certification = certify_shadow_football_enrichment(
        wc_summary, [json_path_wc, md_path_wc]
    )
    assert wc_certification.status == "SHADOW_READY_FOR_MANUAL_REVIEW"
    assert wc_certification.selectable_for_production is False
    assert wc_certification.manual_authorization_required is True

    # 2. Generic club fixture canary scenario (offline)
    club_path = Path(
        "tests/fixtures/enrichment/football_data_foundation/master_final/generic_club_shadow_fixture.json"
    )
    club_claims = load_fixture_context_fixture(club_path)

    club_summary = ShadowFactFuser().fuse(club_claims)
    assert club_summary is not None
    assert not club_summary.conflicts
    assert club_summary.selectable_for_production is False
    assert club_summary.manual_authorization_required is True

    json_path_club, md_path_club = write_shadow_fusion_artifacts(
        club_summary, tmp_path, "generic_club_canary"
    )

    club_certification = certify_shadow_football_enrichment(
        club_summary, [json_path_club, md_path_club]
    )
    assert club_certification.status == "SHADOW_READY_FOR_MANUAL_REVIEW"
    assert club_certification.selectable_for_production is False
    assert club_certification.manual_authorization_required is True
