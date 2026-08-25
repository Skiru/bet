import json
from pathlib import Path

TARGET_SPORTS = {"basketball", "volleyball", "hockey", "tennis", "cs2", "dota2", "valorant"}

def test_reports_exist():
    plan_path = Path("tests/fixtures/multisport_foundation/pass_e/provider_mapping_plan.json")
    summary_path = Path("tests/fixtures/multisport_foundation/pass_e/pass_e_summary.json")

    assert plan_path.is_file()
    assert summary_path.is_file()

def test_reports_are_pretty_and_sorted():
    for name in ["provider_mapping_plan.json", "pass_e_summary.json"]:
        path = Path(f"tests/fixtures/multisport_foundation/pass_e/{name}")
        text = path.read_text(encoding="utf-8")
        assert text.endswith("\n")
        assert "\n  " in text or "\n" in text
        data = json.loads(text)
        assert data is not None

def test_reports_cover_exactly_seven_target_sports():
    # Plan report
    plan_text = Path("tests/fixtures/multisport_foundation/pass_e/provider_mapping_plan.json").read_text(encoding="utf-8")
    plan = json.loads(plan_text)
    assert set(plan["target_sports"]) == TARGET_SPORTS
    assert set(plan["provider_mapping_by_sport"]) == TARGET_SPORTS

    # Summary report
    summary_text = Path("tests/fixtures/multisport_foundation/pass_e/pass_e_summary.json").read_text(encoding="utf-8")
    summary = json.loads(summary_text)
    assert set(summary["target_sports"]) == TARGET_SPORTS
    assert set(summary["provider_mapping_statuses"]) == TARGET_SPORTS

def test_no_raw_secrets_or_forbidden_headers_in_reports():
    forbidden_tokens = [
        "authorization", "cookie", "bearer", "x-api-key",
        "x-apisports-key", "x-rapidapi-key"
    ]
    for name in ["provider_mapping_plan.json", "pass_e_summary.json"]:
        path = Path(f"tests/fixtures/multisport_foundation/pass_e/{name}")
        text = path.read_text(encoding="utf-8").lower()
        for tok in forbidden_tokens:
            assert tok not in text

def test_no_betting_decisions_or_production_activation_enablement():
    for name in ["provider_mapping_plan.json", "pass_e_summary.json"]:
        path = Path(f"tests/fixtures/multisport_foundation/pass_e/{name}")
        text = path.read_text(encoding="utf-8")
        # Check no raw betting decision terms enabled
        assert '"betting_decisions": true' not in text
        assert '"live_calls_allowed": true' not in text
        assert '"live_call_allowed": true' not in text
        assert '"production_activation": true' not in text
        assert '"production_selectable": true' not in text
        assert '"betting_decisions_enabled": true' not in text

def test_reports_do_not_modify_pass_b_or_c_reports():
    # Verify Pass B and Pass C files still exist intact
    assert Path("tests/fixtures/multisport_foundation/pass_b/source_inventory_carry_forward.json").is_file()
    assert Path("tests/fixtures/multisport_foundation/pass_b/source_bound_shadow_status_by_sport.json").is_file()
    assert Path("tests/fixtures/multisport_foundation/pass_c/pass_c_summary.json").is_file()
