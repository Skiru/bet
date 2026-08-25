import json
from pathlib import Path

def test_pass_c_summary_preserved_and_fail_closed():
    path = Path("tests/fixtures/multisport_foundation/pass_c/pass_c_summary.json")
    assert path.is_file()

    data = json.loads(path.read_text(encoding="utf-8"))
    metrics = data["metrics"]

    # Still says no live calls, no production activation, no betting decisions
    assert metrics["live_calls_made"] is False
    assert metrics["provider_access_attempted"] is False
    assert metrics["production_activation"] is False
    assert metrics["betting_decisions"] is False

def test_pass_bc_verifiers_remain_importable():
    from bet.enrichment.multisport_foundation.verifier import (
        verify_plan,
        verify_source_inventory,
        verify_shadow_artifacts,
        verify_activation_candidates,
        verify_live_observations,
    )
    assert verify_plan is not None
    assert verify_source_inventory is not None
    assert verify_shadow_artifacts is not None
    assert verify_activation_candidates is not None
    assert verify_live_observations is not None
