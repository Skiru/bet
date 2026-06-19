from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any


class TransportResult:
    def __init__(
        self,
        raw_data: Any,
        cache_hit: bool = False,
        http_status: int | None = None,
        error: str = "",
    ):
        self.raw_data = raw_data
        self.cache_hit = cache_hit
        self.http_status = http_status
        self.error = error


class BaseTransport:
    def fetch(
        self, url_or_path: str, params: Mapping[str, Any] | None = None
    ) -> TransportResult:
        raise NotImplementedError


class LocalFileTransport(BaseTransport):
    def fetch(
        self, url_or_path: str, params: Mapping[str, Any] | None = None
    ) -> TransportResult:
        p = Path(url_or_path)
        if not p.exists():
            return TransportResult(
                None, error=f"File not found: {url_or_path}", http_status=404
            )
        try:
            if p.suffix == ".json":
                with open(p, encoding="utf-8") as f:
                    return TransportResult(
                        json.load(f), cache_hit=True, http_status=200
                    )
            else:
                return TransportResult(p.read_bytes(), cache_hit=True, http_status=200)
        except Exception as e:
            return TransportResult(None, error=str(e), http_status=500)
