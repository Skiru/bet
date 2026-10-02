"""scripts/sofa/prepare_refit.py - the between-days refit, on temp dirs only.

Every step is exercised against a temporary config/, DB and runs dir; no test
reads or writes the repo's config/, data/sofa.db or runs/sofa.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import timeutil
from bet.sofa.config import REPO_CONFIG_DIR, config_dir, config_path
from scripts.sofa import prepare_refit as pr

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _no_lsof(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pr, "processes_holding", lambda path: [])


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, doc: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")


def _constants(k_football: float) -> dict[str, Any]:
    return {
        "fitted_from": {"settled_rows": 100},
        "K_CENTRE": {
            "value": 25.0,
            "by_sport": {"football": k_football, "tennis": 2.0},
            "status": "FITTED",
        },
        "K_PRICE": {"value": None, "status": "NOT_FITTED"},
        "MAX_LADDER_SIGMA": {"value": None, "status": "NO_DIVERGENCE"},
    }


def _calibration(lo: float, *, direction: bool, player: bool) -> dict[str, Any]:
    cell = {"n": 1000, "realised": lo + 0.01, "realised_lo95": lo}
    doc: dict[str, Any] = {
        "fitted_from": {"scored_rows": 10},
        "pooled": {"0.700-0.750": cell},
        "pooled_by_sport": {"football": {"0.700-0.750": cell}},
        "by_market": {
            "goals_total": {
                "0.700-0.750": cell,
                **({} if direction else {"0.750-0.800": cell}),
            }
        },
        "by_class": {
            "women": {
                "by_market": {"goals_total": {"0.700-0.750": cell}},
                "by_market_direction": {},
                "pooled_by_sport": {},
            }
        },
    }
    if direction:
        doc["by_market_direction"] = {"goals_total|OVER": {"0.700-0.750": cell}}
    if player:
        doc["by_market"]["player_shots_for"] = {"0.700-0.750": cell}
    return doc


def _config_set(root: Path, *, new: bool) -> Path:
    cfg = root
    _write(cfg / "sofa_engine_constants.json", _constants(20.0 if new else 25.0))
    _write(
        cfg / "sofa_league_baselines.json",
        {
            "fitted_from": {"settled_rows": 100},
            "half_match_coherence": "OK" if new else ["goals_for: -10.8%"],
            "goals_total": {
                "1": {"mean": 2.9 if new else 2.5, "n": 40},
                "2": {"mean": 3.0, "n": 40},
                **({"3": {"mean": 1.0, "n": 31}} if new else {}),
            },
        },
    )
    _write(
        cfg / "sofa_market_reliability.json",
        {
            "_fitted_from": {"settled_rows": 100},
            "goals_total": {
                "0.7-0.8": {
                    "realised": 0.70 if new else 0.74,
                    "n": 500,
                    "correction": 0.05 if new else 0.0,
                    "status": "MEASURED",
                }
            },
        },
    )
    _write(
        cfg / "sofa_confidence_calibration.json",
        _calibration(0.72 if new else 0.70, direction=new, player=new),
    )
    _write(cfg / "sofa_women_competitions.json", {"women": []})
    return cfg


def _paths(tmp: Path) -> pr.Paths:
    return pr.Paths(
        config_dir=tmp / "config",
        db_path=tmp / "sofa.db",
        runs_dir=tmp / "runs" / "sofa",
        scratch=tmp / "scratch",
        date="2026-10-03",
    )


SCHEMA = """CREATE TABLE sofa_settled_row (
    id INTEGER PRIMARY KEY AUTOINCREMENT, run_date TEXT NOT NULL,
    sofascore_event_id INTEGER NOT NULL, sport TEXT NOT NULL, competition_id INTEGER,
    market TEXT NOT NULL, subject TEXT NOT NULL, line REAL NOT NULL,
    direction TEXT NOT NULL, outcome TEXT NOT NULL, actual_value REAL,
    UNIQUE(sofascore_event_id, market, subject, line, direction))"""


def _db(path: Path, live: int = 3, cache: int = 5) -> Path:
    conn = sqlite3.connect(str(path))
    conn.execute(SCHEMA)
    for i in range(live):
        conn.execute(
            "INSERT INTO sofa_settled_row (run_date, sofascore_event_id, sport, "
            "market, subject, line, direction, outcome, actual_value) "
            "VALUES (?, ?, 'football', 'goals_total', '', 2.5, 'OVER', ?, 3)",
            (
                "2026-10-01" if i % 2 else "2026-10-02",
                100 + i,
                "WIN" if i % 2 else "LOSS",
            ),
        )
    for i in range(cache):
        conn.execute(
            "INSERT INTO sofa_settled_row (run_date, sofascore_event_id, sport, "
            "market, subject, line, direction, outcome) "
            "VALUES ('cache-calibration', ?, 'football', 'corners_total', '', 9.5, "
            "'UNDER', 'WIN')",
            (1000 + i,),
        )
    conn.commit()
    conn.close()
    return path


# --------------------------------------------------------------------------
# SOFA_CONFIG_DIR - the one override every config reader follows
# --------------------------------------------------------------------------


def test_config_dir_defaults_to_the_repo_and_follows_the_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("SOFA_CONFIG_DIR", raising=False)
    assert config_dir() == REPO_CONFIG_DIR == REPO / "config"
    monkeypatch.setenv("SOFA_CONFIG_DIR", str(tmp_path))
    assert config_path("x.json") == tmp_path.resolve() / "x.json"
    monkeypatch.setenv("SOFA_CONFIG_DIR", "  ")
    assert config_dir() == REPO_CONFIG_DIR


def test_sheet_and_replay_readers_follow_sofa_config_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from bet.sofa.config import SofaConfig
    from scripts.sofa import calibrate_from_cache, run_sheet

    _config_set(tmp_path, new=True)
    monkeypatch.setenv("SOFA_CONFIG_DIR", str(tmp_path))
    cfg = SofaConfig()
    assert (
        run_sheet.load_engine_constants(cfg)["K_CENTRE"]["by_sport"]["football"] == 20.0
    )
    assert run_sheet.load_baselines(cfg)["goals_total"]["1"]["mean"] == 2.9
    assert "goals_total" in run_sheet.load_reliability(cfg)
    assert calibrate_from_cache.k_centre_for("football") == 20.0
    assert calibrate_from_cache.load_baselines()["goals_total"]["1"]["mean"] == 2.9


def test_module_level_config_paths_are_fixed_by_the_env_at_import(
    tmp_path: Path,
) -> None:
    """confidence / samples / derived / tennis_rating build their paths at
    import, so a child process started with SOFA_CONFIG_DIR reads the scratch
    files - the way prepare_refit runs every replay stage."""
    code = (
        "from bet.sofa import confidence, samples, derived, tennis_rating;"
        "print(confidence.DEFAULT_CALIBRATION);"
        "print(confidence._WOMEN_COMPETITIONS_PATH);"
        "print(samples._FRIENDLIES_PATH); print(samples._NO_STATS_PATH);"
        "print(derived.CORRELATIONS_PATH); print(tennis_rating.DEFAULT_CONFIG)"
    )
    env = pr.child_env(SOFA_CONFIG_DIR=str(tmp_path))
    out = subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    lines = out.split()
    assert len(lines) == 6
    assert all(Path(line).parent == tmp_path.resolve() for line in lines)


# --------------------------------------------------------------------------
# 1. backup
# --------------------------------------------------------------------------


def test_backup_writes_a_manifest_skips_secrets_and_refuses_to_overwrite(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    _config_set(paths.config_dir, new=False)
    (paths.config_dir / "api_keys.json").write_text('{"k": "secret"}')
    result = pr.backup(paths, None)
    dest = paths.backup_dir
    assert dest.name == "backup_2026-10-03"
    manifest = json.loads((dest / pr.MANIFEST).read_text())
    assert "api_keys.json" not in manifest["files"]
    assert not (dest / "api_keys.json").exists()
    assert manifest["excluded"] == ["api_keys.json"]
    for name, entry in manifest["files"].items():
        assert entry["sha256"] == _sha(paths.config_dir / name) == _sha(dest / name)
    assert result["exit"] == 0
    with pytest.raises(pr.RefitError, match="refusing to overwrite"):
        pr.backup(paths, None)


def test_backup_db_copies_the_files_and_refuses_without_twice_its_size_free(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    paths = _paths(tmp_path)
    _config_set(paths.config_dir, new=False)
    _db(paths.db_path)
    target = tmp_path / "bk" / "sofa.db"

    class Usage:
        free = 10

    monkeypatch.setattr("shutil.disk_usage", lambda p: Usage())
    with pytest.raises(pr.RefitError, match="2 x DB"):
        pr.backup(paths, target)
    assert not paths.backup_dir.exists(), "a refusal leaves nothing behind"
    monkeypatch.undo()
    monkeypatch.setattr(pr, "processes_holding", lambda path: [])
    result = pr.backup(paths, target)
    assert target.read_bytes() == paths.db_path.read_bytes()
    db = result["manifest"]["db"]
    assert db["checkpoint"]["attempted"] is True
    assert db["changed_during_copy"] is False


# --------------------------------------------------------------------------
# 2. rebuild-cache-rows
# --------------------------------------------------------------------------


def test_rebuild_dry_run_counts_and_touches_nothing(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _db(paths.db_path)
    before = _sha(paths.db_path)
    report = pr.rebuild_cache_rows(paths, dry_run=True, confirm=False)
    assert report["cache_rows"] == 5
    assert report["live_rows"] == 3
    assert report["before"] == {
        "2026-10-01": 1,
        "2026-10-02": 2,
        "cache-calibration": 5,
    }
    assert _sha(paths.db_path) == before


def test_rebuild_needs_confirm_and_never_points_calibrate_at_config(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    _db(paths.db_path)
    with pytest.raises(pr.RefitError, match="--confirm"):
        pr.rebuild_cache_rows(paths, dry_run=False, confirm=False)
    with pytest.raises(pr.RefitError, match="never point into config"):
        pr.rebuild_cache_rows(
            paths,
            dry_run=True,
            confirm=False,
            calibrate_out=paths.config_dir / "sofa_market_reliability.json",
        )


def _fake_calibrate(db: Path, *, touch_live: str | None = None) -> pr.Runner:
    def runner(
        cmd: Sequence[str], env: dict[str, str], log: Path | None
    ) -> tuple[int, list[str]]:
        assert "calibrate_from_cache.py" in cmd[1]
        assert "--out" not in cmd
        conn = sqlite3.connect(str(db))
        for i in range(4):
            conn.execute(
                "INSERT INTO sofa_settled_row (run_date, sofascore_event_id, sport, "
                "market, subject, line, direction, outcome) VALUES "
                "('cache-calibration', ?, 'football', 'fouls_total', '', 20.5, "
                "'OVER', 'LOSS')",
                (5000 + i,),
            )
        if touch_live == "replace":
            # What INSERT OR REPLACE did on 2026-09-26: same count, new id.
            conn.execute(
                "INSERT OR REPLACE INTO sofa_settled_row (run_date, "
                "sofascore_event_id, sport, market, subject, line, direction, "
                "outcome) VALUES ('2026-10-02', 100, 'football', 'goals_total', "
                "'', 2.5, 'OVER', 'WIN')"
            )
        conn.commit()
        conn.close()
        return 0, ['SOFA_SUMMARY: {"stage": "CALIBRATE_FROM_CACHE", "verdict": "OK"}']

    return runner


def test_rebuild_replaces_cache_rows_and_leaves_live_rows(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _db(paths.db_path)
    report = pr.rebuild_cache_rows(
        paths,
        dry_run=False,
        confirm=True,
        require_db_backup=False,
        chunk=2,
        runner=_fake_calibrate(paths.db_path),
    )
    assert report["deleted"] == 5
    assert report["after"]["cache-calibration"] == 4
    assert report["after"]["2026-10-02"] == 2
    assert report["calibrate_summary"][0]["stage"] == "CALIBRATE_FROM_CACHE"


def test_rebuild_refuses_when_a_live_row_is_replaced(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _db(paths.db_path)
    with pytest.raises(pr.RefitError, match="LIVE ROWS CHANGED"):
        pr.rebuild_cache_rows(
            paths,
            dry_run=False,
            confirm=True,
            runner=_fake_calibrate(paths.db_path, touch_live="replace"),
            require_db_backup=False,
        )


# --------------------------------------------------------------------------
# 3. fit
# --------------------------------------------------------------------------


def _fake_fit(*, write_live: Path | None = None) -> pr.Runner:
    def runner(
        cmd: Sequence[str], env: dict[str, str], log: Path | None
    ) -> tuple[int, list[str]]:
        new = _config_set(Path(env["SOFA_CONFIG_DIR"]) / "_new", new=True)
        if "fit_constants.py" in cmd[1]:
            out = Path(cmd[cmd.index("--config-dir") + 1])
            assert out == Path(env["SOFA_CONFIG_DIR"])
            for name in pr.FIT_OUTPUTS[:3]:
                (out / name).write_bytes((new / name).read_bytes())
            if write_live is not None:
                (write_live / "sofa_engine_constants.json").write_text("{}")
            return 1, []  # PARTIAL: K_PRICE NOT_FITTED
        out = Path(cmd[cmd.index("--out") + 1])
        out.write_bytes((new / pr.CONFIDENCE_FILE).read_bytes())
        return 0, []

    return runner


def test_fit_writes_only_into_scratch(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _config_set(paths.config_dir, new=False)
    _db(paths.db_path)
    live = {p.name: _sha(p) for p in paths.config_dir.glob("*.json")}
    result = pr.fit(paths, force=False, runner=_fake_fit())
    assert result["complete"] is True
    assert {p.name: _sha(p) for p in paths.config_dir.glob("*.json")} == live
    # Files the fits do not write are present in scratch (copied from live).
    assert (paths.scratch_config / "sofa_women_competitions.json").exists()
    new_k = json.loads(
        (paths.scratch_config / "sofa_engine_constants.json").read_text()
    )
    assert new_k["K_CENTRE"]["by_sport"]["football"] == 20.0
    manifest = json.loads((paths.scratch / pr.FIT_MANIFEST).read_text())
    assert set(manifest["outputs_sha256"]) == set(pr.FIT_OUTPUTS)
    with pytest.raises(pr.RefitError, match="--force"):
        pr.fit(paths, force=False, runner=_fake_fit())


def test_fit_refuses_a_scratch_under_runs_or_config(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _config_set(paths.config_dir, new=False)
    _db(paths.db_path)
    for bad in (
        paths.runs_dir / "refit_2026-10-03",
        paths.config_dir / "x",
        REPO / "runs" / "sofa" / "refit_x",
    ):
        paths.scratch = bad
        with pytest.raises(pr.RefitError, match="overlaps"):
            pr.fit(paths, force=False, runner=_fake_fit())


def test_fit_aborts_when_the_live_config_moves(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _config_set(paths.config_dir, new=False)
    _db(paths.db_path)
    with pytest.raises(pr.RefitError, match="LIVE CONFIG CHANGED"):
        pr.fit(paths, force=False, runner=_fake_fit(write_live=paths.config_dir))


# --------------------------------------------------------------------------
# 4. compare
# --------------------------------------------------------------------------


def test_compare_reports_every_section_from_two_config_sets(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _config_set(paths.config_dir, new=False)
    _config_set(paths.scratch_config, new=True)
    report = pr.compare(paths, days=None, with_sheet=False, replay=False)
    cfg = report["configs"]
    k = {r["constant"]: r for r in cfg["constants"]}
    assert k["K_CENTRE.by_sport.football"]["old"] == 25.0
    assert k["K_CENTRE.by_sport.football"]["new"] == 20.0
    assert k["K_PRICE"]["new_status"] == "NOT_FITTED"
    top = cfg["baselines"]["top"][0]
    assert (top["market"], top["competition"], top["delta"]) == (
        "goals_total",
        "1",
        0.4,
    )
    assert cfg["baselines"]["added_entries"] == 1
    assert cfg["baselines"]["half_match_coherence"]["new"] == "OK"
    rel = cfg["reliability"]["top"][0]
    assert rel["delta_correction"] == 0.05
    conf = cfg["confidence"]
    assert conf["top_moves"][0]["delta_lo95"] == 0.02
    assert [a["curve"] for a in conf["by_market_direction"]["added"]] == [
        "goals_total|OVER"
    ]
    removed = [r for r in conf["buckets_added_or_removed"] if r["change"] == "removed"]
    assert removed and removed[0]["bucket"] == "0.750-0.800"
    assert conf["player_curves"][0]["curve"] == "player_shots_for"
    assert conf["player_curves"][0]["n"] == 1000
    assert "women" in conf["by_class"]
    md = (paths.scratch / "compare_report.md").read_text()
    for heading in (
        "Engine constants",
        "League baselines",
        "Market reliability",
        "Confidence curves",
        "by_market_direction",
        "Player-prop",
        "Coupon replay",
        "SHEET was NOT re-run",
    ):
        assert heading in md
    # Review 2026-10-03: the OVER curves (what Superbet quotes, what CONFIDENCE
    # reads) come first; the combined player_shots_for curve is listed apart
    # as never read.
    assert "OVER - what Superbet quotes" in md
    assert md.index("OVER - what Superbet quotes") < md.index("never read for a prop")
    assert md.index("never read for a prop") < md.index("| player_shots_for |")
    assert pr._bucket_mid("0.700-0.750") == "0.725"
    assert json.loads((paths.scratch / "compare_report.json").read_text())


def _leg(eid: int, market: str, conf: float, odds: float = 1.5) -> dict[str, Any]:
    return {
        "sofascore_event_id": eid,
        "match": f"M{eid}",
        "market": market,
        "subject": "",
        "line": 2.5,
        "direction": "OVER",
        "confidence": conf,
        "offered_odds": odds,
    }


def _artifact(legs: list[dict[str, Any]], profile: str) -> dict[str, Any]:
    return {
        "created_at_utc": "2026-10-01T13:58:00Z",
        "profile": profile,
        "pdf_max_singles": 30 if profile == "standard" else None,
        "prints_builders": profile == "standard",
        "min_ev": None,
        "legs": legs,
        "singles": legs,
        "builders": [],
    }


def _real_day(paths: pr.Paths, day: str) -> Path:
    real = paths.runs_dir / day
    real.mkdir(parents=True)
    legs = [_leg(100, "goals_total", 0.75), _leg(101, "goals_total", 0.72)]
    _write(real / "08_confidence.json", _artifact(legs, "standard"))
    _write(real / "05_sheet.json", [])
    (real / "closing.jsonl").write_text("")
    return real


def _fake_replay(paths: pr.Paths, *, clobber: Path | None = None) -> pr.Runner:
    def runner(
        cmd: Sequence[str], env: dict[str, str], log: Path | None
    ) -> tuple[int, list[str]]:
        assert cmd[2] == "_frozen" and cmd[4] == "2026-10-01T13:58:00Z"
        argv = list(cmd[cmd.index("--") + 1 :])
        runs = Path(env["SOFA_RUNS_DIR"])
        assert Path(argv[argv.index("--runs-dir") + 1]) == runs
        assert not pr.is_within(runs, paths.runs_dir)
        if clobber is not None:
            (clobber / "08_confidence.json").write_text("{}")
        if "run_confidence.py" not in argv[0]:
            return 0, []
        day = argv[argv.index("--date") + 1]
        new = Path(env["SOFA_CONFIG_DIR"]) == paths.scratch_config
        legs = (
            [_leg(100, "goals_total", 0.78), _leg(102, "corners_total", 0.71)]
            if new
            else [_leg(100, "goals_total", 0.75), _leg(101, "goals_total", 0.72)]
        )
        _write(runs / day / "08_confidence.json", _artifact(legs, "standard"))
        return 0, []

    return runner


def test_replay_diffs_printed_legs_and_reads_their_settled_outcome(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    _config_set(paths.config_dir, new=False)
    _config_set(paths.scratch_config, new=True)
    _db(paths.db_path)
    real = _real_day(paths, "2026-10-01")
    real_sha = {p.name: _sha(p) for p in real.iterdir()}
    report = pr.compare(
        paths, days=["2026-10-01"], with_sheet=False, runner=_fake_replay(paths)
    )
    std = report["replay"]["2026-10-01"]["profiles"]["standard"]
    effect = std["config_effect"]
    assert [r["key"][0] for r in effect["dropped"]] == [101]
    assert effect["dropped"][0]["settled"]["outcome"] == "WIN"
    assert effect["dropped"][0]["units_at_printed_odds"] == 0.5
    assert [r["key"][0] for r in effect["added"]] == [102]
    assert effect["added"][0]["settled"] is None
    assert effect["changed"][0]["delta"] == 0.03
    assert std["code_drift_vs_real"] == {"dropped": 0, "added": 0, "changed": 0}
    assert {p.name: _sha(p) for p in real.iterdir()} == real_sha
    assert "in-sample" in (paths.scratch / "compare_report.md").read_text()


def test_replay_refuses_when_the_real_day_changes(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _config_set(paths.config_dir, new=False)
    _config_set(paths.scratch_config, new=True)
    real = _real_day(paths, "2026-10-01")
    with pytest.raises(pr.RefitError, match="THE REAL DAY"):
        pr.compare(
            paths,
            days=["2026-10-01"],
            with_sheet=False,
            runner=_fake_replay(paths, clobber=real),
        )


def test_the_md5_guard_ignores_the_closing_capture_loop(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    real = _real_day(paths, "2026-10-01")
    expected = pr.day_fingerprint(real)
    (real / "closing.jsonl").write_text('{"appended": 1}\n')
    (real / "capture_closing.log").write_text("x")
    pr.guard_day(real, expected)  # no raise


def test_frozen_runner_fixes_the_clock_for_the_stage(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(timeutil, "now", timeutil.now)  # restored after the test
    script = tmp_path / "stage.py"
    script.write_text(
        "import sys\nfrom bet.sofa.timeutil import now\n"
        "print(now().isoformat(), sys.argv[1:])\nraise SystemExit(1)\n"
    )
    rc = pr.main(["_frozen", "--at", "2026-10-01T13:58:00Z", "--", str(script), "--x"])
    assert rc == 1
    assert "2026-10-01T13:58:00+00:00 ['--x']" in capsys.readouterr().out


# --------------------------------------------------------------------------
# 5. install / 6. restore
# --------------------------------------------------------------------------


def _ready_to_install(tmp_path: Path) -> pr.Paths:
    paths = _paths(tmp_path)
    _config_set(paths.config_dir, new=False)
    live_cal = json.loads((paths.config_dir / pr.CONFIDENCE_FILE).read_text())
    live_cal["admitted_player_markets"] = ["player_shots_for"]
    _write(paths.config_dir / pr.CONFIDENCE_FILE, live_cal)
    _db(paths.db_path)
    pr.fit(paths, force=False, runner=_fake_fit())
    # The operator decision is made in config/ after the fit started.
    scratch_cal = json.loads((paths.scratch_config / pr.CONFIDENCE_FILE).read_text())
    assert "admitted_player_markets" not in scratch_cal
    pr.backup(paths, None)
    return paths


def test_install_carries_operator_keys_and_prints_the_commit(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    paths = _ready_to_install(tmp_path)
    with pytest.raises(pr.RefitError, match="--confirm"):
        pr.install(paths, confirm=False, tests=lambda: 0)
    pr.install(paths, confirm=True, tests=lambda: 0)
    cal = json.loads((paths.config_dir / pr.CONFIDENCE_FILE).read_text())
    assert cal["admitted_player_markets"] == ["player_shots_for"]
    assert "goals_total|OVER" in cal["by_market_direction"]
    k = json.loads((paths.config_dir / "sofa_engine_constants.json").read_text())
    assert k["K_CENTRE"]["by_sport"]["football"] == 20.0
    assert (paths.config_dir / "sofa_league_baselines.json").read_bytes() == (
        paths.scratch_config / "sofa_league_baselines.json"
    ).read_bytes()
    assert "refit 2026-10-03: new comparability epoch" in capsys.readouterr().out


def test_install_restores_the_backup_when_tests_fail(tmp_path: Path) -> None:
    paths = _ready_to_install(tmp_path)
    before = {p.name: _sha(p) for p in paths.config_dir.glob("*.json")}
    with pytest.raises(pr.RefitError, match="restored"):
        pr.install(paths, confirm=True, tests=lambda: 1)
    assert {p.name: _sha(p) for p in paths.config_dir.glob("*.json")} == before


def test_install_refuses_when_config_moved_since_the_backup(tmp_path: Path) -> None:
    paths = _ready_to_install(tmp_path)
    (paths.config_dir / "sofa_engine_constants.json").write_text("{}")
    with pytest.raises(pr.RefitError, match="changed since backup"):
        pr.install(paths, confirm=True, tests=lambda: 0)


def test_restore_round_trips(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _config_set(paths.config_dir, new=False)
    pr.backup(paths, None)
    before = {p.name: _sha(p) for p in paths.config_dir.glob("*.json")}
    (paths.config_dir / "sofa_engine_constants.json").write_text("{}")
    with pytest.raises(pr.RefitError, match="--confirm"):
        pr.restore(paths, confirm=False, backup_dir=paths.backup_dir)
    result = pr.restore(paths, confirm=True, backup_dir=paths.backup_dir)
    assert result["restored"] == ["sofa_engine_constants.json"]
    assert {p.name: _sha(p) for p in paths.config_dir.glob("*.json")} == before


def test_cli_refusal_exits_two(tmp_path: Path) -> None:
    rc = pr.main(
        [
            "--config-dir",
            str(tmp_path / "config"),
            "--db-path",
            str(tmp_path / "none.db"),
            "rebuild-cache-rows",
            "--dry-run",
        ]
    )
    assert rc == 2


def test_printed_legs_reads_builder_legs_in_the_real_shape() -> None:
    """A builder leg has no fixture id and names its price `odds`
    (08_confidence_wariant.json, 2026-10-01); only stakeable builders print."""
    leg = {"market": "corners_total", "subject": "", "line": 8.5,
           "direction": "OVER", "confidence": 0.8, "odds": 1.3}
    builder = {"sofascore_event_id": 7, "match": "A - B", "legs": [leg],
               "best_for_fixture": True, "ev_after_haircut": 0.04}
    unstaked = {**builder, "sofascore_event_id": 8, "ev_after_haircut": -0.01}
    artifact = {"profile": "standard", "min_ev": None, "prints_builders": True,
                "singles": [],
                "builders": [builder, unstaked]}
    printed = pr.printed_legs(artifact)
    assert list(printed) == [(7, "corners_total", "", 8.5, "OVER")]
    entry = printed[(7, "corners_total", "", 8.5, "OVER")]
    assert entry["offered_odds"] == 1.3 and entry["match"] == "A - B"
    assert entry["as"] == ["builder#1"]


def test_rebuild_hands_the_real_runs_dir_to_the_player_replay(tmp_path: Path) -> None:
    """Review 2026-10-03: without --runs-dir the replay read SOFA_RUNS_DIR, and
    a scratch runs dir there emptied the player replay with exit 0."""
    paths = _paths(tmp_path)
    _db(paths.db_path)
    seen: list[list[str]] = []
    inner = _fake_calibrate(paths.db_path)

    def runner(cmd: Sequence[str], env: dict[str, str], log: Path | None
               ) -> tuple[int, list[str]]:
        seen.append(list(cmd))
        return inner(cmd, env, log)

    pr.rebuild_cache_rows(paths, dry_run=False, confirm=True, runner=runner,
        require_db_backup=False)
    cmd = seen[0]
    assert cmd[cmd.index("--runs-dir") + 1] == str(paths.runs_dir)


def test_rebuild_stops_when_the_player_replay_produced_nothing(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _db(paths.db_path)

    def runner(cmd: Sequence[str], env: dict[str, str], log: Path | None
               ) -> tuple[int, list[str]]:
        return 1, ['SOFA_SUMMARY: {"stage": "CALIBRATE_FROM_CACHE", "verdict": '
                   '"PARTIAL", "metrics": {"player_replay": "NO_ROWS"}}']

    with pytest.raises(pr.RefitError, match="NO_ROWS"):
        pr.rebuild_cache_rows(paths, dry_run=False, confirm=True, runner=runner,
        require_db_backup=False)


def test_a_runs_dir_from_the_environment_must_be_the_real_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Review 2026-10-03: --runs-dir defaulted to SOFA_RUNS_DIR, so a shell left
    pointing at a scratch rebuild fitted the player ladder of a few days."""
    monkeypatch.setenv("SOFA_RUNS_DIR", str(tmp_path / "scratch_runs"))
    rc = pr.main(["--date", "2026-10-03", "rebuild-cache-rows", "--dry-run"])
    assert rc == 2
    assert "SOFA_RUNS_DIR" in capsys.readouterr().err
    args = pr.build_parser().parse_args(
        ["--runs-dir", str(tmp_path / "scratch_runs"), "--date", "2026-10-03",
         "rebuild-cache-rows", "--dry-run"])
    assert pr.resolve_paths(args).runs_dir == tmp_path / "scratch_runs"


def test_rebuild_needs_todays_db_backup(tmp_path: Path) -> None:
    """Review 2026-10-03: the delete of ~50M rows is not undoable without a
    DB copy, and the step only asked for one in a message."""
    paths = _paths(tmp_path)
    _db(paths.db_path)
    with pytest.raises(pr.RefitError, match="no DB backup"):
        pr.rebuild_cache_rows(paths, dry_run=False, confirm=True,
                              runner=_fake_calibrate(paths.db_path))
    paths.config_dir.mkdir(parents=True, exist_ok=True)
    (paths.config_dir / "sofa_engine_constants.json").write_text("{}")
    pr.backup(paths, tmp_path / "dbcopy" / "sofa.db")
    report = pr.rebuild_cache_rows(paths, dry_run=False, confirm=True,
                                   runner=_fake_calibrate(paths.db_path))
    assert report["exit"] == 0


def test_rebuild_refuses_while_another_process_holds_the_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _paths(tmp_path)
    _db(paths.db_path)
    monkeypatch.setattr(pr, "processes_holding", lambda p: ["pid 1 backfill"])
    with pytest.raises(pr.RefitError, match="other processes"):
        pr.rebuild_cache_rows(paths, dry_run=False, confirm=True,
                              runner=_fake_calibrate(paths.db_path),
                              require_db_backup=False)
    report = pr.rebuild_cache_rows(paths, dry_run=False, confirm=True,
                                   runner=_fake_calibrate(paths.db_path),
                                   require_db_backup=False,
                                   allow_other_holders=True)
    assert report["exit"] == 0


def test_a_db_path_from_the_environment_must_be_the_real_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("SOFA_DB_PATH", str(tmp_path / "other.db"))
    rc = pr.main(["--date", "2026-10-03", "rebuild-cache-rows", "--dry-run"])
    assert rc == 2 and "SOFA_DB_PATH" in capsys.readouterr().err
