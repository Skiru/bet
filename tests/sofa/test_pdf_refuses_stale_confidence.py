"""The PDF is the coupon: it must not print CONFIDENCE's legs from before the
latest SHEET (review 2026-09-29)."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from typing import Any

SCRIPT = Path(__file__).parents[2] / "scripts" / "sofa" / "build_coupon_pdf.py"


def _module() -> Any:
    spec = importlib.util.spec_from_file_location("build_coupon_pdf", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_confidence_older_than_the_sheet_refuses(tmp_path: Path) -> None:
    pdf = _module()
    (tmp_path / "05_sheet.json").write_text("[]")
    (tmp_path / "08_confidence.json").write_text("{}")
    os.utime(tmp_path / "08_confidence.json", (1_000, 1_000))
    os.utime(tmp_path / "05_sheet.json", (2_000, 2_000))
    msg = pdf.confidence_older_than_sheet(tmp_path, "08_confidence.json")
    assert msg and msg.startswith("STALE_CONFIDENCE")


def test_confidence_after_the_sheet_is_fine(tmp_path: Path) -> None:
    pdf = _module()
    (tmp_path / "05_sheet.json").write_text("[]")
    (tmp_path / "08_confidence_wariant.json").write_text("{}")
    os.utime(tmp_path / "05_sheet.json", (1_000, 1_000))
    os.utime(tmp_path / "08_confidence_wariant.json", (2_000, 2_000))
    assert (
        pdf.confidence_older_than_sheet(tmp_path, "08_confidence_wariant.json") is None
    )
    # A missing file is the main() path's own error, not this check's.
    assert pdf.confidence_older_than_sheet(tmp_path, "08_confidence.json") is None
