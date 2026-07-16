"""Closed registry for agent COMMAND_REQUEST operations."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


class CommandRequestError(ValueError):
    pass


@dataclass(frozen=True)
class ResolvedCommand:
    argv: list[str]
    timeout_seconds: float
    expected_exit_code: int
    postconditions: list[str]


def resolve_command_request(request: Any) -> ResolvedCommand:
    """Map a typed command ID to fixed argv; raw argv/shell text is forbidden."""
    if not isinstance(request, Mapping):
        raise CommandRequestError("COMMAND_REQUEST_MUST_BE_STRUCTURED")
    if set(request) - {"command_id", "parameters"}:
        raise CommandRequestError("COMMAND_REQUEST_UNKNOWN_FIELDS")
    command_id = request.get("command_id")
    parameters = request.get("parameters") or {}
    if not isinstance(parameters, Mapping):
        raise CommandRequestError("COMMAND_REQUEST_PARAMETERS_INVALID")
    if command_id == "WAIT_FOR_RATE_LIMIT":
        if set(parameters) != {"seconds"}:
            raise CommandRequestError("WAIT_FOR_RATE_LIMIT_PARAMETERS_INVALID")
        seconds = parameters.get("seconds")
        if isinstance(seconds, bool) or not isinstance(seconds, int) or not 1 <= seconds <= 30:
            raise CommandRequestError("WAIT_FOR_RATE_LIMIT_SECONDS_OUT_OF_RANGE")
        return ResolvedCommand(
            argv=["/bin/sleep", str(seconds)],
            timeout_seconds=float(seconds + 2),
            expected_exit_code=0,
            postconditions=["rerun_validate_agent_artifact"],
        )
    raise CommandRequestError("COMMAND_REQUEST_ID_NOT_ALLOWLISTED")
