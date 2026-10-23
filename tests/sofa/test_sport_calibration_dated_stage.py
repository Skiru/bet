"""The dated chain of staged sport calibrations
(sport_confidence.calibration_path_for): a day reads the staged file with the
latest `effective_from` at or before it - .next.json (10-14) for 10-14..10-23,
.next.2026-10-24.json from 10-24 - and a day already built never moves."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bet.sofa import sport_confidence as scf


def _doc(path: Path, eff: str | None) -> None:
    doc: dict[str, object] = {"sports": {}}
    if eff is not None:
        doc["effective_from"] = eff
    path.write_text(json.dumps(doc), encoding="utf-8")


def _config(tmp_path: Path) -> Path:
    _doc(tmp_path / scf.CALIBRATION_FILE, None)
    _doc(tmp_path / scf.NEXT_CALIBRATION_FILE, "2026-10-14")
    _doc(tmp_path / "sofa_sport_confidence_calibration.next.2026-10-24.json",
         "2026-10-24")
    return tmp_path


@pytest.mark.parametrize(("day", "name"), [
    ("2026-10-13", scf.CALIBRATION_FILE),
    ("2026-10-14", scf.NEXT_CALIBRATION_FILE),
    ("2026-10-22", scf.NEXT_CALIBRATION_FILE),
    ("2026-10-23", scf.NEXT_CALIBRATION_FILE),
    ("2026-10-24", "sofa_sport_confidence_calibration.next.2026-10-24.json"),
    ("2026-11-30", "sofa_sport_confidence_calibration.next.2026-10-24.json"),
])
def test_chain_picks_latest_effective(tmp_path: Path, day: str, name: str) -> None:
    assert scf.calibration_path_for(day, _config(tmp_path)).name == name


def test_without_dated_file_unchanged(tmp_path: Path) -> None:
    _doc(tmp_path / scf.CALIBRATION_FILE, None)
    _doc(tmp_path / scf.NEXT_CALIBRATION_FILE, "2026-10-14")
    assert scf.calibration_path_for(
        "2026-10-13", tmp_path).name == scf.CALIBRATION_FILE
    assert scf.calibration_path_for(
        "2026-12-01", tmp_path).name == scf.NEXT_CALIBRATION_FILE


def test_dated_file_without_next(tmp_path: Path) -> None:
    _doc(tmp_path / scf.CALIBRATION_FILE, None)
    _doc(tmp_path / "sofa_sport_confidence_calibration.next.2026-10-24.json",
         "2026-10-24")
    assert scf.calibration_path_for("2026-10-23", tmp_path).name == scf.CALIBRATION_FILE
    assert scf.calibration_path_for("2026-10-24", tmp_path).name.endswith(
        ".next.2026-10-24.json")


def test_name_and_effective_from_must_agree(tmp_path: Path) -> None:
    _doc(tmp_path / scf.CALIBRATION_FILE, None)
    _doc(tmp_path / "sofa_sport_confidence_calibration.next.2026-10-24.json",
         "2026-10-23")
    with pytest.raises(ValueError):
        scf.calibration_path_for("2026-10-24", tmp_path)


def test_other_names_ignored(tmp_path: Path) -> None:
    _config(tmp_path)
    _doc(tmp_path / "sofa_sport_confidence_calibration.next.backup.json", "2026-10-20")
    assert scf.calibration_path_for(
        "2026-10-21", tmp_path).name == scf.NEXT_CALIBRATION_FILE


def test_is_staged_calibration() -> None:
    assert scf.is_staged_calibration(Path(scf.NEXT_CALIBRATION_FILE))
    assert scf.is_staged_calibration(
        Path("sofa_sport_confidence_calibration.next.2026-10-24.json"))
    assert not scf.is_staged_calibration(Path(scf.CALIBRATION_FILE))


DATED_1024 = "sofa_sport_confidence_calibration.next.2026-10-24.json"


def test_installed_config_built_days_keep_their_file() -> None:
    """The repository's config: 10-14..10-23 (built) read .next.json, the
    file they read before the dated chain; 10-24 reads the hockey refit."""
    for day in ("2026-10-14", "2026-10-22", "2026-10-23"):
        assert scf.calibration_path_for(day).name == scf.NEXT_CALIBRATION_FILE
    assert scf.calibration_path_for("2026-10-13").name == scf.CALIBRATION_FILE
    assert scf.calibration_path_for("2026-10-24").name == DATED_1024


def test_dated_1024_changes_hockey_only() -> None:
    """The 2026-10-24 file is .next.json with the hockey section refitted
    (REFIT_HOKEJ_SIATKOWKA_2026-10-23.md); every other sport identical."""
    nxt = json.loads(scf.calibration_path_for("2026-10-23").read_text(encoding="utf-8"))
    new = json.loads(scf.calibration_path_for("2026-10-24").read_text(encoding="utf-8"))
    assert new["effective_from"] == "2026-10-24"
    assert nxt["effective_from"] == "2026-10-14"
    for sport in ("basketball", "volleyball", "cs2"):
        assert new["sports"][sport] == nxt["sports"][sport]
    assert new["sports"]["hockey"] != nxt["sports"]["hockey"]
    assert new["sports"]["hockey"]["fitted_from"]["before"] == "2026-10-23"
    assert new["sports"]["hockey"]["fitted_from"]["league_rate_rule"] is True
    assert "league_season_restart" not in new["sports"]["hockey"]["fitted_from"]
    carried = {k for k in new["new_market_curves_fitted_from"]
               if k.startswith("hockey:")}
    assert carried <= {"hockey:" + k for k in new["sports"]["hockey"]["curves"]}
