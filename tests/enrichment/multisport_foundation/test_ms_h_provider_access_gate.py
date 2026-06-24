from bet.enrichment.multisport_foundation.provider_authorization import (
    ProviderAuthorizationStatus,
    authorize_probe,
    build_authorization_report,
    default_authorization_specs,
    validate_authorization_report,
)

TARGET_SPORTS = {"basketball", "volleyball", "hockey", "tennis", "cs2", "dota2", "valorant"}

def test_default_authorization_report_covers_exactly_seven_sports():
    r = build_authorization_report({})
    assert set(r['target_sports']) == TARGET_SPORTS
    assert set(r['provider_access_by_sport']) == TARGET_SPORTS
    assert validate_authorization_report(r) == []

def test_default_state_makes_no_live_or_provider_access():
    r = build_authorization_report({})
    assert r['live_calls_made'] is False
    assert r['provider_access_attempted'] is False
    assert r['production_activation'] is False
    assert r['betting_decisions'] is False
    for items in r['provider_access_by_sport'].values():
        for item in items:
            assert item['allow_real_network'] is False
            assert item['max_requests'] <= 1
            assert item['production_selectable'] is False
            assert item['betting_decisions_enabled'] is False

def test_default_state_is_blocked_no_credentials_for_all_sports():
    r = build_authorization_report({})
    assert set(r['status_by_sport'].values()) == {ProviderAuthorizationStatus.BLOCKED_NO_CREDENTIALS}

def test_api_sports_shared_key_still_requires_terms_scope_and_operator_approval():
    r = build_authorization_report({'API_SPORTS_KEY': 'secret'})
    for s in ['basketball', 'volleyball', 'hockey', 'tennis']:
        assert r['status_by_sport'][s] == ProviderAuthorizationStatus.BLOCKED_TERMS_REVIEW_NOT_APPROVED

def test_api_sports_becomes_authorized_only_after_all_gates():
    env = {
        'API_SPORTS_KEY': 'secret',
        'MULTISPORT_API_SPORTS_TERMS_APPROVED': '1',
        'MULTISPORT_API_SPORTS_DATA_SCOPE_APPROVED': '1',
        'MULTISPORT_API_SPORTS_OPERATOR_APPROVED': '1'
    }
    r = build_authorization_report(env)
    for s in ['basketball', 'volleyball', 'hockey', 'tennis']:
        assert r['status_by_sport'][s] == ProviderAuthorizationStatus.AUTHORIZED_FOR_SANITIZED_LIVE_PROBE
    for s in ['cs2', 'dota2', 'valorant']:
        assert r['status_by_sport'][s] == ProviderAuthorizationStatus.BLOCKED_NO_CREDENTIALS

def test_pandascore_requires_token_terms_scope_and_operator_approval():
    env = {
        'PANDASCORE_TOKEN': 'secret',
        'MULTISPORT_PANDASCORE_TERMS_APPROVED': '1',
        'MULTISPORT_PANDASCORE_DATA_SCOPE_APPROVED': '1',
        'MULTISPORT_PANDASCORE_OPERATOR_APPROVED': '1'
    }
    r = build_authorization_report(env)
    for s in ['cs2', 'dota2', 'valorant']:
        assert r['status_by_sport'][s] == ProviderAuthorizationStatus.AUTHORIZED_FOR_SANITIZED_LIVE_PROBE

def test_authorization_never_enables_production_or_betting():
    env = {
        'API_SPORTS_KEY': 'secret',
        'MULTISPORT_API_SPORTS_TERMS_APPROVED': '1',
        'MULTISPORT_API_SPORTS_DATA_SCOPE_APPROVED': '1',
        'MULTISPORT_API_SPORTS_OPERATOR_APPROVED': '1',
        'PANDASCORE_TOKEN': 'secret',
        'MULTISPORT_PANDASCORE_TERMS_APPROVED': '1',
        'MULTISPORT_PANDASCORE_DATA_SCOPE_APPROVED': '1',
        'MULTISPORT_PANDASCORE_OPERATOR_APPROVED': '1'
    }
    r = build_authorization_report(env)
    assert validate_authorization_report(r) == []
    for items in r['provider_access_by_sport'].values():
        for item in items:
            assert item['allow_real_network'] is False
            assert item['production_selectable'] is False
            assert item['betting_decisions_enabled'] is False
            assert item['next_allowed_phase'] in {'pass_i_authorized_single_flight_probe', 'none'}

def test_individual_status_priority_terms_then_scope_then_operator():
    [b] = [s for s in default_authorization_specs() if s.sport == 'basketball']
    assert authorize_probe(b, {'API_SPORTS_KEY': 'secret'}).status == ProviderAuthorizationStatus.BLOCKED_TERMS_REVIEW_NOT_APPROVED
    assert authorize_probe(b, {'API_SPORTS_KEY': 'secret', 'MULTISPORT_API_SPORTS_TERMS_APPROVED': '1'}).status == ProviderAuthorizationStatus.BLOCKED_DATA_SCOPE_NOT_APPROVED
    assert authorize_probe(b, {'API_SPORTS_KEY': 'secret', 'MULTISPORT_API_SPORTS_TERMS_APPROVED': '1', 'MULTISPORT_API_SPORTS_DATA_SCOPE_APPROVED': '1'}).status == ProviderAuthorizationStatus.BLOCKED_OPERATOR_APPROVAL_MISSING
