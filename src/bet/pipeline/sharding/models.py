"""Typed models and contracts for specialist chunking and evidence acquisition."""
from __future__ import annotations

from typing import Any, Sequence
from pydantic import Field, field_validator, model_validator
from bet.pipeline.contracts.base import StrictBaseModel
from bet.pipeline.contracts.common import SourceReferenceV1, EvidenceClaimV1, _validate_sha256


class WorkOrderBudgetV1(StrictBaseModel):
    """Budget and scope limits for a specialist work order."""
    max_events_per_chunk: int = Field(default=15, ge=1, le=100)
    max_prompt_bytes: int = Field(default=32000, ge=1000)
    max_estimated_tokens: int = Field(default=8000, ge=500)
    max_retrieval_queries_per_event: int = Field(default=5, ge=0)
    max_total_retrievals_per_chunk: int = Field(default=25, ge=0)
    max_wall_time_seconds: int = Field(default=300, ge=10)
    max_retries: int = Field(default=1, ge=0)
    sequential_execution_required: bool = True


class ChunkWorkOrderV1(StrictBaseModel):
    """Work order for an individual event chunk."""
    chunk_id: str
    parent_work_order_id: str
    parent_work_order_sha256: str
    step_id: str
    betting_day: str
    run_id: str
    runtime_mode: str = "DRY_RUN"
    source_head: str
    source_tree: str
    manifest_sha256: str
    parent_plan_id: str = ""
    parent_plan_sha256: str = ""
    chunk_index: int = Field(ge=0)
    total_chunks: int = Field(ge=1)
    event_ids: tuple[str, ...]
    agent_name: str
    allowed_tools: tuple[str, ...] = ()
    input_refs: tuple[dict[str, Any], ...] = ()
    task_allowlist: tuple[str, ...] = ()
    acquisition_plan_refs: tuple[str, ...] = ()
    acquisition_plan: FactAcquisitionPlanV1 | dict[str, Any] | None = None
    hard_rules: tuple[str, ...] = ()
    forbidden_outputs: tuple[str, ...] = ()
    expected_artifact_path: str
    expected_artifact_type: str
    allowed_artifact_statuses: tuple[str, ...] = ("PASS", "NO_ACTION_TERMINAL", "BLOCK")
    attempt_number: int = 1
    attempt_id: str = ""
    budget: WorkOrderBudgetV1 = Field(default_factory=WorkOrderBudgetV1)

    @field_validator("event_ids", "allowed_tools", "input_refs", "task_allowlist", "acquisition_plan_refs", "hard_rules", "forbidden_outputs", "allowed_artifact_statuses", mode="before")
    @classmethod
    def coerce_tuples(cls, v: Any) -> tuple[Any, ...]:
        if isinstance(v, (list, tuple, set)):
            return tuple(v)
        return ()

    @model_validator(mode="after")
    def validate_chunk_bindings(self) -> ChunkWorkOrderV1:
        if not self.chunk_id or not self.parent_work_order_id:
            raise ValueError("CHUNK_WO_BINDING_EMPTY: chunk_id and parent_work_order_id are required")
        if not self.event_ids:
            raise ValueError("CHUNK_WO_BINDING_EMPTY: event_ids tuple cannot be empty")
        if not self.agent_name:
            raise ValueError("CHUNK_WO_BINDING_EMPTY: agent_name is required")
        if not self.parent_work_order_sha256 or self.parent_work_order_sha256 == "UNKNOWN" or len(self.parent_work_order_sha256) != 64:
            raise ValueError("CHUNK_WO_BINDING_EMPTY: parent_work_order_sha256 must be a valid 64-char hex SHA256")
        if not self.source_head or self.source_head == "UNKNOWN" or len(self.source_head) != 40:
            raise ValueError("CHUNK_WO_BINDING_EMPTY: source_head must be a valid 40-char commit SHA")
        if not self.source_tree or self.source_tree == "UNKNOWN" or len(self.source_tree) != 40:
            raise ValueError("CHUNK_WO_BINDING_EMPTY: source_tree must be a valid 40-char tree SHA")
        if not self.manifest_sha256 or self.manifest_sha256 == "UNKNOWN" or len(self.manifest_sha256) != 64:
            raise ValueError("CHUNK_WO_BINDING_EMPTY: manifest_sha256 must be a valid 64-char hex SHA256")
        if not self.expected_artifact_path or self.expected_artifact_path == "UNKNOWN":
            raise ValueError("CHUNK_WO_BINDING_EMPTY: expected_artifact_path is required")
        if not self.expected_artifact_type or self.expected_artifact_type == "UNKNOWN":
            raise ValueError("CHUNK_WO_BINDING_EMPTY: expected_artifact_type is required")
        return self


class ChunkExecutionPlanV1(StrictBaseModel):
    """Plan partitioning a parent event universe into deterministic chunks."""
    plan_id: str
    parent_work_order_id: str
    step_id: str
    betting_day: str
    run_id: str
    total_events: int = Field(ge=0)
    chunks: tuple[ChunkWorkOrderV1, ...]
    plan_sha256: str = ""


class ChunkArtifactV1(StrictBaseModel):
    """Artifact emitted by a single completed chunk."""
    chunk_id: str
    chunk_work_order_sha256: str = ""
    parent_work_order_id: str
    parent_work_order_sha256: str = ""
    parent_plan_id: str = ""
    parent_plan_sha256: str = ""
    chunk_index: int = Field(ge=0)
    total_chunks: int = Field(ge=1, default=1)
    status: str = "PASS"  # PASS | BLOCK | FAILED
    producer_agent_id: str
    betting_day: str = ""
    run_id: str = ""
    source_head: str = ""
    source_tree: str = ""
    manifest_sha256: str = ""
    processed_event_ids: tuple[str, ...]
    event_records: list[dict[str, Any]] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)
    receipts: list[dict[str, Any]] = Field(default_factory=list)
    chunk_sha256: str = ""

    @field_validator("processed_event_ids", mode="before")
    @classmethod
    def coerce_processed_event_ids(cls, v: Any) -> tuple[str, ...]:
        if isinstance(v, (list, tuple, set)):
            return tuple(str(x) for x in v)
        return ()

    @model_validator(mode="after")
    def validate_chunk_artifact_bindings(self) -> ChunkArtifactV1:
        if not self.chunk_id or not self.parent_work_order_id:
            raise ValueError("CHUNK_ARTIFACT_BINDING_EMPTY: chunk_id and parent_work_order_id required")
        if not self.chunk_work_order_sha256 or self.chunk_work_order_sha256 == "UNKNOWN" or len(self.chunk_work_order_sha256) != 64:
            raise ValueError("CHUNK_ARTIFACT_BINDING_EMPTY: chunk_work_order_sha256 required")
        if not self.parent_work_order_sha256 or self.parent_work_order_sha256 == "UNKNOWN" or len(self.parent_work_order_sha256) != 64:
            raise ValueError("CHUNK_ARTIFACT_BINDING_EMPTY: parent_work_order_sha256 required")
        if not self.source_head or self.source_head == "UNKNOWN" or len(self.source_head) != 40:
            raise ValueError("CHUNK_ARTIFACT_BINDING_EMPTY: source_head required")
        if not self.source_tree or self.source_tree == "UNKNOWN" or len(self.source_tree) != 40:
            raise ValueError("CHUNK_ARTIFACT_BINDING_EMPTY: source_tree required")
        if not self.manifest_sha256 or self.manifest_sha256 == "UNKNOWN" or len(self.manifest_sha256) != 64:
            raise ValueError("CHUNK_ARTIFACT_BINDING_EMPTY: manifest_sha256 required")
        return self


class ChunkAggregationReceiptV1(StrictBaseModel):
    """Receipt emitted after aggregating all chunks into a complete step artifact."""
    aggregation_id: str
    parent_work_order_id: str
    parent_plan_sha256: str
    total_chunks_expected: int = Field(ge=1)
    total_chunks_aggregated: int = Field(ge=1)
    chunk_ids: tuple[str, ...]
    chunk_artifact_hashes: tuple[str, ...]
    total_events_accounted: int = Field(ge=0)
    producer_kind: str = "DETERMINISTIC_CHUNK_AGGREGATOR"
    aggregation_code_sha256: str
    status: str = "PASS"

    @field_validator("aggregation_code_sha256")
    @classmethod
    def check_sha(cls, v: str) -> str:
        res = _validate_sha256(v)
        if res is None:
            raise ValueError("aggregation_code_sha256 cannot be None")
        return res


class FactRequirementV1(StrictBaseModel):
    """Specific fact requirement for market analysis or pricing."""
    requirement_id: str
    fact_type: str
    sport: str
    market_families_affected: tuple[str, ...] = ()
    requirement_level: str = "REQUIRED_FOR_PRICING"
    allowed_tools: tuple[str, ...] = ("bet_sqlite_query", "webfetch")
    query_templates: tuple[str, ...] = ()
    max_age_hours: int = 48
    min_independent_sources: int = 1
    conflict_policy: str = "FAIL_CLOSED"
    missing_data_action: str = "BLOCK"

    @field_validator("market_families_affected", "allowed_tools", "query_templates", mode="before")
    @classmethod
    def coerce_tuples(cls, v: Any) -> tuple[str, ...]:
        if isinstance(v, (list, set, tuple)):
            return tuple(str(x) for x in v)
        return ()


class FactAcquisitionPlanV1(StrictBaseModel):
    """Plan specifying facts to acquire for an event."""
    plan_id: str
    canonical_event_id: str
    sport: str
    requirements: tuple[FactRequirementV1, ...] = ()
    max_queries: int = 10

    @field_validator("requirements", mode="before")
    @classmethod
    def coerce_requirements(cls, v: Any) -> tuple[FactRequirementV1, ...]:
        if isinstance(v, (list, tuple)):
            res = []
            for item in v:
                if isinstance(item, dict):
                    res.append(FactRequirementV1.model_validate(item))
                elif isinstance(item, FactRequirementV1):
                    res.append(item)
            return tuple(res)
        return ()

    @field_validator("canonical_event_id")
    @classmethod
    def check_canonical_event_id(cls, v: str) -> str:
        if v == "ALL_SHORTLIST_EVENTS":
            raise ValueError("FactAcquisitionPlanV1 requires event-specific canonical_event_id, ALL_SHORTLIST_EVENTS forbidden")
        return v


class RetrievalReceiptV1(StrictBaseModel):
    """Receipt for a web fetch or external search retrieval."""
    receipt_id: str
    tool: str
    query_or_url: str
    source_publisher: str | None = None
    retrieved_at: str
    effective_at: str | None = None
    normalized_excerpt: str
    content_sha256: str
    provenance_level: str = "AGENT_ATTESTED_TOOL_RESULT"


class DatabaseQueryReceiptV1(StrictBaseModel):
    """Receipt for a direct SQLite query via bet_sqlite_query."""
    query_id: str
    query_purpose: str
    query_sql: str
    row_count: int = Field(ge=0)
    executed_at: str
    result_sha256: str
    provenance_level: str = "AGENT_ATTESTED_TOOL_RESULT"


class EvidenceConflictV1(StrictBaseModel):
    """Conflict between two or more evidence claims."""
    conflict_id: str
    canonical_event_id: str
    fact_type: str
    conflicting_claim_ids: tuple[str, ...]
    resolution_status: str = "UNRESOLVED"


class SourceIndependenceClusterV1(StrictBaseModel):
    """Groups sources that copy or aggregate each other to prevent false independent counting."""
    cluster_id: str
    cluster_name: str
    member_sources: tuple[str, ...]


class EvidenceBundleV1(StrictBaseModel):
    """Aggregated bundle of evidence claims, receipts, and conflicts for an event."""
    bundle_id: str
    canonical_event_id: str
    sport: str
    claims: list[EvidenceClaimV1] = Field(default_factory=list)
    retrieval_receipts: list[RetrievalReceiptV1] = Field(default_factory=list)
    database_receipts: list[DatabaseQueryReceiptV1] = Field(default_factory=list)
    conflicts: list[EvidenceConflictV1] = Field(default_factory=list)
    overall_provenance_level: str = "AGENT_ATTESTED_TOOL_RESULT"
