import hashlib
import json
from datetime import UTC, datetime

import pytest

from bet.pipeline.reusable_stage_output import ReusableStageOutputValidator, ReuseStatus


def _case(tmp_path):
    root = tmp_path / "artifacts"
    root.mkdir()
    output = root / "output.json"
    output.write_text('{"value":1}', encoding="utf-8")
    output_sha = hashlib.sha256(output.read_bytes()).hexdigest()
    receipt = root / "receipt.json"
    receipt_payload = {
        "canonical_event_id": "event-1",
        "stage_id": "S2",
        "output_sha256": output_sha,
        "input_fingerprint": "fingerprint-1",
        "producer": "bet-pipeline",
        "run_id": "run-1",
    }
    receipt.write_text(json.dumps(receipt_payload, sort_keys=True), encoding="utf-8")
    receipt_sha = hashlib.sha256(receipt.read_bytes()).hexdigest()
    state = {
        "canonical_event_id": "event-1",
        "stage_id": "S2",
        "status": "PASS",
        "input_fingerprint": "fingerprint-1",
        "stage_contract_version": "v1",
        "model_registry_sha256": "model-1",
        "provider_config_sha256": "provider-1",
        "policy_config_sha256": "policy-1",
        "output_sha256": output_sha,
        "receipt_sha256": receipt_sha,
        "completed_at": "2026-07-30T10:00:00+00:00",
        "dependency_status": "CURRENT",
        "run_id": "run-1",
    }
    artifact = {"path": str(output), "sha256": output_sha}
    receipt_meta = {"path": str(receipt), "sha256": receipt_sha}
    expected = {
        "canonical_event_id": "event-1",
        "stage_id": "S2",
        "input_fingerprint": "fingerprint-1",
        "stage_contract_version": "v1",
        "model_registry_sha256": "model-1",
        "provider_config_sha256": "provider-1",
        "policy_config_sha256": "policy-1",
        "producer": "bet-pipeline",
        "run_id": "run-1",
        "artifact_root": root,
        "latest_upstream_at": datetime(2026, 7, 30, 9, 0, tzinfo=UTC),
    }
    return state, artifact, receipt_meta, expected


@pytest.mark.parametrize(
    ("case_id", "mutation", "expected"),
    [
        ("34-global-pass", lambda s, a, r, e: s.clear(), ReuseStatus.MISSING_STATE),
        ("35-analysis-row", lambda s, a, r, e: s.clear(), ReuseStatus.MISSING_STATE),
        ("36-gate-row", lambda s, a, r, e: s.clear(), ReuseStatus.MISSING_STATE),
        (
            "37-output-missing",
            lambda s, a, r, e: a.update(path=str(e["artifact_root"] / "missing")),
            ReuseStatus.OUTPUT_MISSING,
        ),
        (
            "38-output-hash",
            lambda s, a, r, e: a.update(sha256="bad"),
            ReuseStatus.OUTPUT_HASH_MISMATCH,
        ),
        (
            "39-output-directory",
            lambda s, a, r, e: a.update(path=str(e["artifact_root"])),
            ReuseStatus.OUTPUT_MISSING,
        ),
        (
            "40-unsafe-output",
            lambda s, a, r, e: a.update(
                path=str(e["artifact_root"].parent / "outside")
            ),
            ReuseStatus.UNSAFE_PATH,
        ),
        (
            "41-receipt-missing",
            lambda s, a, r, e: r.update(
                path=str(e["artifact_root"] / "missing-receipt")
            ),
            ReuseStatus.RECEIPT_MISSING,
        ),
        (
            "42-receipt-hash",
            lambda s, a, r, e: r.update(sha256="bad"),
            ReuseStatus.RECEIPT_HASH_MISMATCH,
        ),
        (
            "45-fingerprint",
            lambda s, a, r, e: e.update(input_fingerprint="changed"),
            ReuseStatus.FINGERPRINT_MISMATCH,
        ),
        (
            "46-contract",
            lambda s, a, r, e: e.update(stage_contract_version="v2"),
            ReuseStatus.CONTRACT_MISMATCH,
        ),
        (
            "47-model",
            lambda s, a, r, e: e.update(model_registry_sha256="changed"),
            ReuseStatus.MODEL_MISMATCH,
        ),
        (
            "48-provider",
            lambda s, a, r, e: e.update(provider_config_sha256="changed"),
            ReuseStatus.CONFIG_MISMATCH,
        ),
        (
            "49-policy",
            lambda s, a, r, e: e.update(policy_config_sha256="changed"),
            ReuseStatus.CONFIG_MISMATCH,
        ),
        (
            "50-upstream-newer",
            lambda s, a, r, e: e.update(
                latest_upstream_at=datetime(2026, 7, 30, 11, 0, tzinfo=UTC)
            ),
            ReuseStatus.UPSTREAM_NEWER,
        ),
        (
            "51-dependency-stale",
            lambda s, a, r, e: s.update(dependency_status="STALE"),
            ReuseStatus.DEPENDENCY_STALE,
        ),
        (
            "52-invalid-status",
            lambda s, a, r, e: s.update(status="FAILED"),
            ReuseStatus.INVALID_STATUS,
        ),
    ],
)
def test_reuse_rejects_invalid_state(tmp_path, case_id, mutation, expected):
    state, artifact, receipt, expected_values = _case(tmp_path)
    mutation(state, artifact, receipt, expected_values)
    result = ReusableStageOutputValidator().validate(
        state, artifact, receipt, **expected_values
    )
    assert result.status is expected


@pytest.mark.parametrize("field", ["canonical_event_id", "stage_id"])
def test_43_44_receipt_bindings(tmp_path, field):
    state, artifact, receipt, expected = _case(tmp_path)
    payload = json.loads(open(receipt["path"], encoding="utf-8").read())
    payload[field] = "other"
    open(receipt["path"], "w", encoding="utf-8").write(
        json.dumps(payload, sort_keys=True)
    )
    receipt["sha256"] = hashlib.sha256(open(receipt["path"], "rb").read()).hexdigest()
    state["receipt_sha256"] = receipt["sha256"]
    result = ReusableStageOutputValidator().validate(
        state, artifact, receipt, **expected
    )
    assert result.status is ReuseStatus.RECEIPT_BINDING_MISMATCH


def test_53_valid_reuse(tmp_path):
    state, artifact, receipt, expected = _case(tmp_path)
    assert (
        ReusableStageOutputValidator()
        .validate(state, artifact, receipt, **expected)
        .status
        is ReuseStatus.REUSABLE
    )


def test_54_deterministic_reuse(tmp_path):
    state, artifact, receipt, expected = _case(tmp_path)
    validator = ReusableStageOutputValidator()
    assert validator.validate(
        state, artifact, receipt, **expected
    ) == validator.validate(state, artifact, receipt, **expected)


@pytest.mark.parametrize(
    "field",
    ["participant_identity", "kickoff", "provider_evidence", "canonical_status"],
)
def test_55_58_fingerprint_changes_invalidate_reuse(tmp_path, field):
    state, artifact, receipt, expected = _case(tmp_path)
    expected["input_fingerprint"] = f"changed-{field}"
    result = ReusableStageOutputValidator().validate(
        state, artifact, receipt, **expected
    )
    assert result.status is ReuseStatus.FINGERPRINT_MISMATCH
