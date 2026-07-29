"""Runtime modes for the betting pipeline wrappers."""
from __future__ import annotations

import os
from enum import Enum


class RuntimeMode(str, Enum):
    CERTIFICATION = "CERTIFICATION"
    DRY_RUN = "DRY_RUN"
    LIVE_SHADOW = "LIVE_SHADOW"
    LIVE_ANALYSIS_SHADOW = "LIVE_ANALYSIS_SHADOW"
    PRODUCTION = "PRODUCTION"


LIVE_ACK_KEY = "BET_PIPELINE_LIVE_ACK"
LIVE_ACK_VALUE = "I_UNDERSTAND_LIVE_PROVIDER_CALLS"

WRITE_ACK_KEY = "BET_PIPELINE_WRITE_ACK"
WRITE_ACK_VALUE = "I_UNDERSTAND_PRODUCTION_WRITE"


def parse_runtime_mode(mode: RuntimeMode | str) -> RuntimeMode:
    """Parse runtime mode safely supporting string prefix and enum objects."""
    if hasattr(mode, "value"):
        return RuntimeMode(mode.value)

    mode_str = str(mode).upper()
    try:
        return RuntimeMode(mode_str)
    except ValueError:
        if "." in mode_str:
            clean_str = mode_str.split(".")[-1]
            try:
                return RuntimeMode(clean_str)
            except ValueError:
                pass
        return RuntimeMode.DRY_RUN


def validate_runtime_mode_acks(mode: RuntimeMode | str) -> tuple[bool, str]:
    """Validate that the required environment acknowledgements are set for the given mode.

    Returns (is_valid, error_msg).
    """
    mode_enum = parse_runtime_mode(mode)

    if mode_enum in (RuntimeMode.LIVE_SHADOW, RuntimeMode.LIVE_ANALYSIS_SHADOW):
        live_ack = os.environ.get(LIVE_ACK_KEY, "")
        if live_ack != LIVE_ACK_VALUE:
            return False, "BLOCKED_LIVE_NETWORK_ACK_MISSING"

    elif mode_enum == RuntimeMode.PRODUCTION:
        write_ack = os.environ.get(WRITE_ACK_KEY, "")
        if write_ack != WRITE_ACK_VALUE:
            return False, "BLOCKED_WRITE_ACK_MISSING"

    return True, ""
