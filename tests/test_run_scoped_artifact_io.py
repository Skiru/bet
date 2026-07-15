"""Canonical run-scoped artifact publication contract tests."""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

import pytest

from bet.pipeline.artifact_io import ArtifactPublishError, publish_run_artifact

DAY = "2026-07-13"
RUN_ID = "artifact-io-test"
TYPE = "TEST_ARTIFACT"


def _payload(**updates: object) -> dict:
    value = {
        "schema_version": 1,
        "artifact_type": TYPE,
        "betting_day": DAY,
        "run_id": RUN_ID,
        "value": 1,
    }
    value.update(updates)
    return value


def _publish(root: Path, target: Path, payload: dict | None = None):
    root.mkdir(parents=True, exist_ok=True)
    return publish_run_artifact(
        run_root=root,
        target=target,
        payload=payload or _payload(),
        betting_day=DAY,
        run_id=RUN_ID,
        artifact_type=TYPE,
    )


def test_tmp_run_root_publishes_validated_json_atomically(tmp_path: Path):
    target = tmp_path / "artifacts/result.json"
    receipt = _publish(tmp_path, target)
    assert receipt.path == target
    assert receipt.sha256 and receipt.bytes_written > 0
    assert receipt.already_present is False
    assert json.loads(target.read_text(encoding="utf-8")) == _payload()
    assert not list(target.parent.glob("*.tmp"))


def test_reports_pipeline_runs_root_is_allowed():
    reports = Path(__file__).resolve().parents[1] / "reports/pipeline_runs"
    root = reports / f"artifact-io-test-{uuid.uuid4().hex}"
    target = root / "result.json"
    try:
        assert _publish(root, target).path == target
    finally:
        target.unlink(missing_ok=True)
        root.rmdir()


def test_cross_run_traversal_and_symlink_escape_are_rejected(tmp_path: Path):
    current = tmp_path / "current"
    another = tmp_path / "another"
    current.mkdir()
    another.mkdir()
    with pytest.raises(ArtifactPublishError, match="ARTIFACT_CROSS_RUN_PATH"):
        _publish(current, another / "result.json")
    with pytest.raises(ArtifactPublishError, match="ARTIFACT_PATH_TRAVERSAL"):
        _publish(current, Path("../result.json"))

    outside = tmp_path / "outside"
    outside.mkdir()
    (current / "escape").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ArtifactPublishError, match="ARTIFACT_SYMLINK_ESCAPE"):
        _publish(current, current / "escape/result.json")


def test_crash_before_exclusive_link_never_publishes_complete_artifact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    target = tmp_path / "result.json"

    def fail_link(_source: object, _target: object) -> None:
        raise OSError("injected crash before exclusive link")

    monkeypatch.setattr(os, "link", fail_link)
    with pytest.raises(OSError, match="injected crash"):
        _publish(tmp_path, target)
    assert not target.exists()
    assert not list(tmp_path.glob("*.tmp"))


def test_immutable_republication_is_idempotent_but_conflict_blocks(tmp_path: Path):
    target = tmp_path / "result.json"
    first = _publish(tmp_path, target)
    second = _publish(tmp_path, target)
    assert second.sha256 == first.sha256
    assert second.already_present is True
    with pytest.raises(ArtifactPublishError, match="ARTIFACT_IMMUTABLE_CONFLICT"):
        _publish(tmp_path, target, _payload(value=2))


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        (_payload(schema_version=3), "ARTIFACT_SCHEMA_INVALID"),
        (_payload(betting_day="2026-07-12"), "ARTIFACT_DAY_MISMATCH"),
        (_payload(run_id="another-run"), "ARTIFACT_RUN_MISMATCH"),
        (_payload(artifact_type="OTHER"), "ARTIFACT_TYPE_MISMATCH"),
    ],
)
def test_payload_binding_failures_have_stable_codes(tmp_path: Path, payload: dict, code: str):
    with pytest.raises(ArtifactPublishError) as exc:
        _publish(tmp_path, tmp_path / "result.json", payload)
    assert exc.value.code == code
