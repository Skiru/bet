from __future__ import annotations

import subprocess


def test_pass_b_helpers_remain_importable() -> None:
    # Verify we can import the required helper functions from the package
    from bet.enrichment.multisport_foundation import (
        verify_plan,
        verify_source_inventory,
        verify_shadow_artifacts,
    )
    assert verify_plan is not None
    assert verify_source_inventory is not None
    assert verify_shadow_artifacts is not None


def test_pass_b_report_remains_unchanged() -> None:
    # Use git status or git diff to verify reports/multisport_foundation/pass_b/source_bound_shadow_status_by_sport.json is unchanged
    path = "reports/multisport_foundation/pass_b/source_bound_shadow_status_by_sport.json"
    result = subprocess.run(
        ["git", "diff", "--name-only", path],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "", f"File {path} was unexpectedly modified!"
