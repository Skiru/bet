"""Re-export shim: the implementation moved to ``bet.canonical_json``.

It is a self-contained JSON canonicaliser with no pipeline dependencies, and
``bet.models`` needs it at import time. Leaving it under ``bet.pipeline.contracts``
meant every provider client loaded the S0-S10 package -- including its manifest
validator, which raises when the legacy manifest's script paths go stale.
"""

from bet.canonical_json import (  # noqa: F401
    bytes_canonical_json,
    dumps_canonical_json,
    hash_canonical_json,
)

__all__ = ["dumps_canonical_json", "bytes_canonical_json", "hash_canonical_json"]
