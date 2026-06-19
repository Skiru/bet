from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from bet.enrichment.football_data_foundation.connector_kernel.access import (
    AccessRequirement,
)
from bet.enrichment.football_data_foundation.connector_kernel.pagination import (
    PaginationModel,
)
from bet.enrichment.football_data_foundation.connector_kernel.state import (
    CapabilityState,
)
from bet.integration.source_result import SourceOperationResult


class BaseConnector:
    provider: str
    source_family: str
    source_class: str
    supported_operations: Sequence[str]
    supported_capabilities: Sequence[str]
    access_requirements: Sequence[AccessRequirement]
    dependency_requirements: Sequence[str]
    transport_type: str
    pagination_model: PaginationModel
    cache_policy: str
    state_model: str
    evidence_policy: str
    drift_policy: str

    def execute(self, operation: str, **kwargs: Any) -> SourceOperationResult[Any]:
        raise NotImplementedError
