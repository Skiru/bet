from __future__ import annotations
import json
import os
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

TARGET_SPORTS = ("basketball", "volleyball", "hockey", "tennis", "cs2", "dota2", "valorant")

class SingleFlightProbeStatus(StrEnum):
    SINGLE_FLIGHT_BLOCKED_ACCESS_GATE = "SINGLE_FLIGHT_BLOCKED_ACCESS_GATE"
    SINGLE_FLIGHT_BLOCKED_OPERATOR_FLAG = "SINGLE_FLIGHT_BLOCKED_OPERATOR_FLAG"
    SINGLE_FLIGHT_BLOCKED_MAPPING_NOT_READY = "SINGLE_FLIGHT_BLOCKED_MAPPING_NOT_READY"
    SINGLE_FLIGHT_BLOCKED_PASS_F_PROBE_NOT_READY = "SINGLE_FLIGHT_BLOCKED_PASS_F_PROBE_NOT_READY"
    SINGLE_FLIGHT_BLOCKED_TRANSPORT_UNAVAILABLE = "SINGLE_FLIGHT_BLOCKED_TRANSPORT_UNAVAILABLE"
    SINGLE_FLIGHT_BLOCKED_PROVIDER_ACCESS = "SINGLE_FLIGHT_BLOCKED_PROVIDER_ACCESS"
    SINGLE_FLIGHT_RESULT_CAPTURED_SANITIZED = "SINGLE_FLIGHT_RESULT_CAPTURED_SANITIZED"

class ProbeTransport(Protocol):
    def get(self, *, provider_key: str, sport: str, route_key: str, url_template: str) -> dict[str, Any]: ...

@dataclass(frozen=True)
class SingleFlightProbePolicy:
    sport: str
    provider_key: str
    route_key: str
    source_access_status: str
    source_mapping_status: str
    source_probe_status: str = "SANITIZED_PROBE_BLOCKED_NO_CREDENTIALS"
    allow_real_network: bool = False
    max_requests: int = 1
    sanitized_probe_only: bool = True
    production_selectable: bool = False
    betting_decisions_enabled: bool = False
    request_url_template: str = ""

    def __post_init__(self) -> None:
        if self.max_requests != 1:
            raise ValueError("single_flight_max_requests_must_equal_1")
        if self.sanitized_probe_only is not True:
            raise ValueError("sanitized_probe_only_required")
        if self.production_selectable is not False:
            raise ValueError("production_selectable_forbidden")
        if self.betting_decisions_enabled is not False:
            raise ValueError("betting_decisions_forbidden")

@dataclass(frozen=True)
class SingleFlightProbeArtifact:
    artifact_id: str
    sport: str
    provider_key: str
    route_key: str
    status: str
    source_access_status: str
    source_mapping_status: str
    request_method: str
    request_url_template: str
    sanitized_request_metadata: dict[str, Any]
    sanitized_response_envelope: dict[str, Any]
    proof_fields_observed: tuple[str, ...]
    missing_proof_fields: tuple[str, ...]
    live_call_made: bool
    provider_access_attempted: bool
    max_requests: int
    blocked_reason: str
    production_selectable: bool
    betting_decisions_enabled: bool
    source_probe_status: str = "SANITIZED_PROBE_BLOCKED_NO_CREDENTIALS"
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.production_selectable is not False:
            raise ValueError("production_selectable_must_be_false")
        if self.betting_decisions_enabled is not False:
            raise ValueError("betting_decisions_enabled_must_be_false")
        if self.status != SingleFlightProbeStatus.SINGLE_FLIGHT_RESULT_CAPTURED_SANITIZED:
            if len(self.proof_fields_observed) > 0:
                raise ValueError("proof_fields_observed_must_be_empty_unless_captured")
        else:
            if not self.live_call_made or not self.provider_access_attempted:
                raise ValueError("captured_requires_live_call_and_provider_access")

    def to_jsonable(self) -> dict[str, Any]:
        item = asdict(self)
        item["proof_fields_observed"] = list(self.proof_fields_observed)
        item["missing_proof_fields"] = list(self.missing_proof_fields)
        item["evidence_refs"] = list(self.evidence_refs)
        return item

def default_policy_for_sport(
    sport: str,
    access_status: str = "BLOCKED_NO_CREDENTIALS",
    mapping_status: str = "BLOCKED_NO_CREDENTIALS",
    probe_status: str = "SANITIZED_PROBE_BLOCKED_NO_CREDENTIALS"
) -> SingleFlightProbePolicy:
    provider_key = "pandascore" if sport in {"cs2", "dota2", "valorant"} else "api-sports-family"
    route_key = {
        "basketball": "api_basketball_games",
        "volleyball": "api_volleyball_games",
        "hockey": "api_hockey_games",
        "tennis": "api_tennis_fixtures",
        "cs2": "pandascore_cs2_matches",
        "dota2": "pandascore_dota2_matches",
        "valorant": "pandascore_valorant_matches"
    }[sport]
    return SingleFlightProbePolicy(
        sport=sport,
        provider_key=provider_key,
        route_key=route_key,
        source_access_status=access_status,
        source_mapping_status=mapping_status,
        source_probe_status=probe_status,
        request_url_template=f"https://provider.example.invalid/{provider_key}/{route_key}"
    )

def minimum_fact_fields_for_sport(sport: str) -> tuple[str, ...]:
    if sport == "tennis":
        return ("fixture_id", "participant_a", "participant_b", "start_time")
    if sport in {"cs2", "dota2", "valorant"}:
        return ("match_id", "opponents", "begin_at")
    return ("fixture_id", "home_team", "away_team", "start_time")

def _empty_request_metadata() -> dict[str, Any]:
    return {
        "credential_header_family": "provider_auth",
        "credential_header_present": False,
        "credential_value": "redacted_presence_only",
        "query_parameter_values": "redacted_presence_only"
    }

@dataclass(frozen=True)
class ProofFieldSpec:
    logical_name: str
    accepted_paths: tuple[str, ...]

PROOF_FIELD_SPECS = {
    "fixture_id": ProofFieldSpec(
        "fixture_id",
        (
            "fixture_id",
            "id",
            "game.id",
            "fixture.id",
            "response[].id",
            "response[].game.id",
        )
    ),
    "home_team": ProofFieldSpec(
        "home_team",
        (
            "home_team",
            "teams.home.name",
            "home.name",
            "response[].teams.home.name",
            "response[].home.name",
        )
    ),
    "away_team": ProofFieldSpec(
        "away_team",
        (
            "away_team",
            "teams.away.name",
            "away.name",
            "response[].teams.away.name",
            "response[].away.name",
        )
    ),
    "start_time": ProofFieldSpec(
        "start_time",
        (
            "start_time",
            "date",
            "time",
            "begin_at",
            "fixture.date",
            "game.date",
            "response[].date",
            "response[].time",
            "response[].game.date",
        )
    ),
    "participant_a": ProofFieldSpec(
        "participant_a",
        (
            "participant_a",
            "player_or_team_a",
            "players.home.name",
            "participants.0.name",
            "response[].players.home.name",
            "response[].participants.0.name",
        )
    ),
    "participant_b": ProofFieldSpec(
        "participant_b",
        (
            "participant_b",
            "player_or_team_b",
            "players.away.name",
            "participants.1.name",
            "response[].players.away.name",
            "response[].participants.1.name",
        )
    ),
    "match_id": ProofFieldSpec(
        "match_id",
        (
            "match_id",
            "id",
            "response[].id",
        )
    ),
    "opponents": ProofFieldSpec(
        "opponents",
        (
            "opponents",
            "response[].opponents",
            "competitors",
            "response[].competitors",
        )
    ),
    "begin_at": ProofFieldSpec(
        "begin_at",
        (
            "begin_at",
            "scheduled_at",
            "start_time",
            "response[].begin_at",
            "response[].scheduled_at",
        )
    ),
}

def evaluate_segments(obj: Any, segments: list[str]) -> bool:
    if not segments:
        return obj not in (None, "", [], {})

    current = segments[0]
    remaining = segments[1:]

    # Check if current segment represents a list iteration, e.g. "response[]"
    if current.endswith("[]"):
        key = current[:-2]
        if not isinstance(obj, dict) or key not in obj:
            return False
        val = obj[key]
        if not isinstance(val, list) or not val:
            return False
        # If there are remaining segments, at least one item must satisfy them
        if remaining:
            return any(evaluate_segments(item, remaining) for item in val)
        else:
            return val not in (None, "", [], {})

    # Check if current segment is numeric (list index), e.g. "0" or "1"
    if current.isdigit():
        idx = int(current)
        if not isinstance(obj, list) or idx < 0 or idx >= len(obj):
            return False
        val = obj[idx]
        return evaluate_segments(val, remaining)

    # Otherwise, it's a standard dictionary key lookup
    if not isinstance(obj, dict) or current not in obj:
        return False
    val = obj[current]
    return evaluate_segments(val, remaining)

def check_logical_field(raw: dict[str, Any], logical_name: str) -> bool:
    spec = PROOF_FIELD_SPECS.get(logical_name)
    if not spec:
        return False
    for path in spec.accepted_paths:
        segments = path.split(".")
        if evaluate_segments(raw, segments):
            return True
    return False

def _sanitize_response(raw: dict[str, Any], proof_fields: tuple[str, ...]) -> tuple[dict[str, Any], tuple[str, ...], tuple[str, ...]]:
    forbidden = {"odds", "prediction", "predictions", "pick", "stake", "edge", "recommendation", "bookmaker"}

    # Check if raw or nested parts contains forbidden fields
    def has_forbidden(obj: Any) -> list[str]:
        found = []
        if isinstance(obj, dict):
            for k, v in obj.items():
                if str(k).lower() in forbidden:
                    found.append(str(k))
                found.extend(has_forbidden(v))
        elif isinstance(obj, list):
            for item in obj:
                found.extend(has_forbidden(item))
        return found

    forbidden_found = sorted(list(set(has_forbidden(raw))))

    observed_list = []
    missing_list = []
    for f in proof_fields:
        if check_logical_field(raw, f):
            observed_list.append(f)
        else:
            missing_list.append(f)

    observed = tuple(observed_list)
    missing = tuple(missing_list)

    envelope = {
        "payload_shape": "object",
        "minimum_fact_fields_observed": list(observed),
        "minimum_fact_fields_missing": list(missing),
        "forbidden_domain_fields_present": forbidden_found,
        "raw_payload_persisted": False
    }
    return envelope, observed, missing

def run_single_flight_probe(
    policy: SingleFlightProbePolicy,
    *,
    operator_network_flag: bool | None = None,
    transport: ProbeTransport | None = None
) -> SingleFlightProbeArtifact:
    if operator_network_flag is None:
        operator_network_flag = (os.environ.get("MULTISPORT_PASS_I_ALLOW_REAL_NETWORK") == "1")

    proof_fields = minimum_fact_fields_for_sport(policy.sport)
    base = dict(
        artifact_id=f"pass_i:{policy.sport}:{policy.provider_key}:{policy.route_key}",
        sport=policy.sport,
        provider_key=policy.provider_key,
        route_key=policy.route_key,
        source_access_status=policy.source_access_status,
        source_mapping_status=policy.source_mapping_status,
        source_probe_status=policy.source_probe_status,
        request_method="GET",
        request_url_template=policy.request_url_template,
        sanitized_request_metadata=_empty_request_metadata(),
        max_requests=1,
        production_selectable=False,
        betting_decisions_enabled=False,
        evidence_refs=(f"pass_h:{policy.sport}", f"pass_f:{policy.sport}")
    )

    def art(status, reason, live=False, attempted=False, env=None, observed=(), missing=None):
        return SingleFlightProbeArtifact(
            **base,
            status=status,
            sanitized_response_envelope=env or {"status": "blocked", "raw_payload_persisted": False},
            proof_fields_observed=observed,
            missing_proof_fields=missing if missing is not None else proof_fields,
            live_call_made=live,
            provider_access_attempted=attempted,
            blocked_reason=reason
        )

    if policy.source_access_status != "AUTHORIZED_FOR_SANITIZED_LIVE_PROBE":
        return art(SingleFlightProbeStatus.SINGLE_FLIGHT_BLOCKED_ACCESS_GATE, "pass_h_access_gate_not_authorized")
    if policy.source_mapping_status != "MAPPING_READY_FOR_SANITIZED_PROBE":
        return art(SingleFlightProbeStatus.SINGLE_FLIGHT_BLOCKED_MAPPING_NOT_READY, "pass_e_mapping_not_ready")
    if policy.source_probe_status != "SANITIZED_PROBE_READY_DRY_RUN":
        return art(SingleFlightProbeStatus.SINGLE_FLIGHT_BLOCKED_PASS_F_PROBE_NOT_READY, "pass_f_probe_not_ready")
    if not (policy.allow_real_network and operator_network_flag):
        return art(SingleFlightProbeStatus.SINGLE_FLIGHT_BLOCKED_OPERATOR_FLAG, "explicit_operator_network_flag_missing")
    if transport is None:
        return art(SingleFlightProbeStatus.SINGLE_FLIGHT_BLOCKED_TRANSPORT_UNAVAILABLE, "transport_not_injected")

    try:
        raw = transport.get(
            provider_key=policy.provider_key,
            sport=policy.sport,
            route_key=policy.route_key,
            url_template=policy.request_url_template
        )
    except Exception as err:
        return art(
            SingleFlightProbeStatus.SINGLE_FLIGHT_BLOCKED_PROVIDER_ACCESS,
            "provider_access_failed_sanitized",
            attempted=True,
            env={"status": "error", "error_class": err.__class__.__name__, "raw_payload_persisted": False}
        )

    envelope, observed, missing = _sanitize_response(raw, proof_fields)
    if envelope["forbidden_domain_fields_present"]:
        return art(
            SingleFlightProbeStatus.SINGLE_FLIGHT_BLOCKED_PROVIDER_ACCESS,
            "forbidden_domain_fields_in_provider_payload",
            live=True,
            attempted=True,
            env=envelope,
            observed=(),
            missing=missing
        )
    if missing:
        return art(
            SingleFlightProbeStatus.SINGLE_FLIGHT_BLOCKED_PROVIDER_ACCESS,
            "minimum_fact_fields_missing",
            live=True,
            attempted=True,
            env=envelope,
            observed=(),
            missing=missing
        )

    return art(
        SingleFlightProbeStatus.SINGLE_FLIGHT_RESULT_CAPTURED_SANITIZED,
        "",
        live=True,
        attempted=True,
        env=envelope,
        observed=observed,
        missing=()
    )

def build_default_single_flight_report() -> dict[str, Any]:
    # Dynamic load from Pass H, Pass E and Pass F
    access_statuses = {}
    mapping_statuses = {}
    probe_statuses = {}
    for s in TARGET_SPORTS:
        access_statuses[s] = "BLOCKED_NO_CREDENTIALS"
        mapping_statuses[s] = "BLOCKED_NO_CREDENTIALS"
        probe_statuses[s] = "SANITIZED_PROBE_BLOCKED_NO_CREDENTIALS"

    try:
        p_h_path = Path("reports/multisport_foundation/pass_h/provider_access_by_sport.json")
        if p_h_path.exists():
            data = json.loads(p_h_path.read_text(encoding="utf-8"))
            for sport, items in data.items():
                if items:
                    access_statuses[sport] = items[0].get("status", "BLOCKED_NO_CREDENTIALS")
    except Exception:
        pass

    try:
        p_e_path = Path("reports/multisport_foundation/pass_e/provider_mapping_plan.json")
        if p_e_path.exists():
            data = json.loads(p_e_path.read_text(encoding="utf-8"))
            mapping_by_sport = data.get("provider_mapping_by_sport", {})
            for sport, items in mapping_by_sport.items():
                if items:
                    mapping_statuses[sport] = items[0].get("status", "BLOCKED_NO_CREDENTIALS")
    except Exception:
        pass

    try:
        p_f_path = Path("reports/multisport_foundation/pass_f/provider_probe_results_by_sport.json")
        if p_f_path.exists():
            data = json.loads(p_f_path.read_text(encoding="utf-8"))
            probe_by_sport = data.get("provider_probe_results_by_sport", {})
            for sport, items in probe_by_sport.items():
                if items:
                    probe_statuses[sport] = items[0].get("status", "SANITIZED_PROBE_BLOCKED_NO_CREDENTIALS")
    except Exception:
        pass

    by_sport = {}
    for sport in TARGET_SPORTS:
        p = default_policy_for_sport(
            sport,
            access_status=access_statuses[sport],
            mapping_status=mapping_statuses[sport],
            probe_status=probe_statuses[sport]
        )
        by_sport[sport] = [run_single_flight_probe(p).to_jsonable()]

    status_by_sport = {sport: items[0]["status"] for sport, items in by_sport.items()}
    return {
        "phase_id": "MULTISPORT_PASS_I_AUTHORIZED_SINGLE_FLIGHT_SANITIZED_PROBE",
        "target_sports": list(TARGET_SPORTS),
        "single_flight_probe_by_sport": by_sport,
        "status_by_sport": status_by_sport,
        "live_calls_made": False,
        "provider_access_attempted": False,
        "production_activation": False,
        "betting_decisions": False,
        "metrics": {
            "total_target_sports": len(TARGET_SPORTS),
            "single_flight_result_captured_sanitized_count": sum(1 for s in status_by_sport.values() if s == SingleFlightProbeStatus.SINGLE_FLIGHT_RESULT_CAPTURED_SANITIZED),
            "single_flight_blocked_access_gate_count": sum(1 for s in status_by_sport.values() if s == SingleFlightProbeStatus.SINGLE_FLIGHT_BLOCKED_ACCESS_GATE)
        }
    }

def validate_single_flight_report(report: dict[str, Any]) -> list[str]:
    errors = []
    if set(report.get("target_sports", [])) != set(TARGET_SPORTS):
        errors.append("target_sports_mismatch")
    if report.get("production_activation") is not False:
        errors.append("production_activation_must_be_false")
    if report.get("betting_decisions") is not False:
        errors.append("betting_decisions_must_be_false")
    for sport, items in report.get("single_flight_probe_by_sport", {}).items():
        for item in items:
            if item.get("production_selectable") is not False:
                errors.append(f"production_selectable_true:{sport}")
            if item.get("betting_decisions_enabled") is not False:
                errors.append(f"betting_decisions_enabled_true:{sport}")
            if item.get("sanitized_response_envelope", {}).get("raw_payload_persisted") is not False:
                errors.append(f"raw_payload_persisted:{sport}")
    return errors
