from pathlib import Path
from bet.pipeline.final_artifact_consistency import scan_artifact_hygiene


def test_nested_absolute_path_artifacts_are_blocked(tmp_path: Path) -> None:
    bad = tmp_path / "run" / "Users" / "mkoziol" / "projects" / "bet" / "artifact.json"
    bad.parent.mkdir(parents=True)
    bad.write_text("{}", encoding="utf-8")
    report = scan_artifact_hygiene(tmp_path / "run")
    assert not report.ok
    assert any(issue.code == "NESTED_ABSOLUTE_PATH_ARTIFACTS" for issue in report.blockers)


def test_ds_store_and_pycache_are_warnings_not_blockers(tmp_path: Path) -> None:
    root = tmp_path / "run"
    (root / "__pycache__").mkdir(parents=True)
    (root / "__pycache__" / "x.pyc").write_bytes(b"x")
    (root / ".DS_Store").write_bytes(b"x")
    report = scan_artifact_hygiene(root)
    assert report.ok
    assert {issue.code for issue in report.warnings} == {"PYCACHE_IN_EVIDENCE", "DS_STORE_IN_EVIDENCE"}
