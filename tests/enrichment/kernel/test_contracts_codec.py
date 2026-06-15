from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, TypeVar

import pytest

from bet.integration.source_result import (
    SourceOperationResult,
    SourceResultStatus,
    normalize_source_result_status,
)
from src.bet.enrichment.kernel.codec import (
    canonical_json_bytes,
    canonical_json_text,
    canonical_sha256,
    from_primitive,
    to_primitive,
)
from src.bet.enrichment.kernel.contracts import (
    AttemptResult,
    CapabilityResolution,
    EnrichmentPlan,
    OperationRequest,
    OperationSubject,
    PlannedOperation,
    PlannedTransportCall,
    ProviderIdentitySet,
    RouteCandidate,
    SubjectRole,
    TerminalClass,
)

P = TypeVar("P")
T = TypeVar("T")

# --- Test Data Classes ---
@dataclass(frozen=True, slots=True)
class SimpleParams:
    value: str
    count: int

@dataclass(frozen=True, slots=True)
class NestedParams:
    id: int
    simple: SimpleParams

@dataclass(frozen=True, slots=True)
class TestDataclass:
    name: str
    value: int
    decimal_value: Decimal
    dt_value: datetime
    enum_value: SubjectRole
    optional_value: str | None
    list_value: list[int]
    tuple_value: tuple[str, ...]
    mapping_value: Mapping[str, str]
    boolean_value: bool

@dataclass(frozen=True, slots=True)
class DataclassWithDefault:
    name: str
    default_val: str = "default"


# --- Helpers to instantiate OperationRequest and ProviderIdentitySet without default args ---

def create_op_request(
    sport="football", capability_key="key", target_event_entity_id=1,
    subject=None, provider="prov", provider_event_id=None,
    provider_subject_id=None, provider_related_subject_ids=None,
    provider_competition_id=None, provider_season_id=None,
    analysis_cutoff_at=None, parameters=None, contract_version="1.0",
    dto_version="1.0"
):
    if subject is None:
        subject = OperationSubject(entity_id=1, role=SubjectRole.EVENT)
    if provider_related_subject_ids is None:
        provider_related_subject_ids = {}
    if analysis_cutoff_at is None:
        analysis_cutoff_at = datetime.now(UTC)
    return OperationRequest(
        sport=sport, capability_key=capability_key,
        target_event_entity_id=target_event_entity_id, subject=subject,
        provider=provider, provider_event_id=provider_event_id,
        provider_subject_id=provider_subject_id,
        provider_related_subject_ids=provider_related_subject_ids,
        provider_competition_id=provider_competition_id,
        provider_season_id=provider_season_id,
        analysis_cutoff_at=analysis_cutoff_at, parameters=parameters,
        contract_version=contract_version, dto_version=dto_version
    )

def create_provider_identity_set(
    provider="p", event_id=None, competition_id=None, season_id=None,
    participant_ids=None, venue_id=None, official_id=None
):
    if participant_ids is None:
        participant_ids = {}
    return ProviderIdentitySet(
        provider=provider, event_id=event_id, competition_id=competition_id,
        season_id=season_id, participant_ids=participant_ids,
        venue_id=venue_id, official_id=official_id
    )


# --- STATUSES ---

def test_source_result_status_extensions():
    assert SourceResultStatus.STALE == "STALE"
    assert SourceResultStatus.TEMPORAL_UNSAFE == "TEMPORAL_UNSAFE"

def test_normalize_source_result_status_unsupported_enum():
    assert normalize_source_result_status(SourceResultStatus.UNSUPPORTED) == \
        SourceResultStatus.NOT_SUPPORTED

def test_normalize_source_result_status_unsupported_string():
    assert normalize_source_result_status("UNSUPPORTED") == \
        SourceResultStatus.NOT_SUPPORTED

def test_normalize_source_result_status_existing_enum():
    assert normalize_source_result_status(SourceResultStatus.SUCCESS) == \
        SourceResultStatus.SUCCESS

def test_normalize_source_result_status_existing_string():
    assert normalize_source_result_status("SUCCESS") == SourceResultStatus.SUCCESS

def test_normalize_source_result_status_unknown_string_raises_error():
    with pytest.raises(ValueError, match="Unknown SourceResultStatus value: UNKNOWN_STATUS"):
        normalize_source_result_status("UNKNOWN_STATUS")


# --- IMMUTABILITY AND VALIDATION ---

def test_frozen_slots_contracts():
    op_subject = OperationSubject(entity_id=1, role=SubjectRole.EVENT)
    with pytest.raises((AttributeError, TypeError)):
         # Try modifying is blocked on frozen dataclass
         op_subject.entity_id = 2

def test_operation_subject_positive_entity_id():
    OperationSubject(entity_id=1, role=SubjectRole.EVENT)
    with pytest.raises(ValueError, match="entity_id must be a positive integer"):
        OperationSubject(entity_id=0, role=SubjectRole.EVENT)
    with pytest.raises(ValueError, match="entity_id must be a positive integer"):
        OperationSubject(entity_id=-1, role=SubjectRole.EVENT)

def test_operation_subject_rejects_bool_as_entity_id():
    with pytest.raises(ValueError, match="entity_id must be a positive integer"):
        OperationSubject(entity_id=True, role=SubjectRole.EVENT)

def test_operation_request_positive_target_event_entity_id():
    subject = OperationSubject(entity_id=1, role=SubjectRole.EVENT)
    aware_dt = datetime.now(UTC)
    create_op_request(target_event_entity_id=1, subject=subject, analysis_cutoff_at=aware_dt)
    with pytest.raises(ValueError, match="target_event_entity_id must be a positive integer"):
        create_op_request(target_event_entity_id=0, subject=subject, analysis_cutoff_at=aware_dt)

def test_operation_request_rejects_bool_as_target_event_entity_id():
    subject = OperationSubject(entity_id=1, role=SubjectRole.EVENT)
    aware_dt = datetime.now(UTC)
    with pytest.raises(ValueError, match="target_event_entity_id must be a positive integer"):
        create_op_request(target_event_entity_id=True, subject=subject, analysis_cutoff_at=aware_dt)

def test_operation_request_rejects_naive_cutoff():
    subject = OperationSubject(entity_id=1, role=SubjectRole.EVENT)
    naive_dt = datetime.now()
    with pytest.raises(ValueError, match="analysis_cutoff_at must be timezone-aware"):
        create_op_request(subject=subject, analysis_cutoff_at=naive_dt)

def test_operation_request_defensive_mapping_copy():
    subject = OperationSubject(entity_id=1, role=SubjectRole.EVENT)
    aware_dt = datetime.now(UTC)
    related_ids = {"team_a": "1", "team_b": "2"}
    req = create_op_request(
        subject=subject, provider_related_subject_ids=related_ids,
        analysis_cutoff_at=aware_dt
    )
    related_ids["team_c"] = "3"
    assert "team_c" not in req.provider_related_subject_ids

def test_operation_request_empty_required_strings():
    subject = OperationSubject(entity_id=1, role=SubjectRole.EVENT)
    aware_dt = datetime.now(UTC)
    with pytest.raises(ValueError, match="sport cannot be empty"):
        create_op_request(sport="", subject=subject, analysis_cutoff_at=aware_dt)

def test_planned_transport_call_non_negative_worst_case_http_calls():
    PlannedTransportCall(
        provider="p", operation="op", sanitized_request_identity="id",
        worst_case_http_calls=0
    )
    PlannedTransportCall(
        provider="p", operation="op", sanitized_request_identity="id",
        worst_case_http_calls=5
    )
    with pytest.raises(ValueError,
                        match="worst_case_http_calls must be a non-negative integer"):
        PlannedTransportCall(
            provider="p", operation="op", sanitized_request_identity="id",
            worst_case_http_calls=-1
        )

def test_planned_transport_call_rejects_bool_as_worst_case_http_calls():
    with pytest.raises(ValueError,
                        match="worst_case_http_calls must be a non-negative integer"):
        PlannedTransportCall(
            provider="p", operation="op", sanitized_request_identity="id",
            worst_case_http_calls=True
        )

def test_route_candidate_non_negative_ordinal():
    RouteCandidate(provider="p", provenance_family="f", ordinal=0)
    RouteCandidate(provider="p", provenance_family="f", ordinal=1)
    with pytest.raises(ValueError, match="ordinal must be a non-negative integer"):
        RouteCandidate(provider="p", provenance_family="f", ordinal=-1)

def test_route_candidate_rejects_bool_as_ordinal():
    with pytest.raises(ValueError, match="ordinal must be a non-negative integer"):
        RouteCandidate(provider="p", provenance_family="f", ordinal=True)

def test_planned_operation_route_ordinals_contiguous():
    subject = OperationSubject(entity_id=1, role=SubjectRole.EVENT)
    rc1 = RouteCandidate(provider="p1", provenance_family="f1", ordinal=0)
    rc2 = RouteCandidate(provider="p2", provenance_family="f2", ordinal=1)
    PlannedOperation(
        capability_key="ck", subject=subject, parameters=None, route=(rc1, rc2),
        freshness_seconds=None, required=True
    )

    rc_non_contiguous = RouteCandidate(provider="p3", provenance_family="f3",
                                       ordinal=2)
    with pytest.raises(ValueError,
                        match="route ordinals must be contiguous starting from 0"):
        PlannedOperation(
            capability_key="ck", subject=subject, parameters=None,
            route=(rc1, rc_non_contiguous), freshness_seconds=None, required=True
        )
    rc_duplicate_ordinal = RouteCandidate(provider="p4", provenance_family="f4",
                                          ordinal=0)
    with pytest.raises(ValueError, match="route ordinals must be contiguous starting from 0"):
        PlannedOperation(
            capability_key="ck", subject=subject, parameters=None,
            route=(rc1, rc_duplicate_ordinal), freshness_seconds=None, required=True
        )

def test_planned_operation_duplicate_providers_in_route():
    subject = OperationSubject(entity_id=1, role=SubjectRole.EVENT)
    rc1 = RouteCandidate(provider="p1", provenance_family="f1", ordinal=0)
    rc_dup_provider = RouteCandidate(provider="p1", provenance_family="f2",
                                     ordinal=1)
    with pytest.raises(ValueError, match="duplicate provider p1 in route"):
        PlannedOperation(
            capability_key="ck", subject=subject, parameters=None,
            route=(rc1, rc_dup_provider), freshness_seconds=None, required=True
        )

def test_planned_operation_freshness_seconds_positive_int():
    subject = OperationSubject(entity_id=1, role=SubjectRole.EVENT)
    rc = RouteCandidate(provider="p1", provenance_family="f1", ordinal=0)
    PlannedOperation(
        capability_key="ck", subject=subject, parameters=None, route=(rc,),
        freshness_seconds=100, required=True
    )
    with pytest.raises(ValueError,
                        match="freshness_seconds must be a positive integer or None"):
        PlannedOperation(
            capability_key="ck", subject=subject, parameters=None, route=(rc,),
            freshness_seconds=0, required=True
        )
    with pytest.raises(ValueError,
                        match="freshness_seconds must be a positive integer or None"):
        PlannedOperation(
            capability_key="ck", subject=subject, parameters=None, route=(rc,),
            freshness_seconds=True, required=True
        )

def test_planned_operation_terminal_precedence_no_duplicates():
    subject = OperationSubject(entity_id=1, role=SubjectRole.EVENT)
    rc = RouteCandidate(provider="p1", provenance_family="f1", ordinal=0)
    with pytest.raises(ValueError,
                        match="terminal_precedence cannot have duplicate entries"):
        PlannedOperation(
            capability_key="ck", subject=subject, parameters=None, route=(rc,),
            freshness_seconds=None, required=True,
            terminal_precedence=(TerminalClass.PARTIAL, TerminalClass.PARTIAL)
        )

def test_enrichment_plan_positive_target_event_entity_id():
    op_subject = OperationSubject(entity_id=1, role=SubjectRole.EVENT)
    rc = RouteCandidate(provider="p1", provenance_family="f1", ordinal=0)
    op = PlannedOperation(
        capability_key="ck", subject=op_subject, parameters=None, route=(rc,),
        freshness_seconds=None, required=True
    )
    aware_dt = datetime.now(UTC)
    EnrichmentPlan(
        sport="football", target_event_entity_id=1, analysis_cutoff_at=aware_dt,
        operations=(op,), contract_hash="ch", metric_contract_hash="mch",
        policy_config_hash="pch", selection_epoch=0
    )
    with pytest.raises(ValueError,
                        match="target_event_entity_id must be a positive integer"):
        EnrichmentPlan(
            sport="football", target_event_entity_id=0, analysis_cutoff_at=aware_dt,
            operations=(op,), contract_hash="ch", metric_contract_hash="mch",
            policy_config_hash="pch", selection_epoch=0
        )

def test_enrichment_plan_rejects_bool_as_target_event_entity_id():
    op_subject = OperationSubject(entity_id=1, role=SubjectRole.EVENT)
    rc = RouteCandidate(provider="p1", provenance_family="f1", ordinal=0)
    op = PlannedOperation(
        capability_key="ck", subject=op_subject, parameters=None, route=(rc,),
        freshness_seconds=None, required=True
    )
    aware_dt = datetime.now(UTC)
    with pytest.raises(ValueError,
                        match="target_event_entity_id must be a positive integer"):
        EnrichmentPlan(
            sport="football", target_event_entity_id=True, analysis_cutoff_at=aware_dt,
            operations=(op,), contract_hash="ch", metric_contract_hash="mch",
            policy_config_hash="pch", selection_epoch=0
        )

def test_enrichment_plan_rejects_naive_cutoff():
    op_subject = OperationSubject(entity_id=1, role=SubjectRole.EVENT)
    rc = RouteCandidate(provider="p1", provenance_family="f1", ordinal=0)
    op = PlannedOperation(
        capability_key="ck", subject=op_subject, parameters=None, route=(rc,),
        freshness_seconds=None, required=True
    )
    naive_dt = datetime.now()
    with pytest.raises(ValueError, match="analysis_cutoff_at must be timezone-aware"):
        EnrichmentPlan(
            sport="football", target_event_entity_id=1, analysis_cutoff_at=naive_dt,
            operations=(op,), contract_hash="ch", metric_contract_hash="mch",
            policy_config_hash="pch", selection_epoch=0
        )

def test_enrichment_plan_empty_required_strings():
    op_subject = OperationSubject(entity_id=1, role=SubjectRole.EVENT)
    rc = RouteCandidate(provider="p1", provenance_family="f1", ordinal=0)
    op = PlannedOperation(
        capability_key="ck", subject=op_subject, parameters=None, route=(rc,),
        freshness_seconds=None, required=True
    )
    aware_dt = datetime.now(UTC)
    with pytest.raises(ValueError, match="sport cannot be empty"):
        EnrichmentPlan(
            sport="", target_event_entity_id=1, analysis_cutoff_at=aware_dt,
            operations=(op,), contract_hash="ch", metric_contract_hash="mch",
            policy_config_hash="pch", selection_epoch=0
        )

def test_enrichment_plan_operations_not_empty():
    aware_dt = datetime.now(UTC)
    with pytest.raises(ValueError, match="operations cannot be empty"):
        EnrichmentPlan(
            sport="football", target_event_entity_id=1, analysis_cutoff_at=aware_dt,
            operations=(), contract_hash="ch", metric_contract_hash="mch",
            policy_config_hash="pch", selection_epoch=0
        )

def test_enrichment_plan_non_negative_selection_epoch():
    op_subject = OperationSubject(entity_id=1, role=SubjectRole.EVENT)
    rc = RouteCandidate(provider="p1", provenance_family="f1", ordinal=0)
    op = PlannedOperation(
        capability_key="ck", subject=op_subject, parameters=None, route=(rc,),
        freshness_seconds=None, required=True
    )
    aware_dt = datetime.now(UTC)
    EnrichmentPlan(
        sport="football", target_event_entity_id=1, analysis_cutoff_at=aware_dt,
        operations=(op,), contract_hash="ch", metric_contract_hash="mch",
        policy_config_hash="pch", selection_epoch=0
    )
    with pytest.raises(ValueError,
                        match="selection_epoch must be a non-negative integer"):
        EnrichmentPlan(
            sport="football", target_event_entity_id=1, analysis_cutoff_at=aware_dt,
            operations=(op,), contract_hash="ch", metric_contract_hash="mch",
            policy_config_hash="pch", selection_epoch=-1
        )

def test_enrichment_plan_rejects_bool_as_selection_epoch():
    op_subject = OperationSubject(entity_id=1, role=SubjectRole.EVENT)
    rc = RouteCandidate(provider="p1", provenance_family="f1", ordinal=0)
    op = PlannedOperation(
        capability_key="ck", subject=op_subject, parameters=None, route=(rc,),
        freshness_seconds=None, required=True
    )
    aware_dt = datetime.now(UTC)
    with pytest.raises(ValueError,
                        match="selection_epoch must be a non-negative integer"):
        EnrichmentPlan(
            sport="football", target_event_entity_id=1, analysis_cutoff_at=aware_dt,
            operations=(op,), contract_hash="ch", metric_contract_hash="mch",
            policy_config_hash="pch", selection_epoch=True
        )

def test_enrichment_plan_duplicate_operation_identity():
    op_subject1 = OperationSubject(entity_id=1, role=SubjectRole.EVENT)
    rc1 = RouteCandidate(provider="p1", provenance_family="f1", ordinal=0)
    op1 = PlannedOperation(
        capability_key="ck1", subject=op_subject1, parameters=None,
        route=(rc1,), freshness_seconds=None, required=True
    )
    op_subject2 = OperationSubject(entity_id=1, role=SubjectRole.EVENT)
    rc2 = RouteCandidate(provider="p2", provenance_family="f2", ordinal=0)
    # Same capability_key, subject.entity_id, subject.role
    op2 = PlannedOperation(
        capability_key="ck1", subject=op_subject2, parameters=None,
        route=(rc2,), freshness_seconds=None, required=True
    )
    aware_dt = datetime.now(UTC)
    with pytest.raises(ValueError, match="duplicate operation identity"):
        EnrichmentPlan(
            sport="football", target_event_entity_id=1, analysis_cutoff_at=aware_dt,
            operations=(op1, op2), contract_hash="ch", metric_contract_hash="mch",
            policy_config_hash="pch", selection_epoch=0
        )

def test_attempt_result_non_negative_ordinal():
    subject = OperationSubject(entity_id=1, role=SubjectRole.EVENT)
    result = SourceOperationResult(status=SourceResultStatus.SUCCESS)
    AttemptResult(
        capability_key="ck", subject=subject, provider="p", provenance_family="f",
        ordinal=0, logical_request_identity="lri", result=result
    )
    with pytest.raises(ValueError, match="ordinal must be a non-negative integer"):
        AttemptResult(
            capability_key="ck", subject=subject, provider="p", provenance_family="f",
            ordinal=-1, logical_request_identity="lri", result=result
        )

def test_attempt_result_rejects_bool_as_ordinal():
    subject = OperationSubject(entity_id=1, role=SubjectRole.EVENT)
    result = SourceOperationResult(status=SourceResultStatus.SUCCESS)
    with pytest.raises(ValueError, match="ordinal must be a non-negative integer"):
        AttemptResult(
            capability_key="ck", subject=subject, provider="p", provenance_family="f",
            ordinal=True, logical_request_identity="lri", result=result
        )

def test_capability_resolution_attempts_not_empty():
    subject = OperationSubject(entity_id=1, role=SubjectRole.EVENT)
    with pytest.raises(ValueError, match="attempts cannot be empty"):
        CapabilityResolution(
            capability_key="ck", subject=subject, attempts=(),
            selected_attempt_index=None, terminal_status=SourceResultStatus.SUCCESS
        )

def test_capability_resolution_selected_attempt_index_valid():
    subject = OperationSubject(entity_id=1, role=SubjectRole.EVENT)
    result = SourceOperationResult(status=SourceResultStatus.SUCCESS)
    attempt = AttemptResult(
        capability_key="ck", subject=subject, provider="p", provenance_family="f",
        ordinal=0, logical_request_identity="lri", result=result
    )
    CapabilityResolution(
        capability_key="ck", subject=subject, attempts=(attempt,),
        selected_attempt_index=0, terminal_status=SourceResultStatus.SUCCESS
    )
    with pytest.raises(ValueError,
                        match="selected_attempt_index must be a valid index or None"):
        CapabilityResolution(
            capability_key="ck", subject=subject, attempts=(attempt,),
            selected_attempt_index=1, terminal_status=SourceResultStatus.SUCCESS
        )
    with pytest.raises(ValueError,
                        match="selected_attempt_index must be a valid index or None"):
        CapabilityResolution(
            capability_key="ck", subject=subject, attempts=(attempt,),
            selected_attempt_index=-1, terminal_status=SourceResultStatus.SUCCESS
        )

def test_capability_resolution_rejects_bool_as_selected_attempt_index():
    subject = OperationSubject(entity_id=1, role=SubjectRole.EVENT)
    result = SourceOperationResult(status=SourceResultStatus.SUCCESS)
    attempt = AttemptResult(
        capability_key="ck", subject=subject, provider="p", provenance_family="f",
        ordinal=0, logical_request_identity="lri", result=result
    )
    with pytest.raises(ValueError,
                        match="selected_attempt_index must be a valid index or None"):
        CapabilityResolution(
            capability_key="ck", subject=subject, attempts=(attempt,),
            selected_attempt_index=True, terminal_status=SourceResultStatus.SUCCESS
        )

def test_provider_identity_set_non_empty_provider():
    with pytest.raises(ValueError, match="provider cannot be empty"):
        create_provider_identity_set(provider="", participant_ids={})

def test_provider_identity_set_positive_participant_ids_keys():
    create_provider_identity_set(provider="p", participant_ids={1: "id1"})
    with pytest.raises(ValueError,
                        match="participant_ids keys must be positive integers"):
        create_provider_identity_set(provider="p", participant_ids={0: "id1"})
    with pytest.raises(ValueError,
                        match="participant_ids keys must be positive integers"):
        create_provider_identity_set(provider="p", participant_ids={-1: "id1"})

def test_provider_identity_set_rejects_bool_as_participant_ids_keys():
    with pytest.raises(ValueError,
                        match="participant_ids keys must be positive integers"):
        create_provider_identity_set(provider="p", participant_ids={True: "id1"})

def test_provider_identity_set_non_empty_participant_ids_values():
    with pytest.raises(ValueError,
                        match="participant_ids values cannot be empty strings"):
        create_provider_identity_set(provider="p", participant_ids={1: ""})

def test_provider_identity_set_defensive_copy_participant_ids():
    participant_ids = {1: "id1"}
    pis = create_provider_identity_set(provider="p", participant_ids=participant_ids)
    participant_ids[2] = "id2"
    assert "id2" not in pis.participant_ids.values()


# --- IDENTITY / HASH ---

def test_operation_request_logical_identity_stable_with_mapping_order():
    subject = OperationSubject(entity_id=1, role=SubjectRole.EVENT)
    aware_dt = datetime(2023, 1, 1, 12, 0, 0, tzinfo=UTC)
    params = SimpleParams(value="test", count=1)

    related_ids1 = {"team_a": "1", "team_b": "2"}
    req1 = create_op_request(
        sport="football", capability_key="key", target_event_entity_id=1,
        subject=subject, provider="prov", provider_related_subject_ids=related_ids1,
        analysis_cutoff_at=aware_dt, parameters=params, contract_version="1.0",
        dto_version="1.0"
    )

    related_ids2 = {"team_b": "2", "team_a": "1"}  # Different order
    req2 = create_op_request(
        sport="football", capability_key="key", target_event_entity_id=1,
        subject=subject, provider="prov", provider_related_subject_ids=related_ids2,
        analysis_cutoff_at=aware_dt, parameters=params, contract_version="1.0",
        dto_version="1.0"
    )
    assert req1.logical_identity() == req2.logical_identity()

def test_operation_request_logical_identity_stable_with_equivalent_cutoff_timezone():
    subject = OperationSubject(entity_id=1, role=SubjectRole.EVENT)
    params = SimpleParams(value="test", count=1)
    related_ids = {"team_a": "1", "team_b": "2"}

    aware_dt_utc = datetime(2023, 1, 1, 12, 0, 0, tzinfo=UTC)
    req_utc = create_op_request(
        sport="football", capability_key="key", target_event_entity_id=1,
        subject=subject, provider="prov", provider_related_subject_ids=related_ids,
        analysis_cutoff_at=aware_dt_utc, parameters=params, contract_version="1.0",
        dto_version="1.0"
    )

    aware_dt_plus_2 = datetime(2023, 1, 1, 14, 0, 0, tzinfo=timezone(timedelta(hours=2)))
    req_plus_2 = create_op_request(
        sport="football", capability_key="key", target_event_entity_id=1,
        subject=subject, provider="prov", provider_related_subject_ids=related_ids,
        analysis_cutoff_at=aware_dt_plus_2, parameters=params, contract_version="1.0",
        dto_version="1.0"
    )
    assert req_utc.logical_identity() == req_plus_2.logical_identity()

def test_operation_request_logical_identity_changes_with_semantic_field_change():
    subject = OperationSubject(entity_id=1, role=SubjectRole.EVENT)
    aware_dt = datetime(2023, 1, 1, 12, 0, 0, tzinfo=UTC)
    params = SimpleParams(value="test", count=1)
    related_ids = {"team_a": "1"}

    req1 = create_op_request(
        sport="football", capability_key="key", target_event_entity_id=1,
        subject=subject, provider="prov", provider_related_subject_ids=related_ids,
        analysis_cutoff_at=aware_dt, parameters=params, contract_version="1.0",
        dto_version="1.0"
    )

    # Change sport
    req2 = create_op_request(
        sport="basketball", capability_key="key", target_event_entity_id=1,
        subject=subject, provider="prov", provider_related_subject_ids=related_ids,
        analysis_cutoff_at=aware_dt, parameters=params, contract_version="1.0",
        dto_version="1.0"
    )
    assert req1.logical_identity() != req2.logical_identity()

    # Change target_event_entity_id
    req3 = create_op_request(
        sport="football", capability_key="key", target_event_entity_id=2,
        subject=subject, provider="prov", provider_related_subject_ids=related_ids,
        analysis_cutoff_at=aware_dt, parameters=params, contract_version="1.0",
        dto_version="1.0"
    )
    assert req1.logical_identity() != req3.logical_identity()

    # Change parameter
    params_changed = SimpleParams(value="test_new", count=1)
    req4 = create_op_request(
        sport="football", capability_key="key", target_event_entity_id=1,
        subject=subject, provider="prov", provider_related_subject_ids=related_ids,
        analysis_cutoff_at=aware_dt, parameters=params_changed, contract_version="1.0",
        dto_version="1.0"
    )
    assert req1.logical_identity() != req4.logical_identity()

def test_enrichment_plan_plan_hash_stable():
    op_subject = OperationSubject(entity_id=1, role=SubjectRole.EVENT)
    rc1 = RouteCandidate(provider="p1", provenance_family="f1", ordinal=0)
    op1 = PlannedOperation(
        capability_key="ck1", subject=op_subject, parameters=None, route=(rc1,),
        freshness_seconds=None, required=True
    )
    aware_dt = datetime(2023, 1, 1, 12, 0, 0, tzinfo=UTC)
    plan1 = EnrichmentPlan(
        sport="football", target_event_entity_id=1, analysis_cutoff_at=aware_dt,
        operations=(op1,), contract_hash="ch", metric_contract_hash="mch",
        policy_config_hash="pch", selection_epoch=0
    )
    plan2 = EnrichmentPlan(
        sport="football", target_event_entity_id=1, analysis_cutoff_at=aware_dt,
        operations=(op1,), contract_hash="ch", metric_contract_hash="mch",
        policy_config_hash="pch", selection_epoch=0
    )
    assert plan1.plan_hash() == plan2.plan_hash()

def test_enrichment_plan_plan_hash_changes_with_semantic_field_change():
    op_subject = OperationSubject(entity_id=1, role=SubjectRole.EVENT)
    rc1 = RouteCandidate(provider="p1", provenance_family="f1", ordinal=0)
    op1 = PlannedOperation(
        capability_key="ck1", subject=op_subject, parameters=None, route=(rc1,),
        freshness_seconds=None, required=True
    )
    aware_dt = datetime(2023, 1, 1, 12, 0, 0, tzinfo=UTC)

    plan1 = EnrichmentPlan(
        sport="football", target_event_entity_id=1, analysis_cutoff_at=aware_dt,
        operations=(op1,), contract_hash="ch", metric_contract_hash="mch",
        policy_config_hash="pch", selection_epoch=0
    )

    plan_changed_sport = EnrichmentPlan(
        sport="basketball", target_event_entity_id=1, analysis_cutoff_at=aware_dt,
        operations=(op1,), contract_hash="ch", metric_contract_hash="mch",
        policy_config_hash="pch", selection_epoch=0
    )
    assert plan1.plan_hash() != plan_changed_sport.plan_hash()

    plan_changed_epoch = EnrichmentPlan(
        sport="football", target_event_entity_id=1, analysis_cutoff_at=aware_dt,
        operations=(op1,), contract_hash="ch", metric_contract_hash="mch",
        policy_config_hash="pch", selection_epoch=1
    )
    assert plan1.plan_hash() != plan_changed_epoch.plan_hash()


# --- CODEC VECTORS ---

def test_to_primitive_basic_types():
    assert to_primitive(123) == 123
    assert to_primitive("test") == "test"
    assert to_primitive(None) is None
    assert to_primitive(True) is True
    assert to_primitive(False) is False

def test_to_primitive_decimal():
    assert to_primitive(Decimal("1.23")) == "1.23"
    assert to_primitive(Decimal("1.00")) == "1"
    assert to_primitive(Decimal("1")) == "1"
    assert to_primitive(Decimal("-0.0")) == "0"
    assert to_primitive(Decimal("0.0")) == "0"
    with pytest.raises(ValueError, match="Decimal NaN or Infinity are not supported"):
        to_primitive(Decimal("NaN"))
    with pytest.raises(ValueError, match="Decimal NaN or Infinity are not supported"):
        to_primitive(Decimal("Infinity"))

def test_to_primitive_datetime():
    aware_dt = datetime(2023, 1, 1, 12, 30, 45, 123456, tzinfo=UTC)
    assert to_primitive(aware_dt) == "2023-01-01T12:30:45.123Z"
    aware_dt_plus_2 = datetime(2023, 1, 1, 14, 30, 45, 123456,
                               tzinfo=timezone(timedelta(hours=2)))
    assert to_primitive(aware_dt_plus_2) == "2023-01-01T12:30:45.123Z"

def test_to_primitive_strenum():
    assert to_primitive(SubjectRole.EVENT) == "EVENT"

def test_to_primitive_dataclass():
    params = SimpleParams(value="test", count=1)
    assert to_primitive(params) == {"value": "test", "count": 1}

def test_to_primitive_nested_dataclass():
    nested_params = NestedParams(id=1, simple=SimpleParams(value="nested", count=2))
    expected = {"id": 1, "simple": {"value": "nested", "count": 2}}
    assert to_primitive(nested_params) == expected

def test_to_primitive_list_tuple():
    assert to_primitive([1, 2, "test"]) == [1, 2, "test"]
    assert to_primitive((1, 2, "test")) == [1, 2, "test"]

def test_to_primitive_mapping_sorted_keys():
    mapping = {"b": 2, "a": 1}
    assert to_primitive(mapping) == {"a": 1, "b": 2}

def test_to_primitive_rejects_float():
    with pytest.raises(TypeError, match="Float values are not supported"):
        to_primitive(1.23)

def test_to_primitive_rejects_naive_datetime():
    naive_dt = datetime.now()
    with pytest.raises(ValueError, match="Naive datetime is not supported"):
        to_primitive(naive_dt)

def test_canonical_json_text_and_bytes():
    params = SimpleParams(value="test", count=1)
    expected_text = '{"count":1,"value":"test"}'
    expected_bytes = b'{"count":1,"value":"test"}'
    assert canonical_json_text(params) == expected_text
    assert canonical_json_bytes(params) == expected_bytes

def test_canonical_sha256():
    params1 = SimpleParams(value="test", count=1)
    params2 = SimpleParams(value="test", count=1)
    params3 = SimpleParams(value="other", count=2)
    assert canonical_sha256(params1) == canonical_sha256(params2)
    assert canonical_sha256(params1) != canonical_sha256(params3)

def test_from_primitive_basic_types():
    assert from_primitive(int, 1) == 1
    assert from_primitive(str, "test") == "test"
    assert from_primitive(type(None), None) is None
    assert from_primitive(bool, True) is True
    assert from_primitive(bool, False) is False

def test_from_primitive_rejects_bool_as_int():
    with pytest.raises(TypeError, match="Expected int, got <class 'bool'>"):
        from_primitive(int, True)

def test_from_primitive_decimal():
    assert from_primitive(Decimal, "1.23") == Decimal("1.23")
    assert from_primitive(Decimal, "1") == Decimal("1")
    assert from_primitive(Decimal, Decimal("5.67")) == Decimal("5.67")
    with pytest.raises(TypeError, match="Cannot convert .* to Decimal"):
        from_primitive(Decimal, "NaN")

def test_from_primitive_datetime():
    dt_str = "2023-01-01T12:30:45.123Z"
    expected_dt = datetime(2023, 1, 1, 12, 30, 45, 123000, tzinfo=UTC)
    assert from_primitive(datetime, dt_str) == expected_dt
    with pytest.raises(TypeError, match="Cannot convert .* to timezone-aware datetime"):
        from_primitive(datetime, "2023-01-01T12:30:45")  # Naive

def test_from_primitive_strenum():
    assert from_primitive(SubjectRole, "EVENT") == SubjectRole.EVENT
    with pytest.raises(TypeError, match="Unknown enum value 'UNKNOWN_ROLE' for SubjectRole"):
        from_primitive(SubjectRole, "UNKNOWN_ROLE")

def test_from_primitive_dataclass():
    primitive_data = {
        "name": "test", "value": 1, "decimal_value": "1.0",
        "dt_value": "2023-01-01T12:00:00.000Z", "enum_value": "EVENT",
        "optional_value": None, "list_value": [1, 2],
        "tuple_value": ["a", "b"], "mapping_value": {"k": "v"},
        "boolean_value": True
    }
    dt = datetime(2023, 1, 1, 12, 0, 0, tzinfo=UTC)
    expected_obj = TestDataclass(
        name="test", value=1, decimal_value=Decimal("1.0"), dt_value=dt,
        enum_value=SubjectRole.EVENT, optional_value=None, list_value=[1, 2],
        tuple_value=("a", "b"), mapping_value={"k": "v"}, boolean_value=True
    )
    assert from_primitive(TestDataclass, primitive_data) == expected_obj

def test_from_primitive_dataclass_missing_required_field():
    primitive_data = {"value": "test"}
    with pytest.raises(ValueError,
                        match="Missing required field 'count' for dataclass SimpleParams"):
        from_primitive(SimpleParams, primitive_data)

def test_from_primitive_dataclass_unknown_field():
    primitive_data = {"value": "test", "count": 1, "extra": "field"}
    with pytest.raises(ValueError, match="Unknown fields {'extra'}"):
        from_primitive(SimpleParams, primitive_data)

def test_from_primitive_dataclass_with_default():
    primitive_data = {"name": "test"}
    expected_obj = DataclassWithDefault(name="test", default_val="default")
    assert from_primitive(DataclassWithDefault, primitive_data) == expected_obj

    primitive_data_with_default = {"name": "test", "default_val": "custom"}
    expected_obj_custom = DataclassWithDefault(name="test", default_val="custom")
    assert from_primitive(DataclassWithDefault, primitive_data_with_default) == \
        expected_obj_custom

def test_from_primitive_list():
    assert from_primitive(list[int], [1, 2, 3]) == [1, 2, 3]
    with pytest.raises(TypeError, match="Expected list, got <class 'str'>"):
        from_primitive(list[int], "not a list")
    with pytest.raises(TypeError, match="Expected int, got <class 'str'>"):
        from_primitive(list[int], [1, "2", 3])

def test_from_primitive_tuple_unspecified():
    assert from_primitive(tuple[Any, ...], [1, "a"]) == (1, "a")

def test_from_primitive_tuple_ellipsis():
    assert from_primitive(tuple[int, ...], [1, 2, 3]) == (1, 2, 3)
    with pytest.raises(TypeError, match="Expected int, got <class 'str'>"):
        from_primitive(tuple[int, ...], [1, "2", 3])

def test_from_primitive_tuple_fixed_size():
    assert from_primitive(tuple[int, str], [1, "a"]) == (1, "a")
    with pytest.raises(TypeError, match="Expected int, got <class 'str'>"):
        from_primitive(tuple[int, str], ["1", "a"])
    with pytest.raises(ValueError, match="Tuple length mismatch"):
        from_primitive(tuple[int, str], [1, "a", 3])

def test_from_primitive_mapping():
    assert from_primitive(Mapping[str, int], {"a": 1, "b": 2}) == {"a": 1, "b": 2}
    with pytest.raises(TypeError, match="Only string keys are supported for mappings"):
        from_primitive(Mapping[int, int], {1: 1})
    with pytest.raises(TypeError, match="Expected int, got <class 'str'>"):
        from_primitive(Mapping[str, int], {"a": "1"})

def test_from_primitive_optional():
    assert from_primitive(int | None, 1) == 1
    assert from_primitive(int | None, None) is None
    with pytest.raises(TypeError, match="Could not convert 1.0 to any of "):
        from_primitive(int | None, 1.0)

def test_from_primitive_rejects_float():
    with pytest.raises(TypeError, match="Expected int, got <class 'float'>"):
        from_primitive(int, 1.0)
    with pytest.raises(TypeError, match="Expected str, got <class 'float'>"):
        from_primitive(str, 1.0)

def test_from_primitive_unsupported_type_raises_error():
    class CustomClass:
        pass
    with pytest.raises(TypeError, match=r"Unsupported expected type: <class '.*CustomClass'>"):
        from_primitive(CustomClass, CustomClass())


# --- COMPATIBILITY ---

def test_existing_source_result_status_imports_work():
    from bet.integration.source_result import SourceResultStatus
    assert SourceResultStatus.SUCCESS == "SUCCESS"

def test_existing_source_operation_result_imports_work():
    from bet.integration.source_result import SourceOperationResult
    result = SourceOperationResult(status=SourceResultStatus.SUCCESS)
    assert result.status == SourceResultStatus.SUCCESS

def test_kernel_public_re_exports_work():
    from src.bet.enrichment.kernel import SubjectRole, canonical_sha256
    assert SubjectRole.EVENT == "EVENT"
    assert callable(canonical_sha256)

def test_existing_dto_from_models_remain_importable():
    from src.bet.enrichment.models import NormalizedEventStatus
    assert NormalizedEventStatus.SCHEDULED == "SCHEDULED"
