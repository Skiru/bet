"""Focused tests for runner runtime path inheritance in orchestrator sandboxes."""
from __future__ import annotations

import json
from pathlib import Path

from scripts.pipeline_steps import _runner


def _fixture_root() -> Path:
    return Path(__file__).parent / "fixtures" / "pipeline_wrappers"


def _write_env_dump_script(fixture_root: Path) -> Path:
    dump_script = fixture_root / "scripts" / "dump_env.py"
    dump_script.write_text(
        "import json\n"
        "import os\n"
        "from pathlib import Path\n"
        "record_path = Path(os.environ['FIXTURE_RECORD_PATH'])\n"
        "record_path.write_text(json.dumps(dict(os.environ)), encoding='utf-8')\n",
        encoding="utf-8",
    )
    return dump_script


def test_parent_tmp_runtime_env_is_preserved_for_child_subprocesses(tmp_path, monkeypatch):
    fixture_root = _fixture_root()
    record_path = tmp_path / "capture.json"
    dump_script = _write_env_dump_script(fixture_root)
    parent_run_root = Path("/tmp") / f"bet-runner-inherit-{tmp_path.name}"

    try:
        monkeypatch.setattr(_runner, "ROOT", fixture_root)
        monkeypatch.setenv("FIXTURE_RECORD_PATH", str(record_path))
        monkeypatch.setenv("BET_PIPELINE_RUN_ROOT", str(parent_run_root))
        monkeypatch.setenv("BET_PIPELINE_DATA_DIR", str(parent_run_root / "data"))
        monkeypatch.setenv("BET_PIPELINE_COUPON_DIR", str(parent_run_root / "coupons"))
        monkeypatch.setenv("BET_PIPELINE_ARTIFACT_DIR", str(parent_run_root / "artifacts"))
        monkeypatch.setenv("BET_PIPELINE_BETTING_DAY", "2026-06-25")
        monkeypatch.setenv("BET_PIPELINE_RUN_ID", "run-inherit")

        rc = _runner.run_scripts(
            ["dump_env.py"],
            date="2026-06-25",
            dry_run=True,
            allow_write=False,
            runtime_mode="LIVE_SHADOW",
            betting_day="2026-06-25",
            run_id="run-inherit",
        )

        assert rc == 0
        payload = json.loads(record_path.read_text(encoding="utf-8"))
        assert payload["BET_PIPELINE_RUN_ROOT"] == str(parent_run_root)
        assert payload["BET_PIPELINE_DATA_DIR"] == str(parent_run_root / "data")
        assert payload["BET_PIPELINE_COUPON_DIR"] == str(parent_run_root / "coupons")
        assert payload["BET_PIPELINE_ARTIFACT_DIR"] == str(parent_run_root / "artifacts")
        assert payload["BET_PIPELINE_RUNTIME_MODE"] == "LIVE_SHADOW"
        assert payload["DRY_RUN"] == "1"
        assert payload["DATABASE_URL"].startswith("sqlite:///")
        assert "bet_dryrun_" in payload["DATABASE_URL"]
        assert Path(payload["BET_PIPELINE_DATA_DIR"]).exists()
        assert Path(payload["BET_PIPELINE_COUPON_DIR"]).exists()
        assert Path(payload["BET_PIPELINE_ARTIFACT_DIR"]).exists()
        assert "reports/pipeline_runs" not in payload["BET_PIPELINE_RUN_ROOT"]
    finally:
        if dump_script.exists():
            dump_script.unlink()


def test_run_scripts_does_not_rebuild_reports_when_parent_runtime_env_exists(tmp_path, monkeypatch):
    fixture_root = _fixture_root()
    record_path = tmp_path / "capture.json"
    dump_script = _write_env_dump_script(fixture_root)
    parent_run_root = Path("/tmp") / f"bet-runner-no-reports-{tmp_path.name}" / "nested" / "sandbox"

    try:
        monkeypatch.setattr(_runner, "ROOT", fixture_root)
        monkeypatch.setenv("FIXTURE_RECORD_PATH", str(record_path))
        monkeypatch.setenv("BET_PIPELINE_RUN_ROOT", str(parent_run_root))
        monkeypatch.setenv("BET_PIPELINE_DATA_DIR", str(parent_run_root / "data"))
        monkeypatch.setenv("BET_PIPELINE_COUPON_DIR", str(parent_run_root / "coupons"))
        monkeypatch.setenv("BET_PIPELINE_ARTIFACT_DIR", str(parent_run_root / "artifacts"))
        monkeypatch.setenv("BET_PIPELINE_BETTING_DAY", "2026-06-25")
        monkeypatch.setenv("BET_PIPELINE_RUN_ID", "run-parent")

        rc = _runner.run_scripts(
            ["dump_env.py"],
            date="2026-06-25",
            dry_run=True,
            allow_write=False,
            runtime_mode="DRY_RUN",
            betting_day="2026-06-25",
            run_id="run-parent",
        )

        assert rc == 0
        payload = json.loads(record_path.read_text(encoding="utf-8"))
        assert payload["BET_PIPELINE_RUN_ROOT"] == str(parent_run_root)
        assert not payload["BET_PIPELINE_RUN_ROOT"].startswith(str(fixture_root / "reports"))
        assert "reports/pipeline_runs" not in payload["BET_PIPELINE_RUN_ROOT"]
    finally:
        if dump_script.exists():
            dump_script.unlink()


def test_live_shadow_live_ack_guard_behavior_remains_unchanged(monkeypatch):
    fixture_root = _fixture_root()
    live_script = fixture_root / "scripts" / "settle_on_finish.py"
    live_script.write_text("import sys\nsys.exit(0)\n", encoding="utf-8")

    try:
        monkeypatch.setattr(_runner, "ROOT", fixture_root)
        monkeypatch.delenv("BET_PIPELINE_LIVE_ACK", raising=False)

        assert _runner.run_scripts(["settle_on_finish.py"], dry_run=True, allow_live_network=False, runtime_mode="LIVE_SHADOW") == 5

        monkeypatch.setenv("BET_PIPELINE_LIVE_ACK", "I_UNDERSTAND_LIVE_PROVIDER_CALLS")
        assert _runner.run_scripts(["settle_on_finish.py"], dry_run=True, allow_live_network=True, runtime_mode="LIVE_SHADOW") == 0
    finally:
        if live_script.exists():
            live_script.unlink()


def test_write_ack_behavior_remains_unchanged(tmp_path, monkeypatch):
    fixture_root = _fixture_root()
    record_path = tmp_path / "capture.json"

    monkeypatch.setattr(_runner, "ROOT", fixture_root)
    monkeypatch.setenv("FIXTURE_RECORD_PATH", str(record_path))
    monkeypatch.delenv("FORCE_ALLOW_WRITE", raising=False)
    monkeypatch.delenv("BET_PIPELINE_WRITE_ACK", raising=False)

    assert _runner.run_scripts(["capture_env.py"], dry_run=False, allow_write=True) == 3

    monkeypatch.setenv("BET_PIPELINE_WRITE_ACK", "I_UNDERSTAND_PRODUCTION_WRITE")
    assert _runner.run_scripts(["capture_env.py"], dry_run=False, allow_write=True) == 0
    assert record_path.exists()
