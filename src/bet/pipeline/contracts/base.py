"""Base Pydantic v2 strict models, envelope types, and pipeline contexts."""
from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any, Mapping
from pydantic import Field

# Re-exported, not redefined: the class lives in bet.strict_model so that
# bet.models -- and through it every provider client -- can use it without
# importing this package. Two definitions would drift; this one is an alias.
from bet.strict_model import StrictBaseModel

__all_reexport__ = ["StrictBaseModel"]


class CompletionEnvelopeType(str, Enum):
    SCRIPT_EVIDENCE = "SCRIPT_EVIDENCE"
    AGENT_ARTIFACT = "AGENT_ARTIFACT"
    HUMAN_GATE = "HUMAN_GATE"
    STATE_MARKER = "STATE_MARKER"
    RUN_SUMMARY = "RUN_SUMMARY"


class ArtifactRole(str, Enum):
    PRIMARY = "PRIMARY"
    AUXILIARY = "AUXILIARY"


class ValidatedPipelineDefinition(StrictBaseModel):
    """Immutable pipeline definition context."""
    repo_root: Path
    source_head: str
    source_tree: str
    manifest_path: Path
    manifest_sha256: str
    validated_manifest: Mapping[str, Any]
    compiled_graph: Mapping[str, Any] = Field(default_factory=dict)
    contract_registry: Mapping[str, Any] = Field(default_factory=dict)


class ValidatedRunContext(StrictBaseModel):
    """Immutable pipeline run execution context."""
    definition: ValidatedPipelineDefinition
    betting_day: str
    run_id: str
    runtime_mode: str = "DRY_RUN"
    run_root: Path
    point_in_time_as_of: str | None = None
