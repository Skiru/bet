from bet.pipeline.final_artifact_consistency import validate_market_matrix_lineage


def test_old_matrix_run_id_without_lineage_blocks() -> None:
    report = validate_market_matrix_lineage({"run_id": "OLD"}, expected_current_run_id="NEW", allowed_source_run_ids={"OLD"})
    assert not report.ok
    assert any(issue.code == "MARKET_MATRIX_RUN_LINEAGE_AMBIGUOUS" for issue in report.blockers)


def test_reused_matrix_with_source_and_current_ids_passes() -> None:
    report = validate_market_matrix_lineage({"run_id": "OLD", "current_run_id": "NEW", "source_run_id": "OLD"}, expected_current_run_id="NEW", allowed_source_run_ids={"OLD"})
    assert report.ok
