import json
from pathlib import Path
from bet.enrichment.multisport_foundation import verify_provider_mapping, verify_provider_probes

def test_pass_e_and_f_summaries_exist_and_preserved():
    pass_e = Path("tests/fixtures/multisport_foundation/pass_e/pass_e_summary.json")
    pass_f = Path("tests/fixtures/multisport_foundation/pass_f/pass_f_summary.json")

    assert pass_e.exists(), "Pass E summary report is missing."
    assert pass_f.exists(), "Pass F summary report is missing."

    # Verify Pass F summary still says live_calls_allowed = false
    f_data = json.loads(pass_f.read_text())
    assert f_data["metrics"]["live_calls_allowed"] is False, "Pass F summary must specify live_calls_allowed as False."

def test_mapping_and_probe_verifiers_pass():
    # verify_provider_mapping remains importable and PASS
    res_mapping = verify_provider_mapping()
    assert res_mapping.verdict == "PASS", f"verify_provider_mapping failed: {res_mapping.failed_requirements}"

    # verify_provider_probes remains importable and PASS
    res_probes = verify_provider_probes()
    assert res_probes.verdict == "PASS", f"verify_provider_probes failed: {res_probes.failed_requirements}"
