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
        mapping_status="MAPPING_READY_FOR_SANITIZED_PROBE",
        probe_status="SANITIZED_PROBE_READY_DRY_RUN"
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
        mapping_status="MAPPING_READY_FOR_SANITIZED_PROBE",
        probe_status="SANITIZED_PROBE_READY_DRY_RUN"
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

def test_pass_f_not_ready_blocks_before_transport():
    p = default_policy_for_sport(
        "basketball",
        access_status="AUTHORIZED_FOR_SANITIZED_LIVE_PROBE",
        mapping_status="MAPPING_READY_FOR_SANITIZED_PROBE",
        probe_status="SANITIZED_PROBE_BLOCKED_NO_CREDENTIALS"
    )
    object.__setattr__(p, "allow_real_network", True)
    t = FakeTransport({"fixture_id": "1", "home_team": "A", "away_team": "B", "start_time": "2026"})
    a = run_single_flight_probe(p, operator_network_flag=True, transport=t)
    assert a.status == SingleFlightProbeStatus.SINGLE_FLIGHT_BLOCKED_PASS_F_PROBE_NOT_READY
    assert a.live_call_made is False
    assert a.provider_access_attempted is False
    assert t.calls == 0

def test_nested_proof_extraction_api_sports():
    payload = {
        "response": [
            {
                "game": {"id": 391053, "date": "2026-01-01T00:00:00Z"},
                "teams": {
                    "home": {"name": "A"},
                    "away": {"name": "B"}
                }
            }
        ]
    }
    t = FakeTransport(payload)
    a = run_single_flight_probe(enabled_policy(), operator_network_flag=True, transport=t)
    assert a.status == SingleFlightProbeStatus.SINGLE_FLIGHT_RESULT_CAPTURED_SANITIZED
    assert set(a.proof_fields_observed) == {"fixture_id", "home_team", "away_team", "start_time"}

def test_raw_value_safety():
    payload = {
        "response": [
            {
                "game": {"id": 391053, "date": "2026-01-01T00:00:00Z"},
                "teams": {
                    "home": {"name": "A"},
                    "away": {"name": "B"}
                }
            }
        ]
    }
    t = FakeTransport(payload)
    a = run_single_flight_probe(enabled_policy(), operator_network_flag=True, transport=t)
    
    # Check that artifact / response envelope has no raw payload values
    combined = str(a.to_jsonable())
    assert "391053" not in combined
    assert "2026-01-01T00:00:00Z" not in combined
    # Let's make sure the raw team values 'A' or 'B' are not in observed fields or envelope (though single characters like 'A' could exist elsewhere, but we can check specifically)
    assert a.sanitized_response_envelope.get("minimum_fact_fields_observed") == ["fixture_id", "home_team", "away_team", "start_time"]
    
    env = a.sanitized_response_envelope
    # sanitized_response_envelope may contain only logical field names, missing logical field names, payload shape, forbidden field names and raw_payload_persisted=false
    allowed_keys = {
        "payload_shape",
        "minimum_fact_fields_observed",
        "minimum_fact_fields_missing",
        "forbidden_domain_fields_present",
        "raw_payload_persisted"
    }
    assert set(env.keys()) == allowed_keys

def test_nested_forbidden_fields_block_capture():
    payload_odds = {
        "response": [
            {
                "game": {"id": 391053, "date": "2026-01-01T00:00:00Z"},
                "teams": {
                    "home": {"name": "A", "odds": 1.5},
                    "away": {"name": "B"}
                }
            }
        ]
    }
    t = FakeTransport(payload_odds)
    a = run_single_flight_probe(enabled_policy(), operator_network_flag=True, transport=t)
    assert a.status == SingleFlightProbeStatus.SINGLE_FLIGHT_BLOCKED_PROVIDER_ACCESS
    assert a.blocked_reason == "forbidden_domain_fields_in_provider_payload"
    assert "odds" in a.sanitized_response_envelope["forbidden_domain_fields_present"]

    payload_bookmaker = {
        "response": [
            {
                "game": {"id": 391053, "date": "2026-01-01T00:00:00Z"},
                "teams": {
                    "home": {"name": "A"},
                    "away": {"name": "B"}
                },
                "bookmaker": "Betclic"
            }
        ]
    }
    t2 = FakeTransport(payload_bookmaker)
    a2 = run_single_flight_probe(enabled_policy(), operator_network_flag=True, transport=t2)
    assert a2.status == SingleFlightProbeStatus.SINGLE_FLIGHT_BLOCKED_PROVIDER_ACCESS
    assert a2.blocked_reason == "forbidden_domain_fields_in_provider_payload"
    assert "bookmaker" in a2.sanitized_response_envelope["forbidden_domain_fields_present"]
