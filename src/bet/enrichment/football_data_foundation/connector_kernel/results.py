from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from numbers import Number
from typing import Any

import pandas as pd

from bet.enrichment.football_data_foundation.connector_kernel import BaseConnector
from bet.enrichment.football_data_foundation.connector_kernel.evidence import (
    EvidencePackager,
)
from bet.enrichment.football_data_foundation.normalizers import (
    flatten_multiindex_columns,
    normalize_numeric,
    normalize_value,
)
from bet.integration.source_result import SourceOperationResult, SourceResultStatus

PARSER_VERSION = "football_foundation_v2"
NORMALIZATION_VERSION = "football_foundation_v2"


def build_status_result(
    connector: BaseConnector,
    operation: str,
    status: SourceResultStatus,
    error_code: str,
    parser_diagnostics: Mapping[str, Any] | None = None,
    request_identity: str = "",
) -> SourceOperationResult[Any]:
    return SourceOperationResult(
        status=status,
        provider=connector.provider,
        operation=operation,
        request_identity=request_identity,
        error_code=error_code,
        parser_diagnostics=dict(parser_diagnostics or {}),
        parser_version=PARSER_VERSION,
        normalization_version=NORMALIZATION_VERSION,
    )


def _normalize_scalar(value: Any) -> Any:
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, bool):
        return value
    if isinstance(value, Number):
        return normalize_numeric(value)
    return normalize_value(value)


def _normalize_nested(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _normalize_nested(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_normalize_nested(item) for item in value]
    return _normalize_scalar(value)


def _normalize_mapping(record: Mapping[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in record.items():
        normalized[str(key)] = _normalize_nested(value)
    return normalized


def normalize_payload_records(raw_payload: Any) -> list[dict[str, Any]]:
    if raw_payload is None:
        return []
    if isinstance(raw_payload, pd.DataFrame):
        flat_df = flatten_multiindex_columns(raw_payload)
        records = flat_df.to_dict(orient="records")
        return [_normalize_mapping(record) for record in records]
    if isinstance(raw_payload, Mapping):
        return [_normalize_mapping(raw_payload)]
    if isinstance(raw_payload, Sequence) and not isinstance(
        raw_payload, (str, bytes, bytearray)
    ):
        normalized_records: list[dict[str, Any]] = []
        for item in raw_payload:
            if isinstance(item, Mapping):
                normalized_records.append(_normalize_mapping(item))
                continue
            normalized_records.append(
                {"value": json.dumps(_normalize_nested(item), sort_keys=True)}
            )
        return normalized_records
    return [{"value": _normalize_scalar(raw_payload)}]


def build_success_result(
    connector: BaseConnector,
    operation: str,
    capability: str,
    raw_payload: Any,
    request_identity: str,
    parser_diagnostics: Mapping[str, Any] | None = None,
    retrieved_at: str | None = None,
) -> SourceOperationResult[list[dict[str, Any]]]:
    diagnostics = dict(parser_diagnostics or {})
    normalized_records = normalize_payload_records(raw_payload)
    if not normalized_records:
        return SourceOperationResult(
            status=SourceResultStatus.VALID_EMPTY,
            value=[],
            provider=connector.provider,
            operation=operation,
            request_identity=request_identity,
            parser_diagnostics=diagnostics,
            parser_version=PARSER_VERSION,
            normalization_version=NORMALIZATION_VERSION,
        )

    evidence = EvidencePackager().create_package(
        provider=connector.provider,
        source_family=connector.source_family,
        source_class=connector.source_class,
        operation=operation,
        capability=capability,
        scope=diagnostics.get("scope", "default"),
        request_identity=request_identity,
        raw_payload=raw_payload,
        normalized_records=normalized_records,
        pagination_model=str(connector.pagination_model),
        diagnostics=diagnostics,
        retrieved_at=retrieved_at,
    )

    return SourceOperationResult(
        status=SourceResultStatus.SUCCESS,
        value=normalized_records,
        provider=connector.provider,
        operation=operation,
        request_identity=request_identity,
        parser_diagnostics=diagnostics,
        parser_version=PARSER_VERSION,
        normalization_version=NORMALIZATION_VERSION,
        schema_fingerprint=evidence.schema_fingerprint,
        bundle_id=evidence.evidence_id,
    )
