"""Backward-compatibility shim — canonical location: src/bet/api_clients/

All API client modules now live in src/bet/api_clients/.
This shim re-exports everything for scripts that still use `from api_clients import ...`.
"""

import sys
from pathlib import Path

# Ensure src/ is on path so bet.api_clients resolves
_SRC_DIR = Path(__file__).resolve().parent.parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

# Re-export everything from the canonical package
from bet.api_clients import (  # noqa: F401
    RateLimiter,
    BaseAPIClient,
    APISportsClient,
    CLIENT_REGISTRY,
    get_client,
)
from bet.api_clients.base_client import APIRateLimitError, APIError  # noqa: F401

# Individual module re-exports for `from api_clients.module import X` patterns
# These work because the .py files still exist here as copies during transition.
# Eventually all imports should use `from bet.api_clients.module import X`.
