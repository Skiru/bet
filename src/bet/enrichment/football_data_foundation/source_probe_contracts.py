from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SourceProbeResult:
    source_family: str
    import_status: str  # IMPORT_OK, IMPORT_FAILED
    dependency_status: str  # IMPORT_OK, DEPENDENCY_MISSING
    constructor_status: str  # CONSTRUCTOR_OK, CONSTRUCTOR_FAILED, UNSAFE_TO_PROBE, NOT_IMPLEMENTED
    offline_fixture_status: str  # OFFLINE_FIXTURE_AVAILABLE, OFFLINE_FIXTURE_MISSING, NOT_SUPPORTED
    declared_operations: list[str] = field(default_factory=list)
    declared_capabilities: list[str] = field(default_factory=list)
    fixture_paths: list[str] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SourceAdmissionScore:
    source_family: str
    evidence_status: str
    measured_capabilities: list[str]
    measured_limitations: list[str]
    recommended_role: str
    recommended_next_action: str
    score_breakdown: dict[str, float]
    hard_gates_failed: list[str]
    can_participate_next_phase: bool
    next_phase_kind: str
    reject_reason: str | None = None
