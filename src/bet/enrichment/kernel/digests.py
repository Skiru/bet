from __future__ import annotations
from typing import Any
from bet.enrichment.kernel.codec import canonical_sha256

def runtime_code_digest(**x: Any) -> str:
    return canonical_sha256({"profile": "BET-RUNTIME-CODE-1", **x})

def runtime_environment_digest(x: Any) -> str:
    return canonical_sha256({"profile": "BET-RUNTIME-ENV-1", **dict(x)})

def request_identity(x: Any) -> str:
    return canonical_sha256({"profile": "BET-REQUEST-1", **dict(x)})

def operation_identity(x: Any) -> str:
    return canonical_sha256({"profile": "BET-OPERATION-1", **dict(x)})

def attempt_identity(op: str, index: int) -> str:
    if type(index) is not int or isinstance(index, bool) or index < 0:
        raise TypeError("attempt index must be a non-negative int")
    return canonical_sha256({
        "profile": "BET-ATTEMPT-1",
        "operation_identity": op,
        "attempt_index": index
    })
