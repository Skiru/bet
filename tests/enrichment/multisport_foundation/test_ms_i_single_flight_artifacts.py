import os
import pytest
from bet.enrichment.multisport_foundation.single_flight_probe import (
    SingleFlightProbeStatus,
    SingleFlightProbeArtifact,
    SingleFlightProbePolicy,
    default_policy_for_sport,
    run_single_flight_probe,
)

class FakeTransport:
    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def get(self, **kwargs):
        self.calls += 1
        return self.payload

def enabled_policy(sport="basketball"):
    p = default_policy_for_sport(
        sport,
        access_status="AUTHORIZED_FOR_SANITIZED_LIVE_PROBE",
        mapping_status="MAPPING_READY_FOR_SANITIZED_PROBE"
    )
    object.__setattr__(p, "allow_real_network", True)
    return p

def test_default_current_pass_h_blocked_state_maps_every_sport():
    # Pass H default has all seven sports BLOCKED_NO_CREDENTIALS.
    # Therefore run_single_flight_probe with default policy must show SINGLE_FLIGHT_BLOCKED_ACCESS_GATE
    for sport in ["basketball", "volleyball", "hockey", "tennis", "cs2", "dota2", "valorant"]:
        p = default_policy_for_sport(sport)
        a = run_single_flight_probe(p)
        assert a.status == SingleFlightProbeStatus.SINGLE_FLIGHT_BLOCKED_ACCESS_GATE
        assert a.live_call_made is False
        assert a.provider_access_attempted is False

def test_authorized_access_still_blocks_without_operator_network_flag():
    # Set up access = authorized and mapping = ready, but no allowance flag
    p = default_policy_for_sport(
        "basketball",
        access_status="AUTHORIZED_FOR_SANITIZED_LIVE_PROBE",
        mapping_status="MAPPING_READY_FOR_SANITIZED_PROBE"
    )
    # allow_real_network is false by default in policy, and operator_network_flag defaults to false
    a = run_single_flight_probe(p)
    assert a.status == SingleFlightProbeStatus.SINGLE_FLIGHT_BLOCKED_OPERATOR_FLAG
    assert a.live_call_made is False
    assert a.provider_access_attempted is False

    # Policy enabled, but operator_network_flag is false
    p_enabled = enabled_policy()
    a_gated = run_single_flight_probe(p_enabled, operator_network_flag=False)
    assert a_gated.status == SingleFlightProbeStatus.SINGLE_FLIGHT_BLOCKED_OPERATOR_FLAG
    assert a_gated.live_call_made is False

def test_mapping_not_ready_blocks_before_operator_flag():
    p = default_policy_for_sport(
        "basketball",
        access_status="AUTHORIZED_FOR_SANITIZED_LIVE_PROBE",
        mapping_status="BLOCKED_NO_CREDENTIALS"
    )
    a = run_single_flight_probe(p, operator_network_flag=True)
    assert a.status == SingleFlightProbeStatus.SINGLE_FLIGHT_BLOCKED_MAPPING_NOT_READY
    assert a.live_call_made is False
    assert a.provider_access_attempted is False

def test_no_transport_blocks_without_provider_attempt():
    a = run_single_flight_probe(enabled_policy(), operator_network_flag=True, transport=None)
    assert a.status == SingleFlightProbeStatus.SINGLE_FLIGHT_BLOCKED_TRANSPORT_UNAVAILABLE
    assert a.provider_access_attempted is False

def test_successful_synthetic_transport_captures_only_minimum_facts():
    t = FakeTransport({
        "fixture_id": "1",
        "home_team": "A",
        "away_team": "B",
        "start_time": "2026-01-01T00:00:00Z",
        "ignored_raw_secret_value": "secret"
    })
    a = run_single_flight_probe(enabled_policy(), operator_network_flag=True, transport=t)
    assert a.status == SingleFlightProbeStatus.SINGLE_FLIGHT_RESULT_CAPTURED_SANITIZED
    assert a.live_call_made is True
    assert a.provider_access_attempted is True
    assert a.sanitized_response_envelope["raw_payload_persisted"] is False
    # Confirm raw value of ignored keys or raw credentials is NOT stored or leaked
    assert "ignored_raw_secret_value" not in str(a.sanitized_response_envelope)
    assert set(a.proof_fields_observed) == {"fixture_id", "home_team", "away_team", "start_time"}
    assert t.calls == 1

def test_forbidden_domain_fields_block_result():
    for field_name in ["odds", "prediction", "predictions", "pick", "stake", "edge", "recommendation", "bookmaker"]:
        payload = {
            "fixture_id": "1",
            "home_team": "A",
            "away_team": "B",
            "start_time": "2026",
            field_name: "1.5"
        }
        t = FakeTransport(payload)
        a = run_single_flight_probe(enabled_policy(), operator_network_flag=True, transport=t)
        assert a.status == SingleFlightProbeStatus.SINGLE_FLIGHT_BLOCKED_PROVIDER_ACCESS
        assert a.blocked_reason == "forbidden_domain_fields_in_provider_payload"
        assert a.proof_fields_observed == ()
        assert field_name in a.sanitized_response_envelope["forbidden_domain_fields_present"]

def test_transport_exception_stores_only_sanitized_error_class():
    class BadTransport:
        def get(self, **kwargs):
            raise RuntimeError("secret-provider-url?token=leak_some_private_key")

    a = run_single_flight_probe(enabled_policy(), operator_network_flag=True, transport=BadTransport())
    combined = str(a.to_jsonable()).lower()
    assert a.status == SingleFlightProbeStatus.SINGLE_FLIGHT_BLOCKED_PROVIDER_ACCESS
    assert a.blocked_reason == "provider_access_failed_sanitized"
    assert "token=leak" not in combined
    assert "leak_some_private_key" not in combined
    assert a.sanitized_response_envelope["status"] == "error"
    assert a.sanitized_response_envelope["error_class"] == "RuntimeError"
