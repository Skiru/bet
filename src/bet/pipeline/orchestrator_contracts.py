"""Contracts and constants for the pipeline orchestrator."""
from __future__ import annotations

from enum import Enum


class BlockedReason(str, Enum):
    BLOCKED_WAITING_FOR_AGENT_ARTIFACT = "BLOCKED_WAITING_FOR_AGENT_ARTIFACT"
    BLOCKED_WAITING_FOR_HUMAN_APPROVAL = "BLOCKED_WAITING_FOR_HUMAN_APPROVAL"
    BLOCKED_LIVE_NETWORK_ACK_MISSING = "BLOCKED_LIVE_NETWORK_ACK_MISSING"
    BLOCKED_SCRIPT_EVIDENCE_MISSING = "BLOCKED_SCRIPT_EVIDENCE_MISSING"


class TerminalOutcome(str, Enum):
    NO_ACTION = "NO_ACTION"


class TerminalOutcomeReason(str, Enum):
    S7_HARD_GATE_NO_APPROVED_CANDIDATES = "S7_HARD_GATE_NO_APPROVED_CANDIDATES"


class TerminalNextAction(str, Enum):
    NO_BET_REVIEW_OR_UPSTREAM_DATA_ENRICHMENT = "NO_BET_REVIEW_OR_UPSTREAM_DATA_ENRICHMENT"


class OrchestratorException(Exception):
    """Base exception for orchestrator errors."""
    pass


class OrchestratorBlockError(OrchestratorException):
    """Exception representing a standard closed-fail block during execution."""
    def __init__(self, message: str, step_id: str, reason: BlockedReason | str) -> None:
        super().__init__(message)
        self.step_id = step_id
        self.reason = reason
