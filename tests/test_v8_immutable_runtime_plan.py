import json
from datetime import timedelta

import pytest

from bet.pipeline.runtime_plan import (
    FrozenSelectedEvent,
    MaterialProviderState,
    RuntimePlanRepository,
    RuntimePlanService,
    RuntimePlanStatus,
    selected_event_set_sha256,
)
from tests._c6_helpers import PLAN_NOW, build_plan


def test_plan_persists_all_immutable_bindings(tmp_path):
    built = build_plan(tmp_path)
    row = RuntimePlanRepository(built["conn"]).get("plan-1")
    assert row["status"] == "PLANNED"
    assert row["selected_event_count"] == 1
    assert row["selection_ledger_sha256"]
    assert row["runtime_s1e_sha256"]
    assert row["plan_checkpoint_sha256"]
    assert row["provider_observation_set_sha256"]
    assert row["selected_event_set_sha256"]


def test_selected_event_digest_is_order_independent():
    state = MaterialProviderState(
        "provider",
        "id",
        "SCHEDULED",
        "2027-07-30T14:00:00Z",
        "p",
        None,
        "SUCCESS",
        "SUCCESS",
        "evidence",
    )
    first = FrozenSelectedEvent("1", 1, "ANALYZE_FROM_S2", "fp1", "c1", (state,), {})
    second = FrozenSelectedEvent("2", 2, "ANALYZE_FROM_S2", "fp2", "c2", (state,), {})
    assert selected_event_set_sha256([first, second]) == selected_event_set_sha256(
        [second, first]
    )


def test_evidence_hash_binds_plan_but_not_material_state():
    base = MaterialProviderState(
        "provider",
        "id",
        "SCHEDULED",
        "2027-07-30T14:00:00Z",
        "participants",
        "competition",
        "SUCCESS",
        "SUCCESS",
        "evidence-a",
    )
    refreshed = MaterialProviderState(
        **{**base.__dict__, "provider_evidence_sha256": "evidence-b"}
    )
    first = FrozenSelectedEvent("1", 1, "ANALYZE_FROM_S2", "fp", "chain", (base,), {})
    second = FrozenSelectedEvent(
        "1", 1, "ANALYZE_FROM_S2", "fp", "chain", (refreshed,), {}
    )
    assert base.fingerprint == refreshed.fingerprint
    assert selected_event_set_sha256([first]) != selected_event_set_sha256([second])


def test_illegal_state_transitions_are_blocked(tmp_path):
    built = build_plan(tmp_path)
    repo = RuntimePlanRepository(built["conn"])
    with pytest.raises(ValueError, match="ILLEGAL_PLAN_STATE_TRANSITION"):
        repo.transition("plan-1", RuntimePlanStatus.PLANNED, RuntimePlanStatus.CONSUMED)


def test_duplicate_run_id_is_blocked(tmp_path):
    built = build_plan(tmp_path)
    row = RuntimePlanRepository(built["conn"]).get("plan-1")
    row["plan_id"] = "plan-2"
    row["status"] = "CREATING"
    with pytest.raises(Exception):
        RuntimePlanRepository(built["conn"]).insert_creating(row)


def test_invalid_plan_age_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="PLAN_EXPIRY_INVALID"):
        build_plan(tmp_path, maximum_age=timedelta(0))


def test_snapshot_json_is_canonical_and_bound(tmp_path):
    built = build_plan(tmp_path)
    row = RuntimePlanRepository(built["conn"]).get("plan-1")
    payload = json.loads(open(row["plan_snapshot_path"], encoding="utf-8").read())
    assert payload["selected_event_set_sha256"] == row["selected_event_set_sha256"]


def test_resume_metadata_key_order_does_not_change_digest():
    state = MaterialProviderState(
        "provider",
        "id",
        "SCHEDULED",
        "2027-07-30T14:00:00Z",
        "participants",
        None,
        "SUCCESS",
        "SUCCESS",
        "evidence",
    )
    first = FrozenSelectedEvent(
        "1", 1, "ANALYZE_FROM_S2", "fp", "chain", (state,), {"a": 1, "b": 2}
    )
    second = FrozenSelectedEvent(
        "1", 1, "ANALYZE_FROM_S2", "fp", "chain", (state,), {"b": 2, "a": 1}
    )
    assert selected_event_set_sha256([first]) == selected_event_set_sha256([second])


def test_second_freeze_for_same_run_is_rejected(tmp_path):
    built = build_plan(tmp_path)
    row = RuntimePlanRepository(built["conn"]).get("plan-1")
    assert row["status"] == "PLANNED"
    with pytest.raises(FileExistsError, match="PLAN_RUN_COLLISION"):
        RuntimePlanService().freeze_existing_plan(
            conn=built["conn"],
            plan_id="plan-2",
            run_id="run-1",
            betting_date="2027-07-30",
            canonical_db_path=built["canonical"],
            canonical_db_sha256=row["canonical_db_sha256_at_snapshot"],
            shadow_db_path=built["shadow"],
            shadow_db_initial_sha256=row["shadow_db_initial_sha256"],
            selection_ledger_path=built["selection"],
            runtime_s1e_path=built["runtime_s1e"],
            plan_checkpoint_path=built["checkpoint"],
            created_at_utc=PLAN_NOW,
            classification_policy_sha256="policy-1",
        )
