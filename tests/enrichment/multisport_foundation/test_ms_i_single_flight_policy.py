import pytest
from bet.enrichment.multisport_foundation.single_flight_probe import (
    SingleFlightProbePolicy,
    default_policy_for_sport,
)

def test_single_flight_policy_defaults():
    p = default_policy_for_sport("basketball")
    assert p.max_requests == 1
    assert p.sanitized_probe_only is True
    assert p.production_selectable is False
    assert p.betting_decisions_enabled is False
    assert p.allow_real_network is False

def test_single_flight_policy_invalid_raises():
    # max_requests must be 1
    with pytest.raises(ValueError, match="single_flight_max_requests_must_equal_1"):
        SingleFlightProbePolicy(
            sport="basketball", provider_key="key", route_key="route",
            source_access_status="AUTH", source_mapping_status="READY",
            max_requests=2
        )

    # sanitized_probe_only must be True
    with pytest.raises(ValueError, match="sanitized_probe_only_required"):
        SingleFlightProbePolicy(
            sport="basketball", provider_key="key", route_key="route",
            source_access_status="AUTH", source_mapping_status="READY",
            sanitized_probe_only=False
        )

    # production_selectable must be False
    with pytest.raises(ValueError, match="production_selectable_forbidden"):
        SingleFlightProbePolicy(
            sport="basketball", provider_key="key", route_key="route",
            source_access_status="AUTH", source_mapping_status="READY",
            production_selectable=True
        )

    # betting_decisions_enabled must be False
    with pytest.raises(ValueError, match="betting_decisions_forbidden"):
        SingleFlightProbePolicy(
            sport="basketball", provider_key="key", route_key="route",
            source_access_status="AUTH", source_mapping_status="READY",
            betting_decisions_enabled=True
        )
