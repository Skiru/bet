from __future__ import annotations

import pytest
from bet.enrichment.multisport_foundation import ProviderProbePolicy

def test_default_probe_policy() -> None:
    policy = ProviderProbePolicy(
        provider_key="api-sports-family",
        sport="basketball",
        route_key="api_basketball_games",
    )
    assert policy.allow_real_network is False
    assert policy.terms_review_approved is False
    assert policy.max_requests <= 1
    assert policy.sanitized_probe_only is True
    assert policy.production_selectable is False
    assert policy.betting_decisions_enabled is False

def test_invalid_max_requests_raises_value_error() -> None:
    with pytest.raises(ValueError, match="max_requests must be <= 1"):
        ProviderProbePolicy(
            provider_key="api-sports-family",
            sport="basketball",
            route_key="api_basketball_games",
            max_requests=2,
        )

def test_invalid_sanitized_probe_only_raises_value_error() -> None:
    with pytest.raises(ValueError, match="sanitized_probe_only must be true"):
        ProviderProbePolicy(
            provider_key="api-sports-family",
            sport="basketball",
            route_key="api_basketball_games",
            sanitized_probe_only=False,
        )

def test_invalid_production_selectable_raises_value_error() -> None:
    with pytest.raises(ValueError, match="production_selectable must always be false"):
        ProviderProbePolicy(
            provider_key="api-sports-family",
            sport="basketball",
            route_key="api_basketball_games",
            production_selectable=True,
        )

def test_invalid_betting_decisions_enabled_raises_value_error() -> None:
    with pytest.raises(ValueError, match="betting_decisions_enabled must always be false"):
        ProviderProbePolicy(
            provider_key="api-sports-family",
            sport="basketball",
            route_key="api_basketball_games",
            betting_decisions_enabled=True,
        )
