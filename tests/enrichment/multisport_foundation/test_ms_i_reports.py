import json
from pathlib import Path
from bet.enrichment.multisport_foundation.single_flight_probe_report import write_single_flight_reports

TARGET_SPORTS = {"basketball", "volleyball", "hockey", "tennis", "cs2", "dota2", "valorant"}

def test_reports_exist_and_conform_to_pretty_sorted_json(tmp_path):
    write_single_flight_reports(tmp_path)

    summary_path = tmp_path / "pass_i_summary.json"
    by_sport_path = tmp_path / "single_flight_probe_by_sport.json"

    assert summary_path.exists()
    assert by_sport_path.exists()

    # Verify pretty printing and sorted keys
    for p in [summary_path, by_sport_path]:
        text = p.read_text(encoding="utf-8")
        assert text.endswith("\n")
        assert "\n  " in text  # Multi-line indent
        data = json.loads(text)
        assert data is not None

def test_reports_cover_exactly_seven_sports(tmp_path):
    write_single_flight_reports(tmp_path)

    summary_path = tmp_path / "pass_i_summary.json"
    by_sport_path = tmp_path / "single_flight_probe_by_sport.json"

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    by_sport = json.loads(by_sport_path.read_text(encoding="utf-8"))

    assert set(summary["target_sports"]) == TARGET_SPORTS
    assert set(summary["status_by_sport"].keys()) == TARGET_SPORTS
    assert set(by_sport.keys()) == TARGET_SPORTS

def test_default_reports_have_no_live_calls_or_auth_leaks(tmp_path):
    write_single_flight_reports(tmp_path)

    combined = "\n".join(p.read_text(encoding="utf-8").lower() for p in tmp_path.glob("*.json"))

    # 1. No credentials/tokens
    for leaked in [
        "authorization",
        "bearer",
        "cookie",
        "x-api-key",
        "x-apisports-key",
        "x-rapidapi-key",
    ]:
        assert leaked not in combined, f"Found leaked header/auth term: {leaked}"

    # 2. No production activation or betting decisions enabled
    assert '"production_selectable": true' not in combined
    assert '"betting_decisions_enabled": true' not in combined
    assert '"production_activation": true' not in combined
    assert '"betting_decisions": true' not in combined

    # 3. No forbidden domain fields
    for forbidden in ["pick", "stake", "edge", "recommendation"]:
        assert forbidden not in combined, f"Forbidden domain field found: {forbidden}"

    # 4. Check for default metrics
    summary = json.loads((tmp_path / "pass_i_summary.json").read_text(encoding="utf-8"))
    assert summary["live_calls_made"] is False
    assert summary["provider_access_attempted"] is False
    assert summary["production_activation"] is False
    assert summary["betting_decisions"] is False
