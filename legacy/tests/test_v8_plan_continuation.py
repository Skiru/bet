"""Test suite for plan and continuation contract defects (B12, B13, B15, B16, B21)."""

import sqlite3
from pathlib import Path
import pytest


def test_b12_plan_continuation_status_allowlist_mismatch():
    """B12: plan and continuation maintain different raw-status allowlists."""
    try:
        from bet.pipeline.event_runtime_contract import (
            normalize_provider_status,
            is_status_allowed_for_plan,
            is_status_allowed_for_continuation,
            CanonicalEventStatus,
        )
    except (ImportError, ModuleNotFoundError):
        pytest.fail("B12 defect: status allowlist helpers missing in bet.pipeline.event_runtime_contract", pytrace=False)

    # PENDING status
    p_status = normalize_provider_status("PENDING")
    plan_ok_pending = is_status_allowed_for_plan(p_status)
    cont_ok_pending = is_status_allowed_for_continuation(p_status)
    assert plan_ok_pending == cont_ok_pending, f"B12 defect: PENDING allowed for plan ({plan_ok_pending}) vs continuation ({cont_ok_pending})"

    # NS status
    ns_status = normalize_provider_status("NS")
    plan_ok_ns = is_status_allowed_for_plan(ns_status)
    cont_ok_ns = is_status_allowed_for_continuation(ns_status)
    assert plan_ok_ns == cont_ok_ns, f"B12 defect: NS allowed for plan ({plan_ok_ns}) vs continuation ({cont_ok_ns})"


def test_b13_post_and_awd_enter_analyze_from_s2():
    """B13: raw POST and AWD can enter ANALYZE_FROM_S2."""
    try:
        from bet.pipeline.event_runtime_contract import classify_event_eligibility
    except (ImportError, ModuleNotFoundError):
        pytest.fail("B13 defect: classify_event_eligibility missing in bet.pipeline.event_runtime_contract", pytrace=False)

    # POST (postponed)
    res_post = classify_event_eligibility(
        raw_provider_status="POST",
        canonical_status="POSTPONED",
        observed_kickoff="2026-07-30T18:00:00Z",
    )
    assert not res_post.is_eligible, "B13 defect: raw POST entered ANALYZE_FROM_S2"
    assert res_post.routing_status != "ANALYZE_FROM_S2"

    # AWD (awarded)
    res_awd = classify_event_eligibility(
        raw_provider_status="AWD",
        canonical_status="AWARDED_TERMINAL",
        observed_kickoff="2026-07-30T18:00:00Z",
    )
    assert not res_awd.is_eligible, "B13 defect: raw AWD entered ANALYZE_FROM_S2"
    assert res_awd.routing_status != "ANALYZE_FROM_S2"


def test_b15_continuation_lacks_fresh_provider_revalidation():
    """B15: continuation does not perform fresh provider revalidation."""
    try:
        from bet.pipeline.orchestrator import run_continuation_preflight
    except (ImportError, ModuleNotFoundError, AttributeError):
        pytest.fail("B15 defect: run_continuation_preflight missing or does not enforce fresh provider revalidation", pytrace=False)

    # Run continuation preflight when provider revalidation fails or returns stale evidence
    res = run_continuation_preflight(
        plan_id="plan_1",
        run_id="run_1",
        force_stale_provider=True,
    )
    assert res.status == "BLOCKED"
    assert "PROVIDER_RECHECK_REQUIRED" in res.blocker or "PLAN_REFRESH_REQUIRED" in res.blocker


def test_b16_queue_mutation_without_plan_refresh_required():
    """B16: continuation can alter the queue and continue under the previous plan identity."""
    try:
        from bet.pipeline.orchestrator import verify_continuation_queue
    except (ImportError, ModuleNotFoundError, AttributeError):
        pytest.fail("B16 defect: verify_continuation_queue missing or queue mutation fails silently", pytrace=False)

    plan_events = ["evt_1", "evt_2"]
    current_events = ["evt_1"]  # evt_2 became invalid / dropped
    
    status, blocker = verify_continuation_queue(plan_events=plan_events, current_events=current_events)
    assert status == "BLOCKED", "B16 defect: queue mutation did not block continuation"
    assert blocker == "PLAN_REFRESH_REQUIRED", f"B16 defect: expected PLAN_REFRESH_REQUIRED, got {blocker}"


def test_b21_creating_plan_unlinks_existing_shadow_db(tmp_path):
    """B21: creating or restarting a plan can unlink an existing shadow database."""
    try:
        from bet.pipeline.orchestrator import create_runtime_analysis_shadow_db
    except (ImportError, ModuleNotFoundError, AttributeError):
        pytest.fail("B21 defect: create_runtime_analysis_shadow_db missing", pytrace=False)

    shadow_db_path = tmp_path / "run_shadow.db"
    shadow_db_path.write_text("existing shadow data")

    # Attempting to create shadow DB at existing path without explicit new run ID must fail closed
    with pytest.raises((FileExistsError, RuntimeError, ValueError), match="SHADOW_DB_EXISTS|CANNOT_OVERWRITE"):
        create_runtime_analysis_shadow_db(target_path=shadow_db_path, overwrite=False)
