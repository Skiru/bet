"""Test suite for completed work reuse defects (B18)."""

from pathlib import Path
import pytest


def test_b18_completed_work_reuse_trusts_weak_db_presence(tmp_path):
    """B18: completed-work reuse trusts weak database presence instead of artifact, receipt and input-fingerprint validity."""
    try:
        from bet.pipeline.launch_bridge import check_stage_work_reuse
        
        missing_art = tmp_path / "missing_art.json"
        
        # Calling production stage work reuse function with missing artifact
        reusable = check_stage_work_reuse(
            canonical_event_id="evt_100",
            stage_id="S2",
            db_status="PASS",
            expected_input_fingerprint="fp_1",
            artifact_path=missing_art,
        )
        assert not reusable, "B18 defect: production work reuse accepted missing artifact based on DB row alone"
    except (ImportError, AttributeError):
        pytest.fail("B18 defect: check_stage_work_reuse missing in production launch_bridge", pytrace=False)
