from bet.pipeline.final_artifact_consistency import validate_test_manifest


def test_manifest_missing_required_tests_blocks() -> None:
    report = validate_test_manifest({"test_files_run": ["tests/other.py"]}, required_test_files={"tests/test_final_artifact_cross_consistency.py"})
    assert not report.ok
    assert any(issue.code == "REQUIRED_TESTS_MISSING_FROM_MANIFEST" for issue in report.blockers)


def test_manifest_accepts_basenames() -> None:
    report = validate_test_manifest({"test_files_run": ["/tmp/tests/test_final_artifact_cross_consistency.py"]}, required_test_files={"tests/test_final_artifact_cross_consistency.py"})
    assert report.ok
