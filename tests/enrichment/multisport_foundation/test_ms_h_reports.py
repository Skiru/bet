import json
from pathlib import Path
from bet.enrichment.multisport_foundation.provider_authorization_report import write_authorization_reports

TARGET_SPORTS = {"basketball", "volleyball", "hockey", "tennis", "cs2", "dota2", "valorant"}

def test_reports_are_pretty_json_and_cover_target_sports(tmp_path):
    write_authorization_reports(tmp_path, env={})
    summary = tmp_path / 'pass_h_summary.json'
    by_sport = tmp_path / 'provider_access_by_sport.json'
    
    assert summary.exists()
    assert by_sport.exists()
    
    for path in [summary, by_sport]:
        text = path.read_text()
        assert text.endswith('\n')
        assert '\n  ' in text  # Multi-line / pretty printed
        data = json.loads(text)
        assert isinstance(data, dict)
        
    assert set(json.loads(summary.read_text())['target_sports']) == TARGET_SPORTS
    assert set(json.loads(by_sport.read_text())) == TARGET_SPORTS

def test_reports_do_not_contain_raw_secret_values_or_auth_header_names(tmp_path):
    write_authorization_reports(
        tmp_path,
        env={
            'API_SPORTS_KEY': 'super-secret-value',
            'PANDASCORE_TOKEN': 'another-secret-value',
            'MULTISPORT_API_SPORTS_TERMS_APPROVED': '1'
        }
    )
    combined = '\n'.join(path.read_text().lower() for path in tmp_path.glob('*.json'))
    
    forbidden_terms = [
        'super-secret-value',
        'another-secret-value',
        'authorization',
        'bearer',
        'cookie',
        'x-api-key',
        'x-apisports-key',
        'x-rapidapi-key',
        '"production_selectable": true',
        '"betting_decisions_enabled": true'
    ]
    for forbidden in forbidden_terms:
        assert forbidden not in combined, f"Forbidden term '{forbidden}' was found in the generated JSON reports."

def test_workspace_reports_exist_and_pass_validation():
    reports_dir = Path("reports/multisport_foundation/pass_h")
    summary = reports_dir / 'pass_h_summary.json'
    by_sport = reports_dir / 'provider_access_by_sport.json'
    
    assert summary.exists(), "Pass H summary report is missing from the workspace."
    assert by_sport.exists(), "Pass H provider access by sport report is missing from the workspace."
    
    summary_data = json.loads(summary.read_text())
    by_sport_data = json.loads(by_sport.read_text())
    
    assert set(summary_data['target_sports']) == TARGET_SPORTS
    assert set(by_sport_data) == TARGET_SPORTS
    
    # Run forbidden checks on actual workspace files
    combined = (summary.read_text() + "\n" + by_sport.read_text()).lower()
    forbidden_terms = [
        'authorization',
        'bearer',
        'cookie',
        'x-api-key',
        'x-apisports-key',
        'x-rapidapi-key',
        '"production_selectable": true',
        '"betting_decisions_enabled": true'
    ]
    for forbidden in forbidden_terms:
        assert forbidden not in combined, f"Forbidden term '{forbidden}' was found in the actual workspace JSON reports."
