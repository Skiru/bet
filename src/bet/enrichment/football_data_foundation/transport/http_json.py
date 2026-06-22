from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Mapping
from bet.enrichment.football_data_foundation.kernel.errors import ProviderCapabilityError


@dataclass(frozen=True)
class HttpJsonResponse:
    status_code: int
    body: Any
    body_hash: str
    byte_count: int
    record_count: int
    url: str

    @classmethod
    def from_raw(cls, status_code: int, raw_body_bytes: bytes, url: str) -> HttpJsonResponse:
        try:
            body = json.loads(raw_body_bytes.decode("utf-8"))
        except Exception as e:
            raise ProviderCapabilityError(f"Response is not valid JSON: {e}") from e

        if not isinstance(body, (dict, list)):
            raise ProviderCapabilityError("JSON root must be an object or list")

        body_hash = hashlib.sha256(raw_body_bytes).hexdigest()
        byte_count = len(raw_body_bytes)

        if isinstance(body, dict):
            record_count = 1
            for k, v in body.items():
                if isinstance(v, list) and len(v) > 0:
                    record_count = max(record_count, len(v))
            if record_count == 1:
                record_count = len(body)
        elif isinstance(body, list):
            record_count = len(body)
        else:
            record_count = 1

        return cls(
            status_code=status_code,
            body=body,
            body_hash=body_hash,
            byte_count=byte_count,
            record_count=record_count,
            url=url,
        )


class HttpJsonTransport:
    def get(
        self,
        url: str,
        headers: Mapping[str, str],
        timeout: float = 10.0,
        max_bytes: int = 10 * 1024 * 1024,
    ) -> HttpJsonResponse:
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                status_code = response.status
                content_length = response.headers.get("Content-Length")
                if content_length is not None and int(content_length) > max_bytes:
                    raise ProviderCapabilityError(f"Response exceeds max_bytes cap of {max_bytes}")
                
                raw_body = response.read(max_bytes + 1)
                if len(raw_body) > max_bytes:
                    raise ProviderCapabilityError(f"Response body exceeds max_bytes cap of {max_bytes}")
                
                return HttpJsonResponse.from_raw(status_code, raw_body, url)
        except urllib.error.HTTPError as e:
            raise ProviderCapabilityError(f"HTTP Error {e.code}: {e.reason}") from e
        except urllib.error.URLError as e:
            raise ProviderCapabilityError(f"URL Error: {e.reason}") from e
        except Exception as e:
            if isinstance(e, ProviderCapabilityError):
                raise
            raise ProviderCapabilityError(f"Transport error: {e}") from e


class MockHttpJsonTransport:
    def __init__(self, url_mapping: Mapping[str, Any] | None = None):
        self.url_mapping = url_mapping or {}
        self.calls: list[dict[str, Any]] = []

    def get(
        self,
        url: str,
        headers: Mapping[str, str],
        timeout: float = 10.0,
        max_bytes: int = 10 * 1024 * 1024,
    ) -> HttpJsonResponse:
        self.calls.append({
            "url": url,
            "headers": headers,
            "timeout": timeout,
            "max_bytes": max_bytes,
        })
        
        matched_body = None
        for key, body in self.url_mapping.items():
            if key in url:
                matched_body = body
                break
                
        if matched_body is None:
            raise ProviderCapabilityError(f"MockHttpJsonTransport: URL not found in mapping: {url}")
            
        raw_body_bytes = json.dumps(matched_body).encode("utf-8")
        if len(raw_body_bytes) > max_bytes:
            raise ProviderCapabilityError("Mock response exceeds max_bytes")
            
        return HttpJsonResponse.from_raw(200, raw_body_bytes, url)
