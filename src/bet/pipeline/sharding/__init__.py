"""Specialist chunking and evidence acquisition module."""
from __future__ import annotations

from src.bet.pipeline.sharding.models import (
    WorkOrderBudgetV1,
    ChunkWorkOrderV1,
    ChunkExecutionPlanV1,
    ChunkArtifactV1,
    ChunkAggregationReceiptV1,
    FactRequirementV1,
    FactAcquisitionPlanV1,
    RetrievalReceiptV1,
    DatabaseQueryReceiptV1,
    EvidenceConflictV1,
    SourceIndependenceClusterV1,
    EvidenceBundleV1,
)
from src.bet.pipeline.sharding.lifecycle import (
    ChunkLifecycleError,
    create_chunk_execution_plan,
    validate_chunk_against_work_order,
    aggregate_chunks,
)
