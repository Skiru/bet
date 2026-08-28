"""One HTTP-GET-to-``SourceOperationResult`` path, shared by the non-API-Sports
clients that produce evidence bundles.

The API-Sports family gets this from ``APISportsClient._request_with_evidence``,
whose body is specific to that platform's ``{"response": [...], "errors": {...}}``
envelope. Providers outside that family (Highlightly, Bzzoiro) need the same
seventeen branches -- missing key, exhausted quota, transport error, 401/403/404/
429/5xx, undecodable body, provider error payload -- and every one of them has to
land on a *specific* ``SourceResultStatus``, because the whole point of that enum
is that ENRICH can tell "the provider has nothing for this team" apart from "the
key is wrong" and from "the day's quota is gone".

Duplicating that per provider is how the two copies drift: the second provider
gets a branch the first is missing, a run reports NOT_FOUND where the other would
report RATE_LIMITED, and the preflight advice printed from it is wrong. So it
lives here once, and a provider supplies only what is genuinely its own: the auth
header (``_build_headers``), how its quota headers are spelled
(``_extract_quota_metadata``) and how it reports errors inside a 200 body
(``_classify_provider_payload_error``).
"""
from __future__ import annotations

import json
from typing import Any

import requests

from bet.integration.evidence import write_source_operation_bundle
from bet.integration.source_result import SourceOperationResult, SourceResultStatus


class EvidenceRequestMixin:
    """``_request_with_evidence`` plus the two result-shaping helpers.

    Mix in *before* ``BaseAPIClient``; it relies on ``self.api_name``,
    ``self.base_url``, ``self.api_key``, ``self.rate_limiter``, ``self.TIMEOUT``
    and ``self._build_headers()`` from there.
    """

    @staticmethod
    def _extract_quota_metadata(
        headers: dict[str, Any] | None,
    ) -> dict[str, int | str | None]:
        """Provider quota figures lifted from response headers. ``{}`` by default:
        a provider that publishes none reports none, rather than guessing."""
        return {}

    @staticmethod
    def _classify_provider_payload_error(
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        """``{"status", "error_code"}`` when a 200 body is actually an error, else
        None. Default: a 200 is a 200."""
        return None

    def _check_api_key(self) -> bool:
        return bool(self.api_key)

    def _request_with_evidence(
        self,
        *,
        endpoint: str,
        params: dict[str, Any] | None,
        operation: str,
        source_event_id: str | None = None,
    ) -> SourceOperationResult[Any]:
        from bet.integration.evidence import persist_response_evidence
        from bet.integration.telemetry_wrapper import wrap_request

        if not self._check_api_key():
            return SourceOperationResult(
                status=SourceResultStatus.AUTHENTICATION_ERROR,
                provider=self.api_name,
                operation=operation,
                error_code="missing_api_key",
            )

        if not self.rate_limiter.can_request(self.api_name, 1):
            return SourceOperationResult(
                status=SourceResultStatus.RATE_LIMITED,
                provider=self.api_name,
                operation=operation,
                error_code="quota_exhausted",
                retryable=True,
            )

        url = f"{self.base_url}{endpoint}"
        result = wrap_request(
            provider=self.api_name,
            request_fn=requests.get,
            url=url,
            params=params,
            headers=self._build_headers(),
            timeout=self.TIMEOUT,
            scope_id=endpoint,
        )
        self.rate_limiter.record_request(self.api_name, endpoint, 1)
        quota_metadata = self._extract_quota_metadata(result.headers)

        evidence_refs = []
        if result.status_code is not None:
            try:
                evidence_ref = persist_response_evidence(
                    operation=operation,
                    url=url,
                    params=params,
                    response=result,
                    source_event_id=source_event_id,
                )
                evidence_refs.append(evidence_ref)
            except Exception:
                return SourceOperationResult(
                    status=SourceResultStatus.EVIDENCE_ERROR,
                    provider=self.api_name,
                    operation=operation,
                    http_status=result.status_code,
                    error_code="evidence_persist_failed",
                    quota_metadata=quota_metadata,
                )

        if result.error and result.status_code is None:
            return SourceOperationResult(
                status=SourceResultStatus.TRANSPORT_ERROR,
                provider=self.api_name,
                operation=operation,
                error_code=result.error.type or "transport_error",
                retryable=bool(result.error.retryable),
                evidence_refs=tuple(evidence_refs),
                retry_count=result.retry_count,
                quota_metadata=quota_metadata,
            )

        status_code = result.status_code or 0
        if status_code == 401:
            return SourceOperationResult(
                status=SourceResultStatus.AUTHENTICATION_ERROR,
                provider=self.api_name,
                operation=operation,
                http_status=401,
                error_code="http_401",
                evidence_refs=tuple(evidence_refs),
                quota_metadata=quota_metadata,
            )
        if status_code == 403:
            return SourceOperationResult(
                status=SourceResultStatus.BLOCKED,
                provider=self.api_name,
                operation=operation,
                http_status=403,
                error_code="http_403",
                evidence_refs=tuple(evidence_refs),
                quota_metadata=quota_metadata,
            )
        if status_code == 404:
            return SourceOperationResult(
                status=SourceResultStatus.NOT_FOUND,
                provider=self.api_name,
                operation=operation,
                http_status=404,
                error_code="http_404",
                evidence_refs=tuple(evidence_refs),
                quota_metadata=quota_metadata,
            )
        if status_code == 429:
            return SourceOperationResult(
                status=SourceResultStatus.RATE_LIMITED,
                provider=self.api_name,
                operation=operation,
                http_status=429,
                error_code="http_429",
                retryable=True,
                evidence_refs=tuple(evidence_refs),
                quota_metadata=quota_metadata,
            )
        if status_code >= 400:
            return SourceOperationResult(
                status=SourceResultStatus.UPSTREAM_ERROR,
                provider=self.api_name,
                operation=operation,
                http_status=status_code,
                error_code=f"http_{status_code}",
                evidence_refs=tuple(evidence_refs),
                quota_metadata=quota_metadata,
            )

        try:
            payload = json.loads(result.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return SourceOperationResult(
                status=SourceResultStatus.PARSE_ERROR,
                provider=self.api_name,
                operation=operation,
                http_status=status_code,
                error_code="json_decode_error",
                evidence_refs=tuple(evidence_refs),
                quota_metadata=quota_metadata,
            )

        if isinstance(payload, dict):
            provider_error = self._classify_provider_payload_error(payload)
            if provider_error is not None:
                return SourceOperationResult(
                    status=provider_error["status"],
                    provider=self.api_name,
                    operation=operation,
                    http_status=status_code,
                    error_code=provider_error["error_code"],
                    evidence_refs=tuple(evidence_refs),
                    quota_metadata=quota_metadata,
                )

        return SourceOperationResult(
            status=SourceResultStatus.SUCCESS,
            value=payload,
            provider=self.api_name,
            operation=operation,
            request_identity=evidence_refs[0].request_identity if evidence_refs else "",
            evidence_refs=tuple(evidence_refs),
            http_status=status_code,
            retry_count=result.retry_count,
            quota_metadata=quota_metadata,
        )

    def _bundle_result(
        self,
        *,
        result: SourceOperationResult[Any],
        parser_version: str,
        operation_name: str,
        source_event_refs: list[str],
        value: dict[str, Any],
        parser_diagnostics: dict[str, Any],
        forced_status: SourceResultStatus | None = None,
    ) -> SourceOperationResult[dict[str, Any]]:
        bundle_id = ""
        if result.evidence_refs:
            try:
                bundle_id, _ = write_source_operation_bundle(
                    registered_source_key=self.api_name,
                    operation_name=operation_name,
                    request_identity=result.request_identity,
                    parser_version=parser_version,
                    source_event_refs=source_event_refs,
                    evidence_refs=list(result.evidence_refs),
                )
            except Exception:
                return SourceOperationResult(
                    status=SourceResultStatus.EVIDENCE_ERROR,
                    provider=self.api_name,
                    operation=operation_name,
                    request_identity=result.request_identity,
                    evidence_refs=result.evidence_refs,
                    http_status=result.http_status,
                    error_code="bundle_manifest_failed",
                    quota_metadata=result.quota_metadata,
                )

        return SourceOperationResult(
            status=forced_status or SourceResultStatus.SUCCESS,
            value=value,
            provider=self.api_name,
            operation=operation_name,
            request_identity=result.request_identity,
            evidence_refs=result.evidence_refs,
            bundle_id=bundle_id,
            http_status=result.http_status,
            quota_metadata=result.quota_metadata,
            parser_diagnostics=parser_diagnostics,
            parser_version=parser_version,
            normalization_version=parser_version,
        )

    def _schema_error(
        self,
        result: SourceOperationResult[Any],
        error_code: str,
    ) -> SourceOperationResult[Any]:
        return SourceOperationResult(
            status=SourceResultStatus.SCHEMA_ERROR,
            provider=self.api_name,
            operation=result.operation,
            request_identity=result.request_identity,
            evidence_refs=result.evidence_refs,
            http_status=result.http_status,
            error_code=error_code,
            quota_metadata=result.quota_metadata,
        )
