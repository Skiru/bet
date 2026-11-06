"""The staged football / tennis calibration
(config/sofa_confidence_calibration.next.json) is read INSTEAD of the
installed file from its `effective_from` (confidence.calibration_path_for).
So it must be complete: every key path of the installed file exists in it,
and every key it did not refit - live-only strips, score slices, class
curves, pools, metadata - is the installed file's, byte for byte. Only the
(section, key) pairs named in `staged_change.refitted_keys` may differ
(coordinator 2026-11-06, refit replay 2026-11-05)."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import confidence

ROOT = Path(__file__).resolve().parents[2]
INSTALLED = ROOT / "config" / "sofa_confidence_calibration.json"
STAGED = ROOT / "config" / confidence.NEXT_CALIBRATION_NAME
STAGED_ONLY = {"effective_from", "staged_change"}


Paths = set[tuple[str, ...]]


def _changed(staged: dict[str, Any]) -> tuple[Paths, Paths]:
    change = staged["staged_change"]
    return ({tuple(k) for k in change["refitted_keys"]},
            {tuple(k) for k in change.get("added_keys", [])})


def _paths(node: Any, stop: set[tuple[str, ...]],
           prefix: tuple[str, ...] = ()) -> set[tuple[str, ...]]:
    """Every key path, not descending into a refitted curve (its buckets may differ)."""
    if isinstance(node, dict) and prefix not in stop:
        out: set[tuple[str, ...]] = {prefix} if prefix else set()
        for k, v in node.items():
            out |= _paths(v, stop, (*prefix, str(k)))
        return out
    return {prefix}


def _load() -> tuple[dict[str, Any], dict[str, Any]]:
    if not STAGED.exists():
        pytest.skip("no staged football / tennis calibration")
    return (json.loads(INSTALLED.read_text(encoding="utf-8")),
            json.loads(STAGED.read_text(encoding="utf-8")))


def _get(doc: Any, path: tuple[str, ...]) -> Any:
    for p in path:
        doc = doc[p]
    return doc


def test_every_key_path_of_the_installed_file_is_in_the_staged_one() -> None:
    installed, staged = _load()
    refitted, _ = _changed(staged)
    missing = sorted(_paths(installed, refitted) - _paths(staged, refitted))
    assert not missing, missing[:20]
    assert set(staged) - set(installed) == STAGED_ONLY


def _compare(inst: Any, stag: Any, path: tuple[str, ...],
             refitted: set[tuple[str, ...]], added: set[tuple[str, ...]]) -> None:
    if path in refitted:
        return
    if isinstance(inst, dict) and isinstance(stag, dict) and any(
            r[:len(path)] == path for r in refitted | added):
        extra = {k for k in stag if (*path, k) not in added}
        assert extra == set(inst), (path, sorted(extra ^ set(inst))[:10])
        for k, v in inst.items():
            _compare(v, stag[k], (*path, k), refitted, added)
        return
    assert json.dumps(stag, sort_keys=True) == json.dumps(inst, sort_keys=True), path


def test_keys_not_refitted_are_the_installed_ones_byte_for_byte() -> None:
    installed, staged = _load()
    refitted, added = _changed(staged)
    assert refitted or added, "a staged file that changes nothing should not exist"
    body = {k: v for k, v in staged.items() if k not in STAGED_ONLY}
    _compare(installed, body, (), refitted, added)
    for path in refitted:
        assert _get(staged, path) != _get(installed, path), path
    for path in added:
        with pytest.raises(KeyError):
            _get(installed, path)
        _get(staged, path)


def test_the_staged_file_loads_and_names_its_start() -> None:
    _, staged = _load()
    start = datetime.fromisoformat(staged["effective_from"].replace("Z", "+00:00"))
    assert start.hour == 0 and start.minute == 0
    assert staged["staged_change"]["effective_from"] == staged["effective_from"]
    confidence.Calibration.load(STAGED)


def _stage(tmp_path: Path, effective_from: str) -> Path:
    main = tmp_path / "sofa_confidence_calibration.json"
    main.write_text(json.dumps({"pooled": {}}), encoding="utf-8")
    (tmp_path / confidence.NEXT_CALIBRATION_NAME).write_text(
        json.dumps({"effective_from": effective_from, "pooled": {}}), encoding="utf-8")
    return main


def test_11_06_reads_the_installed_file_at_any_clock_and_11_07_the_staged_one(
        tmp_path: Path) -> None:
    main = _stage(tmp_path, "2026-11-07T00:00:00Z")
    nxt = main.with_name(confidence.NEXT_CALIBRATION_NAME)
    for at in (datetime(2026, 11, 6, 0, 0, tzinfo=UTC),
               datetime(2026, 11, 6, 23, 59, tzinfo=UTC),
               # a rebuild of 11-06 the next morning
               datetime(2026, 11, 7, 6, 0, tzinfo=UTC),
               datetime(2026, 11, 9, 12, 0, tzinfo=UTC)):
        assert confidence.calibration_path_for("2026-11-06", at, main) == main
    assert confidence.calibration_path_for(
        "2026-11-07", datetime(2026, 11, 7, 0, 0, tzinfo=UTC), main) == nxt
    assert confidence.calibration_path_for(
        "2026-11-07", datetime(2026, 11, 6, 23, 59, tzinfo=UTC), main) == main
    assert confidence.calibration_path_for(
        "2026-11-08", datetime(2026, 11, 8, 5, 0, tzinfo=UTC), main) == nxt

