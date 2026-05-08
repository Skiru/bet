"""Tests for data rotation script."""
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from data_rotation import (
    _is_protected,
    _extract_date,
    find_old_files,
    PROTECTED_FILES,
    ROTATABLE_PATTERNS,
)


# ---------------------------------------------------------------------------
# Protected files
# ---------------------------------------------------------------------------


def test_protected_files_not_deleted():
    """Protected patterns are never in the deletion list."""
    tmp = tempfile.mkdtemp()
    data_dir = Path(tmp)

    # Create protected files with old dates in their names
    old_date = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")
    for protected in PROTECTED_FILES:
        (data_dir / protected).write_text("{}")

    # Create a rotatable file that looks old
    old_file = data_dir / f"market_matrix_{old_date}.json"
    old_file.write_text("{}")

    with patch("data_rotation.DATA_DIR", data_dir):
        old_files = find_old_files(days=30)

    old_names = {f.name for f in old_files}
    for protected in PROTECTED_FILES:
        assert protected not in old_names, f"Protected file {protected} found in deletion list"


# ---------------------------------------------------------------------------
# Date extraction
# ---------------------------------------------------------------------------


def test_old_files_detected():
    """Files with old dates are found."""
    tmp = tempfile.mkdtemp()
    data_dir = Path(tmp)

    old_date = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")
    recent_date = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")

    old_file = data_dir / f"market_matrix_{old_date}.json"
    old_file.write_text("{}")
    recent_file = data_dir / f"market_matrix_{recent_date}.json"
    recent_file.write_text("{}")

    with patch("data_rotation.DATA_DIR", data_dir):
        old_files = find_old_files(days=30)

    old_names = {f.name for f in old_files}
    assert old_file.name in old_names
    assert recent_file.name not in old_names

    import shutil
    shutil.rmtree(tmp)


def test_extract_date_formats():
    """Date extraction works for YYYY-MM-DD and YYYYMMDD formats."""
    assert _extract_date("market_matrix_2026-05-01.json") is not None
    assert _extract_date("market_matrix_2026-05-01.json").strftime("%Y-%m-%d") == "2026-05-01"

    assert _extract_date("20260501_s2_shortlist.json") is not None
    assert _extract_date("20260501_s2_shortlist.json").strftime("%Y-%m-%d") == "2026-05-01"

    assert _extract_date("no_date_here.json") is None


# ---------------------------------------------------------------------------
# Dry run safety
# ---------------------------------------------------------------------------


def test_dry_run_doesnt_delete():
    """Dry run mode doesn't actually remove files."""
    tmp = tempfile.mkdtemp()
    data_dir = Path(tmp)

    old_date = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")
    old_file = data_dir / f"market_matrix_{old_date}.json"
    old_file.write_text("{}")

    with patch("data_rotation.DATA_DIR", data_dir):
        old_files = find_old_files(days=30)

    # find_old_files only identifies, doesn't delete
    assert len(old_files) > 0
    assert old_file.exists(), "File should still exist after find_old_files (dry run)"

    import shutil
    shutil.rmtree(tmp)
