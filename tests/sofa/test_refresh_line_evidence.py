"""scripts/sofa/refresh_line_evidence.py - the morning refresh of the line evidence."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _mod():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location(
        "refresh_line_evidence", REPO / "scripts/sofa/refresh_line_evidence.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["refresh_line_evidence"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_the_sport_fits_never_install_curves(tmp_path: Path) -> None:
    mod = _mod()
    cmds = mod.fit_commands("2026-10-08", tmp_path)
    assert [c[3] for c in cmds] == ["hockey", "basketball", "volleyball", "cs2"]
    for c in cmds:
        assert "--dry-run" in c and "--rows-out" in c
        # --out points into the rows directory, never config/
        assert c[c.index("--out") + 1].startswith(str(tmp_path))


def test_a_failed_sport_keeps_the_newest_earlier_rows(  # type: ignore[no-untyped-def]
        tmp_path: Path, monkeypatch) -> None:
    mod = _mod()
    monkeypatch.setattr(mod, "ROWS_ROOT", tmp_path)
    for d in ("2026-10-06", "2026-10-07", "2026-10-09"):
        (tmp_path / f"rows_before_{d}").mkdir()
    assert mod.previous_rows("2026-10-08").name == "rows_before_2026-10-07"
    assert mod.previous_rows("2026-10-06") is None
