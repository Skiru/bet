"""Review 2026-10-27 T-BO5: the tennis rating's calibration population, and
the dated staged calibration SHEET reads from its day.

fit_coefficients dropped a best-of-five match by its outcome (len(sets) <= 3
kept a 3-0, dropped a 3-1 / 3-2). It now fits best-of-three only
(tennis_rating.best_of); the legacy population stays for measurement. A
refitted calibration is staged as config/tennis_rating.next.<d>.json and read
by SHEET from that day (params_path_for), and sheet_config hashes the file the
day reads.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from bet.sofa import sheet_config
from bet.sofa import tennis_rating as tr


def _r(sets: tuple[tuple[int, int], ...], home_won: bool, eid: int = 1,
       tier: str = "TOUR") -> tr.TennisResult:
    return tr.TennisResult(eid, 0, tier, "hard", 1, 2, home_won, sets, None, True)


def test_best_of_reads_the_winners_sets() -> None:
    assert tr.best_of(_r(((6, 3), (6, 4)), True)) == 3
    assert tr.best_of(_r(((3, 6), (6, 4), (1, 0)), True)) == 3  # match tiebreak
    assert tr.best_of(_r(((6, 3), (6, 4), (6, 2)), True)) == 5
    assert tr.best_of(_r(((6, 3), (4, 6), (6, 4), (6, 2)), True)) == 5
    assert tr.best_of(_r(((6, 3), (4, 6), (3, 6), (6, 4), (7, 5)), True)) == 5
    assert tr.best_of(_r(((6, 3),), True)) is None


def _rows() -> list[tuple[tr.TennisResult, dict[str, float]]]:
    feats = {name: 0.0 for name in tr.FEATURES}
    out = []
    shapes = [((6, 3), (6, 4)), ((3, 6), (6, 4), (6, 2)),
              ((6, 3), (6, 4), (6, 2)),                  # BO5 3-0
              ((6, 3), (4, 6), (6, 4), (6, 2)),          # BO5 3-1
              ((6, 3), (4, 6), (3, 6), (6, 4), (7, 5))]  # BO5 3-2
    for i, sets in enumerate(shapes):
        f = dict(feats, lp=0.1 * (i - 2))
        out.append((_r(sets, i % 2 == 0, eid=i), f))
    return out


def test_fit_drops_every_best_of_five_and_legacy_keeps_the_straight_sets(
        monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, int] = {}

    def fake(xs: list[list[float]], ys: list[float]) -> list[float]:
        seen["n"] = len(xs)
        return [0.0] * (len(xs[0]) + 1)

    monkeypatch.setattr(tr, "fit_logistic", fake)
    new = tr.fit_coefficients(_rows())
    assert new["TOUR"]["n"] == 2 and seen["n"] == 2
    legacy = tr.fit_coefficients(_rows(), legacy_set_filter=True)
    # the outcome-selected population: both BO3 and the BO5 3-0 only
    assert legacy["TOUR"]["n"] == 3


def _write(path: Path, doc: dict[str, object]) -> None:
    path.write_text(json.dumps(doc), encoding="utf-8")


def test_params_path_for_reads_a_staged_file_from_its_day(tmp_path: Path) -> None:
    main = tmp_path / "tennis_rating.json"
    _write(main, {"features": ["lp"], "tiers": {}})
    staged = tmp_path / "tennis_rating.next.2026-10-28.json"
    _write(staged, {"effective_from": "2026-10-28", "features": ["lp"],
                    "tiers": {}})
    on = datetime(2026, 10, 28, 6, tzinfo=UTC)
    before = datetime(2026, 10, 27, 22, tzinfo=UTC)
    assert tr.params_path_for("2026-10-28", on, tmp_path) == staged
    # a 10-28 sheet built on 10-27 still reads the installed file
    assert tr.params_path_for("2026-10-28", before, tmp_path) == main
    # a built day never reads it
    assert tr.params_path_for("2026-10-27", on, tmp_path) == main
    _write(tmp_path / "tennis_rating.next.2026-10-29.json",
           {"effective_from": "2026-10-28"})
    with pytest.raises(ValueError):
        tr.params_path_for("2026-10-29", on, tmp_path)


def test_fingerprint_hashes_the_file_the_day_reads(tmp_path: Path) -> None:
    _write(tmp_path / "tennis_rating.json", {"features": ["lp"], "tiers": {}})
    undated = sheet_config.fingerprint(tmp_path)
    on = datetime(2026, 10, 28, 6, tzinfo=UTC)
    # no staged file: dated and undated agree
    assert sheet_config.fingerprint(tmp_path, "2026-10-28", on) == undated
    _write(tmp_path / "tennis_rating.next.2026-10-28.json",
           {"effective_from": "2026-10-28", "features": ["lp"], "tiers": {"X": 1}})
    assert sheet_config.fingerprint(tmp_path) == undated
    assert sheet_config.fingerprint(tmp_path, "2026-10-27", on) == undated
    assert sheet_config.fingerprint(tmp_path, "2026-10-28", on) != undated


def test_installed_config_reads_today() -> None:
    """No staged tennis file reaches a day before 2026-10-28."""
    path = tr.params_path_for("2026-10-27", datetime(2026, 10, 27, 21, tzinfo=UTC))
    assert path.name == "tennis_rating.json"
