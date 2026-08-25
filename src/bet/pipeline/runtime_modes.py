"""Runtime modes for the betting pipeline wrappers."""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum


class RuntimeMode(str, Enum):
    CERTIFICATION = "CERTIFICATION"
    DRY_RUN = "DRY_RUN"
    LIVE_SHADOW = "LIVE_SHADOW"
    LIVE_ANALYSIS_SHADOW = "LIVE_ANALYSIS_SHADOW"
    PRODUCTION = "PRODUCTION"


LIVE_ACK_KEY = "BET_PIPELINE_LIVE_ACK"
LIVE_ACK_VALUE = "I_UNDERSTAND_LIVE_PROVIDER_CALLS"
RUNTIME_MODE_CONTRACT_VERSION = "1"

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
        raise ValueError(f"UNKNOWN_RUNTIME_MODE: {mode}")


@dataclass(frozen=True)
class RuntimeModeCapabilities:
    provider_network_allowed: bool
    model_execution_allowed: bool
    shadow_db_read_allowed: bool
    shadow_db_write_allowed: bool
    canonical_db_read_allowed: bool
    canonical_db_write_allowed: bool
    bookmaker_access_allowed: bool
    automated_bet_placement_allowed: bool
    s9_allowed: bool
    synthetic_outputs: bool
    requires_live_ack: bool


def runtime_mode_capabilities(mode: RuntimeMode | str) -> RuntimeModeCapabilities:
    parsed = parse_runtime_mode(mode)
    if parsed is RuntimeMode.LIVE_ANALYSIS_SHADOW:
        return RuntimeModeCapabilities(
            provider_network_allowed=True,
            model_execution_allowed=True,
            shadow_db_read_allowed=True,
            shadow_db_write_allowed=True,
            canonical_db_read_allowed=True,
            canonical_db_write_allowed=False,
            bookmaker_access_allowed=False,
            automated_bet_placement_allowed=False,
            s9_allowed=False,
            synthetic_outputs=False,
            requires_live_ack=True,
        )
    if parsed is RuntimeMode.PRODUCTION:
        return RuntimeModeCapabilities(
            provider_network_allowed=True,
            model_execution_allowed=True,
            shadow_db_read_allowed=False,
            shadow_db_write_allowed=False,
            canonical_db_read_allowed=True,
            canonical_db_write_allowed=True,
            bookmaker_access_allowed=False,
            automated_bet_placement_allowed=False,
            s9_allowed=False,
            synthetic_outputs=False,
            requires_live_ack=False,
        )
    return RuntimeModeCapabilities(
        provider_network_allowed=False,
        model_execution_allowed=False,
        shadow_db_read_allowed=False,
        shadow_db_write_allowed=False,
        canonical_db_read_allowed=False,
        canonical_db_write_allowed=False,
        bookmaker_access_allowed=False,
        automated_bet_placement_allowed=False,
        s9_allowed=False,
        synthetic_outputs=True,
        requires_live_ack=parsed is RuntimeMode.LIVE_SHADOW,
    )


def validate_runtime_mode_acks(
    mode: RuntimeMode | str, env: dict[str, str] | None = None
) -> tuple[bool, str]:
    """Validate that the required environment acknowledgements are set for the given mode.

    Returns (is_valid, error_msg).
    """
    mode_enum = parse_runtime_mode(mode)
    environment = os.environ if env is None else env

    if runtime_mode_capabilities(mode_enum).requires_live_ack:
        live_ack = environment.get(LIVE_ACK_KEY, "")
        if live_ack != LIVE_ACK_VALUE:
            if env is not None:
                raise ValueError("LIVE_ACK_REQUIRED")
            return False, "BLOCKED_LIVE_NETWORK_ACK_MISSING"

    elif mode_enum == RuntimeMode.PRODUCTION:
        write_ack = environment.get(WRITE_ACK_KEY, "")
        if write_ack != WRITE_ACK_VALUE:
            return False, "BLOCKED_WRITE_ACK_MISSING"

    return True, ""
