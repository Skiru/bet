"""run_confidence and build_coupon_pdf read and write where SOFA_RUNS_DIR says.

On 2026-09-23 both defaulted to a hard-coded ``runs/sofa`` while SHEET and
COUPON honoured SOFA_RUNS_DIR, so a rebuild of the day in a scratch directory
overwrote the real 08_confidence.json and KUPON pdf (restored from the
prev_1330 snapshot). A scratch run must never reach the real day.
"""

import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "module", ["scripts.sofa.run_confidence", "scripts.sofa.build_coupon_pdf"]
)
def test_the_default_runs_dir_is_sofa_runs_dir(
    module: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import importlib

    monkeypatch.setenv("SOFA_RUNS_DIR", str(tmp_path))
    monkeypatch.setattr(sys, "argv", ["x", "--date", "2026-01-01"])
    mod = importlib.import_module(module)
    with pytest.raises(FileNotFoundError) as err:
        mod.main()
    assert str(tmp_path) in str(err.value), "it read somewhere other than SOFA_RUNS_DIR"
