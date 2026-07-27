"""Strict canonical JSON serialization and hashing utility."""
from __future__ import annotations

import json
import hashlib
from decimal import Decimal
from typing import Any


def _canonical_encoder(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        # Format decimal as string without trailing zeros exponent noise
        return str(obj)
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if hasattr(obj, "dict"):
        return obj.dict()
    if isinstance(obj, (set, tuple)):
        return list(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def dumps_canonical_json(data: Any) -> str:
    """Serialize Python object to deterministic canonical JSON string.

    Key features:
    - Sorted keys
    - Separators without extra whitespace (',', ':')
    - UTF-8 string encoding
    - Single trailing newline
    """
    json_str = json.dumps(
        data,
        default=_canonical_encoder,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return json_str + "\n"


def bytes_canonical_json(data: Any) -> bytes:
    """Serialize Python object to canonical JSON bytes."""
    return dumps_canonical_json(data).encode("utf-8")


def hash_canonical_json(data: Any) -> str:
    """Compute SHA-256 hex digest of canonical JSON data."""
    return hashlib.sha256(bytes_canonical_json(data)).hexdigest()
