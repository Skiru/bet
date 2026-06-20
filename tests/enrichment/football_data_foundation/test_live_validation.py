from __future__ import annotations

import json
from pathlib import Path
import pytest

from bet.enrichment.football_data_foundation.live_validation import run_live_validation


def test_live_validation_runs_successfully(tmp_path: Path) -> None:
    # Run the live validation session program
    # Note: run_live_validation performs a real fetch from ESPN, but if it fails
    # it is robust and will output a validation_manifest.json with live source unavailable
    # or it will fetch successfully and create all expected artifacts.
    output_dir = tmp_path / "live_validation_test_output"
    
    try:
        run_live_validation(str(output_dir))
    except SystemExit as e:
        # A SystemExit is raised (with exit code 1) if live source is completely unavailable,
        # which is allowed. We check that in both cases, the scoreboard snapshot file is created.
        assert e.code == 1

    # In either case (fetched successfully or source unavailable), we expect
    # provider_scoreboard_snapshot.json to exist.
    assert (output_dir / "provider_scoreboard_snapshot.json").exists()

    # If the fetch succeeded, let's check all artifacts exist and are non-empty
    if (output_dir / "validation_manifest.json").exists():
        assert (output_dir / "provider_scoreboard_snapshot.md").exists()
        assert (output_dir / "scanner_event_batch.json").exists()
        assert (output_dir / "scanner_event_batch.md").exists()
        assert (output_dir / "out_of_window_events.json").exists()
        assert (output_dir / "event_enrichment_results.json").exists()
        assert (output_dir / "freshness_results.json").exists()
        assert (output_dir / "canonical_mapping_results.json").exists()
        assert (output_dir / "observation_projection_export.json").exists()
        assert (output_dir / "temp_sqlite_snapshot.json").exists()
        assert (output_dir / "validation_summary.md").exists()

        # Let's verify manifest is a valid JSON
        manifest_data = json.loads((output_dir / "validation_manifest.json").read_text(encoding="utf-8"))
        assert manifest_data["phase_id"] == "FOOTBALL_DATA_FOUNDATION_L1_SCANNER_WINDOW_LIVE_VALIDATION_WORLD_CUP_2026_NO_ACTIVATION"
        assert manifest_data["no_real_db_write"] is True
