from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, TypeVar

import pytest

from bet.enrichment.kernel.codec import (
    canonical_json_bytes,
    canonical_json_text,
    canonical_sha256,
    from_primitive,
    to_primitive,
)
from bet.enrichment.kernel.contracts import (
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
from bet.integration.source_result import (
    SourceOperationResult,
    SourceResultStatus,
    normalize_source_result_status,
)

P = TypeVar("P")
T = TypeVar("T")

FIXED_AWARE_DT = datetime(2023, 1, 1, 12, 30, 45, 123456, tzinfo=UTC)


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
class SampleTestDataclass:
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


@dataclass(frozen=True, slots=True)
class SchemaVersionedContract:
    schema_version: str = "v1"
    payload: str = "hello"


def create_op_request(
    sport="football",
    capability_key="key",
    target_event_entity_id=1,
    subject=None,
    provider="prov",
    provider_event_id=None,
    provider_subject_id=None,
    provider_related_subject_ids=None,
    provider_competition_id=None,
    provider_season_id=None,
    analysis_cutoff_at=None,
    parameters=None,
    contract_version="1.0",
    dto_version="1.0",
):
    if subject is None:
        subject = OperationSubject(entity_id=1, role=SubjectRole.EVENT)
    if provider_related_subject_ids is None:
        provider_related_subject_ids = {}
    if analysis_cutoff_at is None:
        analysis_cutoff_at = FIXED_AWARE_DT
    return OperationRequest(
        sport=sport,
        capability_key=capability_key,
        target_event_entity_id=target_event_entity_id,
        subject=subject,
        provider=provider,
        provider_event_id=provider_event_id,
        provider_subject_id=provider_subject_id,
        provider_related_subject_ids=provider_related_subject_ids,
        provider_competition_id=provider_competition_id,
        provider_season_id=provider_season_id,
        analysis_cutoff_at=analysis_cutoff_at,
        parameters=parameters,
        contract_version=contract_version,
        dto_version=dto_version,
    )


def create_provider_identity_set(
    provider="p",
    event_id=None,
    competition_id=None,
    season_id=None,
    participant_ids=None,
    venue_id=None,
    official_id=None,
):
    if participant_ids is None:
        participant_ids = {}
    return ProviderIdentitySet(
        provider=provider,
        event_id=event_id,
        competition_id=competition_id,
        season_id=season_id,
        participant_ids=participant_ids,
        venue_id=venue_id,
        official_id=official_id,
    )


# --- STATUSES ---


def test_source_result_status_extensions():
    assert SourceResultStatus.STALE == "STALE"
    assert SourceResultStatus.TEMPORAL_UNSAFE == "TEMPORAL_UNSAFE"


def test_normalize_source_result_status_unsupported_enum():
    assert (
        normalize_source_result_status(SourceResultStatus.UNSUPPORTED)
        == SourceResultStatus.NOT_SUPPORTED
    )


def test_normalize_source_result_status_unsupported_string():
    assert (
        normalize_source_result_status("UNSUPPORTED")
        == SourceResultStatus.NOT_SUPPORTED
    )


def test_normalize_source_result_status_existing_enum():
    assert (
        normalize_source_result_status(SourceResultStatus.SUCCESS)
        == SourceResultStatus.SUCCESS
    )


def test_normalize_source_result_status_existing_string():
    assert normalize_source_result_status("SUCCESS") == SourceResultStatus.SUCCESS


def test_normalize_source_result_status_unknown_string_raises_error():
    with pytest.raises(
        ValueError, match="Unknown SourceResultStatus value: UNKNOWN_STATUS"
    ):
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
    create_op_request(
        target_event_entity_id=1, subject=subject, analysis_cutoff_at=FIXED_AWARE_DT
    )
    with pytest.raises(
        ValueError, match="target_event_entity_id must be a positive integer"
    ):
        create_op_request(
            target_event_entity_id=0, subject=subject, analysis_cutoff_at=FIXED_AWARE_DT
        )


def test_operation_request_rejects_bool_as_target_event_entity_id():
    subject = OperationSubject(entity_id=1, role=SubjectRole.EVENT)
    with pytest.raises(
        ValueError, match="target_event_entity_id must be a positive integer"
    ):
        create_op_request(
            target_event_entity_id=True,
            subject=subject,
            analysis_cutoff_at=FIXED_AWARE_DT,
        )


def test_operation_request_rejects_naive_cutoff():
    subject = OperationSubject(entity_id=1, role=SubjectRole.EVENT)
    naive_dt = datetime(2023, 1, 1, 12, 0, 0)
    with pytest.raises(ValueError, match="analysis_cutoff_at must be timezone-aware"):
        create_op_request(subject=subject, analysis_cutoff_at=naive_dt)


def test_operation_request_defensive_mapping_copy_and_immutability():
    subject = OperationSubject(entity_id=1, role=SubjectRole.EVENT)
    related_ids = {"team_a": "1", "team_b": "2"}
    req = create_op_request(
        subject=subject,
        provider_related_subject_ids=related_ids,
        analysis_cutoff_at=FIXED_AWARE_DT,
    )
    # Check that mutating original dict doesn't affect the request
    related_ids["team_c"] = "3"
    assert "team_c" not in req.provider_related_subject_ids

    # Check that direct mutation of request mapping is strictly blocked
    with pytest.raises(TypeError):
        req.provider_related_subject_ids["team_d"] = "4"


def test_operation_request_empty_required_strings():
    subject = OperationSubject(entity_id=1, role=SubjectRole.EVENT)
    with pytest.raises(ValueError, match="sport cannot be empty"):
        create_op_request(sport="", subject=subject, analysis_cutoff_at=FIXED_AWARE_DT)
    with pytest.raises(ValueError, match="sport must be a string"):
        create_op_request(sport=123, subject=subject, analysis_cutoff_at=FIXED_AWARE_DT)
    with pytest.raises(ValueError, match="sport cannot be empty"):
        create_op_request(
            sport="   ", subject=subject, analysis_cutoff_at=FIXED_AWARE_DT
        )


def test_planned_transport_call_non_negative_worst_case_http_calls():
    PlannedTransportCall(
        provider="p",
        operation="op",
        sanitized_request_identity="id",
        worst_case_http_calls=0,
    )
    PlannedTransportCall(
        provider="p",
        operation="op",
        sanitized_request_identity="id",
        worst_case_http_calls=5,
    )
    with pytest.raises(
        ValueError, match="worst_case_http_calls must be a non-negative integer"
    ):
        PlannedTransportCall(
            provider="p",
            operation="op",
            sanitized_request_identity="id",
            worst_case_http_calls=-1,
        )


def test_planned_transport_call_rejects_bool_as_worst_case_http_calls():
    with pytest.raises(
        ValueError, match="worst_case_http_calls must be a non-negative integer"
    ):
        PlannedTransportCall(
            provider="p",
            operation="op",
            sanitized_request_identity="id",
            worst_case_http_calls=True,
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
        capability_key="ck",
        subject=subject,
        parameters=None,
        route=(rc1, rc2),
        freshness_seconds=None,
        required=True,
    )

    rc_non_contiguous = RouteCandidate(provider="p3", provenance_family="f3", ordinal=2)
    with pytest.raises(
        ValueError, match="route ordinals must be contiguous starting from 0"
    ):
        PlannedOperation(
            capability_key="ck",
            subject=subject,
            parameters=None,
            route=(rc1, rc_non_contiguous),
            freshness_seconds=None,
            required=True,
        )


def test_planned_operation_duplicate_providers_in_route():
    subject = OperationSubject(entity_id=1, role=SubjectRole.EVENT)
    rc1 = RouteCandidate(provider="p1", provenance_family="f1", ordinal=0)
    rc_dup_provider = RouteCandidate(provider="p1", provenance_family="f2", ordinal=1)
    with pytest.raises(ValueError, match="duplicate provider p1 in route"):
        PlannedOperation(
            capability_key="ck",
            subject=subject,
            parameters=None,
            route=(rc1, rc_dup_provider),
            freshness_seconds=None,
            required=True,
        )


def test_planned_operation_freshness_seconds_positive_int():
    subject = OperationSubject(entity_id=1, role=SubjectRole.EVENT)
    rc = RouteCandidate(provider="p1", provenance_family="f1", ordinal=0)
    PlannedOperation(
        capability_key="ck",
        subject=subject,
        parameters=None,
        route=(rc,),
        freshness_seconds=100,
        required=True,
    )
    with pytest.raises(
        ValueError, match="freshness_seconds must be a positive integer or None"
    ):
        PlannedOperation(
            capability_key="ck",
            subject=subject,
            parameters=None,
            route=(rc,),
            freshness_seconds=0,
            required=True,
        )
    with pytest.raises(
        ValueError, match="freshness_seconds must be a positive integer or None"
    ):
        PlannedOperation(
            capability_key="ck",
            subject=subject,
            parameters=None,
            route=(rc,),
            freshness_seconds=True,
            required=True,
        )


def test_planned_operation_terminal_precedence_no_duplicates():
    subject = OperationSubject(entity_id=1, role=SubjectRole.EVENT)
    rc = RouteCandidate(provider="p1", provenance_family="f1", ordinal=0)
    with pytest.raises(
        ValueError, match="terminal_precedence cannot have duplicate entries"
    ):
        PlannedOperation(
            capability_key="ck",
            subject=subject,
            parameters=None,
            route=(rc,),
            freshness_seconds=None,
            required=True,
            terminal_precedence=(TerminalClass.PARTIAL, TerminalClass.PARTIAL),
        )


def test_enrichment_plan_positive_target_event_entity_id():
    op_subject = OperationSubject(entity_id=1, role=SubjectRole.EVENT)
    rc = RouteCandidate(provider="p1", provenance_family="f1", ordinal=0)
    op = PlannedOperation(
        capability_key="ck",
        subject=op_subject,
        parameters=None,
        route=(rc,),
        freshness_seconds=None,
        required=True,
    )
    EnrichmentPlan(
        sport="football",
        target_event_entity_id=1,
        analysis_cutoff_at=FIXED_AWARE_DT,
        operations=(op,),
        contract_hash="ch",
        metric_contract_hash="mch",
        policy_config_hash="pch",
        selection_epoch=0,
    )
    with pytest.raises(
        ValueError, match="target_event_entity_id must be a positive integer"
    ):
        EnrichmentPlan(
            sport="football",
            target_event_entity_id=0,
            analysis_cutoff_at=FIXED_AWARE_DT,
            operations=(op,),
            contract_hash="ch",
            metric_contract_hash="mch",
            policy_config_hash="pch",
            selection_epoch=0,
        )


def test_enrichment_plan_rejects_bool_as_target_event_entity_id():
    op_subject = OperationSubject(entity_id=1, role=SubjectRole.EVENT)
    rc = RouteCandidate(provider="p1", provenance_family="f1", ordinal=0)
    op = PlannedOperation(
        capability_key="ck",
        subject=op_subject,
        parameters=None,
        route=(rc,),
        freshness_seconds=None,
        required=True,
    )
    with pytest.raises(
        ValueError, match="target_event_entity_id must be a positive integer"
    ):
        EnrichmentPlan(
            sport="football",
            target_event_entity_id=True,
            analysis_cutoff_at=FIXED_AWARE_DT,
            operations=(op,),
            contract_hash="ch",
            metric_contract_hash="mch",
            policy_config_hash="pch",
            selection_epoch=0,
        )


def test_enrichment_plan_rejects_naive_cutoff():
    op_subject = OperationSubject(entity_id=1, role=SubjectRole.EVENT)
    rc = RouteCandidate(provider="p1", provenance_family="f1", ordinal=0)
    op = PlannedOperation(
        capability_key="ck",
        subject=op_subject,
        parameters=None,
        route=(rc,),
        freshness_seconds=None,
        required=True,
    )
    naive_dt = datetime(2023, 1, 1, 12, 0, 0)
    with pytest.raises(ValueError, match="analysis_cutoff_at must be timezone-aware"):
        EnrichmentPlan(
            sport="football",
            target_event_entity_id=1,
            analysis_cutoff_at=naive_dt,
            operations=(op,),
            contract_hash="ch",
            metric_contract_hash="mch",
            policy_config_hash="pch",
            selection_epoch=0,
        )


def test_enrichment_plan_empty_required_strings():
    op_subject = OperationSubject(entity_id=1, role=SubjectRole.EVENT)
    rc = RouteCandidate(provider="p1", provenance_family="f1", ordinal=0)
    op = PlannedOperation(
        capability_key="ck",
        subject=op_subject,
        parameters=None,
        route=(rc,),
        freshness_seconds=None,
        required=True,
    )
    with pytest.raises(ValueError, match="sport cannot be empty"):
        EnrichmentPlan(
            sport="",
            target_event_entity_id=1,
            analysis_cutoff_at=FIXED_AWARE_DT,
            operations=(op,),
            contract_hash="ch",
            metric_contract_hash="mch",
            policy_config_hash="pch",
            selection_epoch=0,
        )


def test_enrichment_plan_operations_not_empty():
    with pytest.raises(ValueError, match="operations cannot be empty"):
        EnrichmentPlan(
            sport="football",
            target_event_entity_id=1,
            analysis_cutoff_at=FIXED_AWARE_DT,
            operations=(),
            contract_hash="ch",
            metric_contract_hash="mch",
            policy_config_hash="pch",
            selection_epoch=0,
        )


def test_enrichment_plan_non_negative_selection_epoch():
    op_subject = OperationSubject(entity_id=1, role=SubjectRole.EVENT)
    rc = RouteCandidate(provider="p1", provenance_family="f1", ordinal=0)
    op = PlannedOperation(
        capability_key="ck",
        subject=op_subject,
        parameters=None,
        route=(rc,),
        freshness_seconds=None,
        required=True,
    )
    EnrichmentPlan(
        sport="football",
        target_event_entity_id=1,
        analysis_cutoff_at=FIXED_AWARE_DT,
        operations=(op,),
        contract_hash="ch",
        metric_contract_hash="mch",
        policy_config_hash="pch",
        selection_epoch=0,
    )
    with pytest.raises(
        ValueError, match="selection_epoch must be a non-negative integer"
    ):
        EnrichmentPlan(
            sport="football",
            target_event_entity_id=1,
            analysis_cutoff_at=FIXED_AWARE_DT,
            operations=(op,),
            contract_hash="ch",
            metric_contract_hash="mch",
            policy_config_hash="pch",
            selection_epoch=-1,
        )


def test_enrichment_plan_rejects_bool_as_selection_epoch():
    op_subject = OperationSubject(entity_id=1, role=SubjectRole.EVENT)
    rc = RouteCandidate(provider="p1", provenance_family="f1", ordinal=0)
    op = PlannedOperation(
        capability_key="ck",
        subject=op_subject,
        parameters=None,
        route=(rc,),
        freshness_seconds=None,
        required=True,
    )
    with pytest.raises(
        ValueError, match="selection_epoch must be a non-negative integer"
    ):
        EnrichmentPlan(
            sport="football",
            target_event_entity_id=1,
            analysis_cutoff_at=FIXED_AWARE_DT,
            operations=(op,),
            contract_hash="ch",
            metric_contract_hash="mch",
            policy_config_hash="pch",
            selection_epoch=True,
        )


def test_enrichment_plan_duplicate_operation_identity():
    op_subject1 = OperationSubject(entity_id=1, role=SubjectRole.EVENT)
    rc1 = RouteCandidate(provider="p1", provenance_family="f1", ordinal=0)
    op1 = PlannedOperation(
        capability_key="ck1",
        subject=op_subject1,
        parameters=None,
        route=(rc1,),
        freshness_seconds=None,
        required=True,
    )
    op_subject2 = OperationSubject(entity_id=1, role=SubjectRole.EVENT)
    rc2 = RouteCandidate(provider="p2", provenance_family="f2", ordinal=0)
    op2 = PlannedOperation(
        capability_key="ck1",
        subject=op_subject2,
        parameters=None,
        route=(rc2,),
        freshness_seconds=None,
        required=True,
    )
    with pytest.raises(ValueError, match="duplicate operation identity"):
        EnrichmentPlan(
            sport="football",
            target_event_entity_id=1,
            analysis_cutoff_at=FIXED_AWARE_DT,
            operations=(op1, op2),
            contract_hash="ch",
            metric_contract_hash="mch",
            policy_config_hash="pch",
            selection_epoch=0,
        )


def test_attempt_result_non_negative_ordinal():
    subject = OperationSubject(entity_id=1, role=SubjectRole.EVENT)
    result = SourceOperationResult(status=SourceResultStatus.SUCCESS)
    AttemptResult(
        capability_key="ck",
        subject=subject,
        provider="p",
        provenance_family="f",
        ordinal=0,
        logical_request_identity="lri",
        result=result,
    )
    with pytest.raises(ValueError, match="ordinal must be a non-negative integer"):
        AttemptResult(
            capability_key="ck",
            subject=subject,
            provider="p",
            provenance_family="f",
            ordinal=-1,
            logical_request_identity="lri",
            result=result,
        )


def test_attempt_result_rejects_bool_as_ordinal():
    subject = OperationSubject(entity_id=1, role=SubjectRole.EVENT)
    result = SourceOperationResult(status=SourceResultStatus.SUCCESS)
    with pytest.raises(ValueError, match="ordinal must be a non-negative integer"):
        AttemptResult(
            capability_key="ck",
            subject=subject,
            provider="p",
            provenance_family="f",
            ordinal=True,
            logical_request_identity="lri",
            result=result,
        )


def test_capability_resolution_attempts_not_empty():
    subject = OperationSubject(entity_id=1, role=SubjectRole.EVENT)
    with pytest.raises(ValueError, match="attempts cannot be empty"):
        CapabilityResolution(
            capability_key="ck",
            subject=subject,
            attempts=(),
            selected_attempt_index=None,
            terminal_status=SourceResultStatus.SUCCESS,
        )


def test_capability_resolution_selected_attempt_index_valid():
    subject = OperationSubject(entity_id=1, role=SubjectRole.EVENT)
    result = SourceOperationResult(status=SourceResultStatus.SUCCESS)
    attempt = AttemptResult(
        capability_key="ck",
        subject=subject,
        provider="p",
        provenance_family="f",
        ordinal=0,
        logical_request_identity="lri",
        result=result,
    )
    CapabilityResolution(
        capability_key="ck",
        subject=subject,
        attempts=(attempt,),
        selected_attempt_index=0,
        terminal_status=SourceResultStatus.SUCCESS,
    )
    with pytest.raises(
        ValueError, match="selected_attempt_index must be a valid index or None"
    ):
        CapabilityResolution(
            capability_key="ck",
            subject=subject,
            attempts=(attempt,),
            selected_attempt_index=1,
            terminal_status=SourceResultStatus.SUCCESS,
        )
    with pytest.raises(
        ValueError, match="selected_attempt_index must be a valid index or None"
    ):
        CapabilityResolution(
            capability_key="ck",
            subject=subject,
            attempts=(attempt,),
            selected_attempt_index=-1,
            terminal_status=SourceResultStatus.SUCCESS,
        )


def test_capability_resolution_rejects_bool_as_selected_attempt_index():
    subject = OperationSubject(entity_id=1, role=SubjectRole.EVENT)
    result = SourceOperationResult(status=SourceResultStatus.SUCCESS)
    attempt = AttemptResult(
        capability_key="ck",
        subject=subject,
        provider="p",
        provenance_family="f",
        ordinal=0,
        logical_request_identity="lri",
        result=result,
    )
    with pytest.raises(
        ValueError, match="selected_attempt_index must be a valid index or None"
    ):
        CapabilityResolution(
            capability_key="ck",
            subject=subject,
            attempts=(attempt,),
            selected_attempt_index=True,
            terminal_status=SourceResultStatus.SUCCESS,
        )


def test_provider_identity_set_non_empty_provider():
    with pytest.raises(ValueError, match="provider cannot be empty"):
        create_provider_identity_set(provider="", participant_ids={})


def test_provider_identity_set_positive_participant_ids_keys():
    create_provider_identity_set(provider="p", participant_ids={1: "id1"})
    with pytest.raises(
        ValueError, match="participant_ids keys must be positive integers"
    ):
        create_provider_identity_set(provider="p", participant_ids={0: "id1"})
    with pytest.raises(
        ValueError, match="participant_ids keys must be positive integers"
    ):
        create_provider_identity_set(provider="p", participant_ids={-1: "id1"})


def test_provider_identity_set_rejects_bool_as_participant_ids_keys():
    with pytest.raises(
        ValueError, match="participant_ids keys must be positive integers"
    ):
        create_provider_identity_set(provider="p", participant_ids={True: "id1"})


def test_provider_identity_set_non_empty_participant_ids_values():
    with pytest.raises(
        ValueError, match="participant_ids values must be non-empty strings"
    ):
        create_provider_identity_set(provider="p", participant_ids={1: ""})


def test_provider_identity_set_defensive_copy_participant_ids_and_immutability():
    participant_ids = {1: "id1"}
    pis = create_provider_identity_set(provider="p", participant_ids=participant_ids)
    participant_ids[2] = "id2"
    assert "id2" not in pis.participant_ids.values()
    with pytest.raises(TypeError):
        pis.participant_ids[3] = "id3"


# --- CODEC VECTORS ---


def test_to_primitive_basic_types():
    assert to_primitive(123) == 123
    assert to_primitive("test") == "test"
    assert to_primitive(None) is None
    assert to_primitive(True) is True
    assert to_primitive(False) is False


@pytest.mark.parametrize(
    "dec_val,expected_str",
    [
        (Decimal("1.2300"), "1.23"),
        (Decimal("1000"), "1000"),
        (Decimal("1E+3"), "1000"),
        (Decimal("0.00000100"), "0.000001"),
        (Decimal("-0.000"), "0"),
        (Decimal("0"), "0"),
        (Decimal("-1.23"), "-1.23"),
        (Decimal("-1000"), "-1000"),
    ],
)
def test_to_primitive_decimal_vectors(dec_val, expected_str):
    assert to_primitive(dec_val) == expected_str


def test_to_primitive_decimal_invalid_rejected():
    with pytest.raises(ValueError, match="Decimal NaN or Infinity are not supported"):
        to_primitive(Decimal("NaN"))
    with pytest.raises(ValueError, match="Decimal NaN or Infinity are not supported"):
        to_primitive(Decimal("Infinity"))


def test_to_primitive_datetime():
    aware_dt = datetime(2023, 1, 1, 12, 30, 45, 123456, tzinfo=UTC)
    assert to_primitive(aware_dt) == "2023-01-01T12:30:45.123456Z"

    # Check that microseconds are NOT truncated even if they end in zeros
    dt_with_zeros = datetime(2023, 1, 1, 12, 30, 45, 120000, tzinfo=UTC)
    assert to_primitive(dt_with_zeros) == "2023-01-01T12:30:45.120000Z"

    # Timezone offset handling
    aware_dt_plus_2 = datetime(
        2023, 1, 1, 14, 30, 45, 123456, tzinfo=timezone(timedelta(hours=2))
    )
    assert to_primitive(aware_dt_plus_2) == "2023-01-01T12:30:45.123456Z"


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


def test_to_primitive_mapping_non_string_keys_rejected():
    with pytest.raises(TypeError, match="Mapping keys must be exactly str"):
        to_primitive({1: "x"})
    with pytest.raises(TypeError, match="Mapping keys must be exactly str"):
        to_primitive({1: "a", "1": "b"})


def test_to_primitive_rejects_float_and_unsupported_types():
    with pytest.raises(TypeError, match="Float values are not supported"):
        to_primitive(1.23)
    with pytest.raises(TypeError, match="Unsupported type: <class 'bytes'>"):
        to_primitive(b"abc")
    with pytest.raises(TypeError, match="Unsupported type: <class 'set'>"):
        to_primitive({1, 2})


def test_to_primitive_rejects_naive_datetime():
    naive_dt = datetime(2023, 1, 1, 12, 0, 0)
    with pytest.raises(ValueError, match="datetime must be timezone-aware"):
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
    dt_str = "2023-01-01T12:30:45.123456Z"
    expected_dt = datetime(2023, 1, 1, 12, 30, 45, 123456, tzinfo=UTC)
    assert from_primitive(datetime, dt_str) == expected_dt
    with pytest.raises(TypeError, match="Cannot convert .* to timezone-aware datetime"):
        from_primitive(datetime, "2023-01-01T12:30:45")  # Naive


def test_from_primitive_strenum():
    assert from_primitive(SubjectRole, "EVENT") == SubjectRole.EVENT
    with pytest.raises(
        TypeError, match="Unknown enum value 'UNKNOWN_ROLE' for SubjectRole"
    ):
        from_primitive(SubjectRole, "UNKNOWN_ROLE")


def test_from_primitive_dataclass():
    primitive_data = {
        "name": "test",
        "value": 1,
        "decimal_value": "1.0",
        "dt_value": "2023-01-01T12:00:00.000000Z",
        "enum_value": "EVENT",
        "optional_value": None,
        "list_value": [1, 2],
        "tuple_value": ["a", "b"],
        "mapping_value": {"k": "v"},
        "boolean_value": True,
    }
    dt = datetime(2023, 1, 1, 12, 0, 0, tzinfo=UTC)
    expected_obj = SampleTestDataclass(
        name="test",
        value=1,
        decimal_value=Decimal("1.0"),
        dt_value=dt,
        enum_value=SubjectRole.EVENT,
        optional_value=None,
        list_value=[1, 2],
        tuple_value=("a", "b"),
        mapping_value={"k": "v"},
        boolean_value=True,
    )
    assert from_primitive(SampleTestDataclass, primitive_data) == expected_obj


def test_from_primitive_dataclass_missing_required_field():
    primitive_data = {"value": "test"}
    with pytest.raises(
        ValueError, match="Missing required field 'count' for dataclass SimpleParams"
    ):
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
    assert (
        from_primitive(DataclassWithDefault, primitive_data_with_default)
        == expected_obj_custom
    )


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


def test_from_primitive_rejects_float_everywhere():
    with pytest.raises(TypeError, match="Expected int, got <class 'float'>"):
        from_primitive(int, 1.0)
    with pytest.raises(TypeError, match="Expected str, got <class 'float'>"):
        from_primitive(str, 1.0)
    with pytest.raises(TypeError, match="Float values are not allowed"):
        from_primitive(Any, 1.0)
    with pytest.raises(TypeError, match="Float values are not allowed"):
        from_primitive(object, 1.0)


def test_from_primitive_rejects_bytes_and_sets():
    with pytest.raises(TypeError, match="Bytes and sets are not allowed"):
        from_primitive(Any, b"abc")
    with pytest.raises(TypeError, match="Bytes and sets are not allowed"):
        from_primitive(object, {1, 2})


def test_from_primitive_unsupported_type_raises_error():
    class CustomClass:
        pass

    with pytest.raises(
        TypeError, match=r"Unsupported expected type: <class '.*CustomClass'>"
    ):
        from_primitive(CustomClass, CustomClass())


# --- SCHEMA VERSIONING ---


def test_schema_version_enforcement():
    # Valid schema_version
    valid_data = {"schema_version": "v1", "payload": "hello"}
    obj = from_primitive(SchemaVersionedContract, valid_data)
    assert obj.schema_version == "v1"

    # Invalid schema_version
    invalid_data = {"schema_version": "v2", "payload": "hello"}
    with pytest.raises(
        ValueError, match="schema_version mismatch: expected 'v1', got 'v2'"
    ):
        from_primitive(SchemaVersionedContract, invalid_data)


# --- IDENTITY PARAMETRIZATION (J) ---


@pytest.mark.parametrize(
    "field_name,new_value",
    [
        ("sport", "basketball"),
        ("capability_key", "different_key"),
        ("target_event_entity_id", 999),
        ("subject", OperationSubject(entity_id=999, role=SubjectRole.HOME)),
        ("provider", "other_provider"),
        ("provider_event_id", "evt_999"),
        ("provider_subject_id", "sub_999"),
        ("provider_related_subject_ids", {"team_a": "10", "team_b": "20"}),
        ("provider_competition_id", "comp_999"),
        ("provider_season_id", "seas_999"),
        ("analysis_cutoff_at", datetime(2023, 1, 1, 14, 0, 0, tzinfo=UTC)),
        ("parameters", SimpleParams(value="different", count=42)),
        ("contract_version", "2.0"),
        ("dto_version", "2.0"),
    ],
)
def test_operation_request_logical_identity_parametrized(field_name, new_value):
    base_params = SimpleParams(value="test", count=1)
    req_base = create_op_request(parameters=base_params)

    # Create copy with modified field
    kwargs = {
        "sport": req_base.sport,
        "capability_key": req_base.capability_key,
        "target_event_entity_id": req_base.target_event_entity_id,
        "subject": req_base.subject,
        "provider": req_base.provider,
        "provider_event_id": req_base.provider_event_id,
        "provider_subject_id": req_base.provider_subject_id,
        "provider_related_subject_ids": req_base.provider_related_subject_ids,
        "provider_competition_id": req_base.provider_competition_id,
        "provider_season_id": req_base.provider_season_id,
        "analysis_cutoff_at": req_base.analysis_cutoff_at,
        "parameters": req_base.parameters,
        "contract_version": req_base.contract_version,
        "dto_version": req_base.dto_version,
    }
    kwargs[field_name] = new_value
    req_mod = OperationRequest(**kwargs)

    assert req_base.logical_identity() != req_mod.logical_identity()


@pytest.mark.parametrize(
    "field_name,new_value",
    [
        ("sport", "basketball"),
        ("target_event_entity_id", 999),
        ("analysis_cutoff_at", datetime(2023, 1, 1, 14, 0, 0, tzinfo=UTC)),
        (
            "operations",
            (
                PlannedOperation(
                    capability_key="ck_modified",
                    subject=OperationSubject(entity_id=1, role=SubjectRole.EVENT),
                    parameters=None,
                    route=(
                        RouteCandidate(
                            provider="p1", provenance_family="f1", ordinal=0
                        ),
                    ),
                    freshness_seconds=None,
                    required=True,
                ),
            ),
        ),
        ("contract_hash", "modified_ch"),
        ("metric_contract_hash", "modified_mch"),
        ("policy_config_hash", "modified_pch"),
        ("selection_epoch", 999),
    ],
)
def test_enrichment_plan_plan_hash_parametrized(field_name, new_value):
    op_subject = OperationSubject(entity_id=1, role=SubjectRole.EVENT)
    rc1 = RouteCandidate(provider="p1", provenance_family="f1", ordinal=0)
    op1 = PlannedOperation(
        capability_key="ck1",
        subject=op_subject,
        parameters=None,
        route=(rc1,),
        freshness_seconds=None,
        required=True,
    )

    plan_base = EnrichmentPlan(
        sport="football",
        target_event_entity_id=1,
        analysis_cutoff_at=FIXED_AWARE_DT,
        operations=(op1,),
        contract_hash="ch",
        metric_contract_hash="mch",
        policy_config_hash="pch",
        selection_epoch=0,
    )

    kwargs = {
        "sport": plan_base.sport,
        "target_event_entity_id": plan_base.target_event_entity_id,
        "analysis_cutoff_at": plan_base.analysis_cutoff_at,
        "operations": plan_base.operations,
        "contract_hash": plan_base.contract_hash,
        "metric_contract_hash": plan_base.metric_contract_hash,
        "policy_config_hash": plan_base.policy_config_hash,
        "selection_epoch": plan_base.selection_epoch,
    }
    kwargs[field_name] = new_value
    plan_mod = EnrichmentPlan(**kwargs)

    assert plan_base.plan_hash() != plan_mod.plan_hash()


# --- KERNEL CONTRACT ROUND-TRIP (F.10) ---


def test_operation_request_round_trip():
    params = SimpleParams(value="nested_val", count=100)
    req = create_op_request(parameters=params)
    primitive = to_primitive(req)

    # Round-trip decode using generic type with postponed annotations resolved
    decoded = from_primitive(OperationRequest[SimpleParams], primitive)

    assert decoded.sport == req.sport
    assert decoded.capability_key == req.capability_key
    assert decoded.target_event_entity_id == req.target_event_entity_id
    assert decoded.subject == req.subject
    assert decoded.provider == req.provider
    assert decoded.parameters == req.parameters
    assert decoded.analysis_cutoff_at == req.analysis_cutoff_at


# --- COMPATIBILITY ---


def test_existing_source_result_status_imports_work():
    from bet.integration.source_result import SourceResultStatus

    assert SourceResultStatus.SUCCESS == "SUCCESS"


def test_existing_source_operation_result_imports_work():
    from bet.integration.source_result import SourceOperationResult

    result = SourceOperationResult(status=SourceResultStatus.SUCCESS)
    assert result.status == SourceResultStatus.SUCCESS


def test_kernel_public_re_exports_work():
    from bet.enrichment.kernel import SubjectRole, canonical_sha256

    assert SubjectRole.EVENT == "EVENT"
    assert callable(canonical_sha256)


def test_existing_dto_from_models_remain_importable():
    from bet.enrichment.models import NormalizedEventStatus

    assert NormalizedEventStatus.SCHEDULED == "SCHEDULED"
