"""Contract descriptor registry for step business models."""
from __future__ import annotations

from typing import Any, Callable, Type
from pydantic import Field
from bet.pipeline.contracts.base import (
    StrictBaseModel,
    CompletionEnvelopeType,
    ArtifactRole,
)


class ContractDescriptor(StrictBaseModel):
    """Descriptor binding a business contract model to its producer/consumer metadata."""
    contract_id: str
    schema_version: int
    model_type: Any  # Type[StrictBaseModel]
    envelope_type: CompletionEnvelopeType
    producer_step: str
    consumer_steps: tuple[str, ...] = ()
    artifact_role: ArtifactRole = ArtifactRole.PRIMARY
    canonical_path_resolver: str | None = None
    current_runtime: bool = True
    migration_from_versions: tuple[int, ...] = ()
    event_scope_kind: str = "FULL_DAY"
    output_scope: str = "run"
    status_policy: tuple[str, ...] = ("PASS", "READY", "NO_ACTION_TERMINAL", "PRICE_PENDING")


class ContractRegistry:
    """Registry managing versioned step contracts."""

    def __init__(self) -> None:
        self._descriptors: dict[tuple[str, int], ContractDescriptor] = {}

    def register(self, descriptor: ContractDescriptor) -> None:
        key = (descriptor.contract_id, descriptor.schema_version)
        if key in self._descriptors:
            raise ValueError(f"Contract {key} is already registered.")
        self._descriptors[key] = descriptor

    def get(self, contract_id: str, schema_version: int) -> ContractDescriptor | None:
        return self._descriptors.get((contract_id, schema_version))

    def get_strict(self, contract_id: str, schema_version: int) -> ContractDescriptor:
        desc = self.get(contract_id, schema_version)
        if desc is None:
            raise KeyError(f"No descriptor registered for ({contract_id}, {schema_version}).")
        return desc

    def list_descriptors(self) -> list[ContractDescriptor]:
        return list(self._descriptors.values())

    def clear(self) -> None:
        self._descriptors.clear()


GLOBAL_CONTRACT_REGISTRY = ContractRegistry()
