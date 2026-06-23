from pathlib import Path
from unittest.mock import patch

import pytest

from bet.enrichment.football_data_foundation.source_bound_activation.facade import (
    build_football_source_bound_activation_candidate,
)
from tests.enrichment.football_data_foundation.test_source_bound_activation_loader import create_mock_bundle


def test_facade_returns_activation_candidate_shadow_only(tmp_path: Path) -> None:
    paths = create_mock_bundle(tmp_path)
    candidate = build_football_source_bound_activation_candidate(
        project_root=tmp_path,
        fixture_slug="worldcup2026-norway-senegal",
    )
    assert candidate.decision.status == "ACTIVATION_CANDIDATE_SHADOW_ONLY"
    assert candidate.decision.selectable_for_production is False
    assert candidate.decision.manual_authorization_required is True
    assert candidate.decision.production_db_write_allowed is False
    assert candidate.decision.betting_decision_allowed is False
    assert candidate.decision.live_network_allowed is False


def test_facade_performs_no_writes(tmp_path: Path) -> None:
    paths = create_mock_bundle(tmp_path)
    
    # We patch Path.write_text, Path.write_bytes, Path.mkdir, open to ensure no writes occur during facade invocation
    with patch.object(Path, "write_text") as mock_write_text, \
         patch.object(Path, "write_bytes") as mock_write_bytes, \
         patch.object(Path, "mkdir") as mock_mkdir:
         
        candidate = build_football_source_bound_activation_candidate(
            project_root=tmp_path,
            fixture_slug="worldcup2026-norway-senegal",
        )
        assert candidate is not None
        
        # Verify no write/mkdir methods were called
        mock_write_text.assert_not_called()
        mock_write_bytes.assert_not_called()
        mock_mkdir.assert_not_called()
