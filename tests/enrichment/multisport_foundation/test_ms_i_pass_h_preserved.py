import json
from pathlib import Path
from bet.enrichment.multisport_foundation import (
    verify_provider_access_gate,
    verify_provider_mapping,
    verify_provider_probes,
    verify_single_flight_probes,
)

def test_pass_h_reports_exist_and_unchanged():
    pass_h_summary_path = Path("tests/fixtures/multisport_foundation/pass_h/pass_h_summary.json")
    provider_access_path = Path("tests/fixtures/multisport_foundation/pass_h/provider_access_by_sport.json")
    
    assert pass_h_summary_path.exists()
    assert provider_access_path.exists()
    
    summary = json.loads(pass_h_summary_path.read_text(encoding="utf-8"))
    assert summary["phase_id"] == "MULTISPORT_PASS_H_PROVIDER_ACCESS_GATE"
    assert summary["live_calls_made"] is False
    assert summary["provider_access_attempted"] is False

def test_verifiers_pass():
    # verify_provider_access_gate remains importable and PASS
    h_res = verify_provider_access_gate()
    assert h_res.verdict == "PASS", f"verify_provider_access_gate failed: {h_res.failed_requirements}"
    
    # verify_provider_mapping remains importable and PASS
    e_res = verify_provider_mapping()
    assert e_res.verdict == "PASS", f"verify_provider_mapping failed: {e_res.failed_requirements}"
    
    # verify_provider_probes remains importable and PASS
    f_res = verify_provider_probes()
    assert f_res.verdict == "PASS", f"verify_provider_probes failed: {f_res.failed_requirements}"

    # New single flight verifier passes
    i_res = verify_single_flight_probes()
    assert i_res.verdict == "PASS", f"verify_single_flight_probes failed: {i_res.failed_requirements}"
