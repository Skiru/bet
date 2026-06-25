"""Contracts and constants for the pipeline orchestrator."""
from __future__ import annotations

from enum import Enum


class BlockedReason(str, Enum):
    BLOCKED_WAITING_FOR_AGENT_ARTIFACT = "BLOCKED_WAITING_FOR_AGENT_ARTIFACT"
    BLOCKED_WAITING_FOR_HUMAN_APPROVAL = "BLOCKED_WAITING_FOR_HUMAN_APPROVAL"


class OrchestratorException(Exception):
    """Base exception for orchestrator errors."""
    pass


class OrchestratorBlockError(OrchestratorException):
    """Exception representing a standard closed-fail block during execution."""
    def __init__(self, message: str, step_id: str, reason: BlockedReason | str) -> None:
        super().__init__(message)
        self.step_id = step_id
        self.reason = reason
