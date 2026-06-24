from __future__ import annotations

import json
from pathlib import Path
from bet.enrichment.multisport_foundation import (
    verify_plan,
    verify_source_inventory,
    verify_provider_corpus,
    verify_shadow_artifacts,
    verify_activation_candidates,
    verify_live_observations,
    verify_provider_mapping,
    verify_provider_probes,
)

def test_pass_e_reports_remain_unchanged() -> None:
    plan_path = Path("reports/multisport_foundation/pass_e/provider_mapping_plan.json")
    summary_path = Path("reports/multisport_foundation/pass_e/pass_e_summary.json")

    assert plan_path.exists()
    assert summary_path.exists()

    # Read plan to check keys
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    assert plan.get("phase_id") == "MULTISPORT_PASS_E_PROVIDER_MAPPING_CONTRACTS"

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary.get("summary_version") == "ms-e-summary-v1"

def test_verifiers_remain_importable_and_pass() -> None:
    # Pass A
    res_a = verify_plan()
    assert res_a.verdict == "PASS"

    # Pass B
    res_b = verify_source_inventory()
    assert res_b.verdict == "PASS"

    # Pass E
    res_e = verify_provider_mapping()
    assert res_e.verdict == "PASS"

    # Pass F
    res_f = verify_provider_probes()
    assert res_f.verdict == "PASS"
