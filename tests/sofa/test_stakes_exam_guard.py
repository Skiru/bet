"""Guards of the pre-registered stakes exams (scripts/sofa/stakes_exam_guard.py
and their use in scripts/sofa/measure_stakes_exam.py), after the 2026-11-18
deviations: the replay completion marker (A1), G1 by commit (A2) and the seal
of the exam outcome files (A3); plus the study switch's S5 / P2 rules.
Offline: tmp dirs, tiny fake files, a throwaway git repo."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

from scripts.sofa import measure_stakes_exam as mse
from scripts.sofa import stakes_exam_guard as guard


@pytest.fixture(autouse=True)
def _football_study() -> Iterator[None]:
    yield
    mse.configure("football")
    mse._UNSEALER.clear()
    mse._POP.clear()


def _chunk(run: Path, rel: str, data: bytes = b"x") -> Path:
    p = run / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return p


# --- A1: replay completion -------------------------------------------------
def test_done_marker_is_refused_for_a_failed_replay(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        guard.write_done(tmp_path, -15, {})
    assert not (tmp_path / guard.DONE_NAME).exists()


def test_replay_without_marker_or_run_is_a_problem(tmp_path: Path) -> None:
    full = tmp_path / "full"
    assert guard.replay_problems(full) == [f"no replay run under {full}"]
    _chunk(full / "all", "dev/rows/2025-01_000.pkl.gz")
    assert "no DONE.json" in guard.replay_problems(full)[0]


def test_clean_marker_passes_and_a_later_chunk_breaks_it(tmp_path: Path) -> None:
    run = tmp_path / "full" / "all"
    _chunk(run, "dev/rows/2025-01_000.pkl.gz")
    _chunk(run, "exam_y/y/2026-01_000.pkl.gz")
    doc = guard.write_done(run, 0, {"records": 2})
    assert doc["files"] == [
        ["dev/rows/2025-01_000.pkl.gz", 1],
        ["exam_y/y/2026-01_000.pkl.gz", 1],
    ]
    assert guard.replay_problems(tmp_path / "full") == []
    _chunk(run, "dev/rows/2025-02_000.pkl.gz")
    assert "differ" in guard.replay_problems(tmp_path / "full")[0]


def test_marker_with_nonzero_rc_is_a_problem(tmp_path: Path) -> None:
    run = tmp_path / "full" / "c1"
    _chunk(run, "dev/y/2025-01_000.pkl.gz")
    (run / guard.DONE_NAME).write_text(
        json.dumps({"rc": 1, "finished_utc": "x", "files": guard.chunk_listing(run)})
    )
    assert guard.replay_problems(tmp_path / "full") == ["c1: rc 1"]


def test_exam_stages_refuse_an_unfinished_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mse, "SCRATCH", tmp_path)
    _chunk(tmp_path / "full" / "all", "dev/rows/2025-01_000.pkl.gz")
    for stage in ("load", "explore", "validate", "power", "submit", "exam"):
        with pytest.raises(SystemExit, match="replay not complete"):
            mse.main([stage])
    with pytest.raises(SystemExit, match="replay not complete"):
        mse.main(["freeze", "--spec-sha", "abc"])


# --- A2: G1 by commit ------------------------------------------------------
def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", *args],
        cwd=repo, check=True, capture_output=True,
    )


def test_uncommitted_lists_untracked_modified_and_staged(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-q")
    a, b, c, d = (tmp_path / n for n in ("a.json", "b.json", "c.json", "d.json"))
    for p in (a, b, c):
        p.write_text("1")
    _git(tmp_path, "add", "a.json", "b.json", "c.json")
    _git(tmp_path, "commit", "-qm", "x")
    b.write_text("2")
    c.write_text("3")
    _git(tmp_path, "add", "c.json")
    d.write_text("4")
    assert guard.uncommitted(tmp_path, [a, b, c, d]) == [
        "b.json: differs from HEAD",
        "c.json: differs from HEAD",
        "d.json: not committed",
    ]


def test_exam_preflight_refuses_uncommitted_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _git(tmp_path, "init", "-q")
    mse.configure("dead_goals")
    monkeypatch.setattr(mse, "REPO", tmp_path)
    monkeypatch.setattr(mse, "check_guards", lambda s: {"coefficients": "h"})
    monkeypatch.setattr(guard, "seal_problems", lambda *a: [])
    with pytest.raises(SystemExit, match="refused \\(exam\\).*not committed"):
        mse.exam_preflight("abc")


# --- A3: the seal ----------------------------------------------------------
def test_seal_hashes_streams_chmods_and_lists(tmp_path: Path) -> None:
    f = _chunk(tmp_path, "exam_y/fr_y.pkl", b"outcome bytes" * 1000)
    manifest = tmp_path / guard.MANIFEST_NAME
    added = guard.seal([f], tmp_path, manifest)
    assert stat.S_IMODE(f.stat().st_mode) == 0
    (e,) = added
    assert e["path"] == "exam_y/fr_y.pkl"
    assert e["size"] == 13000
    assert e["sha256"] == hashlib.sha256(b"outcome bytes" * 1000).hexdigest()
    assert {"sealed_utc", "atime_before_seal_utc"} <= set(e)
    assert guard.seal([f], tmp_path, manifest) == []  # already sealed: kept
    assert guard.seal_problems(tmp_path, manifest, ("exam_y/*",)) == []
    os.chmod(f, 0o600)


def test_seal_problems_catch_a_broken_seal_and_an_unsealed_file(
    tmp_path: Path,
) -> None:
    f = _chunk(tmp_path, "exam_y/fr_y.pkl")
    manifest = tmp_path / guard.MANIFEST_NAME
    assert guard.seal_problems(tmp_path, manifest, ("exam_y/*",)) == [
        f"no seal manifest at {manifest}"
    ]
    guard.seal([f], tmp_path, manifest)
    _chunk(tmp_path, "exam_y/late.pkl")
    os.chmod(f, 0o644)
    probs = guard.seal_problems(tmp_path, manifest, ("exam_y/*",))
    assert probs == [
        "exam_y/fr_y.pkl: seal broken (mode 0o644)",
        "exam_y/late.pkl: outcome file not sealed",
    ]


def test_unsealer_logs_each_open_and_reseals(tmp_path: Path) -> None:
    f = _chunk(tmp_path, "full/all/exam_y/y/2026-01_000.pkl.gz", b"y")
    manifest = tmp_path / guard.MANIFEST_NAME
    guard.seal([f], tmp_path, manifest)
    log = tmp_path / "run" / "exam_access.log"
    with guard.unsealing(tmp_path, manifest, log) as u:
        assert u.open(f).read_bytes() == b"y"
    assert stat.S_IMODE(f.stat().st_mode) == 0
    lines = [ln.split("\t") for ln in log.read_text().splitlines()]
    assert [ln[1:3] for ln in lines] == [
        ["open", "full/all/exam_y/y/2026-01_000.pkl.gz"],
        ["resealed", "full/all/exam_y/y/2026-01_000.pkl.gz"],
    ]
    assert lines[0][3] == hashlib.sha256(b"y").hexdigest()


def test_unsealer_refuses_a_changed_or_unlisted_file(tmp_path: Path) -> None:
    f = _chunk(tmp_path, "exam_y/a.pkl", b"a")
    g = _chunk(tmp_path, "exam_y/b.pkl", b"b")
    manifest = tmp_path / guard.MANIFEST_NAME
    guard.seal([f], tmp_path, manifest)
    os.chmod(f, 0o600)
    f.write_bytes(b"tampered")
    os.chmod(f, 0)
    log = tmp_path / "access.log"
    with guard.unsealing(tmp_path, manifest, log) as u:
        with pytest.raises(PermissionError, match="differs from the manifest"):
            u.open(f)
        with pytest.raises(PermissionError, match="not in the seal manifest"):
            u.open(g)
    assert stat.S_IMODE(f.stat().st_mode) == 0  # resealed even after refusal


def test_sealed_outcomes_are_unreadable_outside_the_exam_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mse, "SCRATCH", tmp_path)
    _chunk(tmp_path / "full" / "all", "exam_y/y/2026-01_000.pkl.gz")
    with pytest.raises(PermissionError, match="only exam --mode exam"):
        list(mse.read_chunks("exam_y", "y"))
    with pytest.raises(PermissionError, match="only exam --mode exam"):
        mse.sealed_path(tmp_path / "exam_y" / "fr_y.pkl")


def test_seal_stage_seals_every_outcome_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mse, "SCRATCH", tmp_path)
    monkeypatch.setattr(mse, "SEAL_MANIFEST", tmp_path / guard.MANIFEST_NAME)
    a = _chunk(tmp_path, "exam_y/fr_y.pkl")
    b = _chunk(tmp_path, "full/all/exam_y/y/2026-01_000.pkl.gz")
    x = _chunk(tmp_path, "full/all/exam/rows/2026-01_000.pkl.gz")
    assert mse.main(["seal"]) == 0
    assert [stat.S_IMODE(p.stat().st_mode) for p in (a, b)] == [0, 0]
    assert stat.S_IMODE(x.stat().st_mode) != 0  # X rows are not outcomes


# --- the dead_goals study: S5 at the frozen coefficient, P2 on touched rows
def _fake_population(states: dict[int, tuple[str, str]]) -> None:
    mse._POP.clear()
    mse._POP.append(
        mse.Pop(
            {e: {"home": h, "away": a, "women": False} for e, (h, a) in states.items()},
            {},
            {},
        )
    )


def test_dead_goals_study_columns_and_rules() -> None:
    st = mse.configure("dead_goals")
    assert mse.COLS == ["own_DEAD", "opp_DEAD"]
    assert mse.ALL_GROUPS == ("goals",)
    assert mse.S3_DIRECTIONS == {"own_DEAD": 1, "opp_DEAD": 1}
    assert (st.s5, st.p2) == ("frozen_coef", "any_column")
    assert mse.WORK != mse.SCRATCH
    assert mse.EVIDENCE.name == "stakes_dead_goals_2026-11-19"


def test_s5_per_column_at_frozen_coefficient() -> None:
    mse.configure("dead_goals")
    # 30 matches, home DEAD in 10: own_DEAD sides 10, opp_DEAD sides 10
    _fake_population(
        {e: ("DEAD" if e < 10 else "ALIVE", "ALIVE") for e in range(30)}
    )
    rows = [
        {"eid": e, "side": s, "centre": 1.0, "alpha": 0.0}
        for e in range(30)
        for s in ("home", "away")
    ]
    need_03 = 7.85 * 1.0 * 1.75 / 0.03**2
    flat = mse._power_of(rows, [])
    assert flat["n_req"] == pytest.approx(need_03) and flat["pass"] is False
    big = mse._power_of(rows, [], {"own_DEAD": 2.5, "opp_DEAD": 0.01})
    assert big["best"] == "own_DEAD"
    assert big["n_req"] == pytest.approx(7.85 * 1.75 / 2.5**2)
    assert big["pass"] is True  # 10 sides >= 2.2
    assert set(big["n_req_by_column"]) == {"own_DEAD", "opp_DEAD"}


def test_p2_any_column_counts_every_row_the_term_touches() -> None:
    _fake_population(
        {e: ("DEAD" if e < 3 else "ALIVE", "ALIVE") for e in range(100)}
    )
    rows = [{"eid": e, "side": s} for e in range(100) for s in ("home", "away")]
    frozen = {"goals_for": {"own_DEAD": 0.10, "opp_DEAD": 0.10}}
    mse.configure("dead_goals")
    # own_DEAD alone 3 / 200 = 1.5%; touched (own or opp) 6 / 200 = 3%
    got = mse.exposure_material(frozen, rows)
    assert got["material"] is True and got["p2_rule"] == "any_column"
    assert got["exposure"]["own_DEAD"] == pytest.approx(0.015)
    mse.configure("football")
    assert mse.exposure_material(frozen, rows)["material"] is False
