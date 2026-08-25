def test_identity_receipt_is_hash_bound_and_secret_free(tmp_path):
    from bet.pipeline.runtime_execution import (
        RuntimeExecutionContext,
        write_runtime_identity_receipt,
    )

    root = tmp_path / "run"
    root.mkdir()
    context = RuntimeExecutionContext.for_test(
        run_root=root, run_id="run-1", plan_id="plan-1"
    )
    receipt = write_runtime_identity_receipt(context, "S2")
    text = receipt.read_text(encoding="utf-8")
    assert "I_UNDERSTAND" not in text
    assert "runtime_context_sha256" in text
