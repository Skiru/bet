"""Explicit versioned migration adapters for step artifacts."""
from __future__ import annotations

from typing import Any, Callable


class MigrationAdapterError(ValueError):
    """Raised when an explicit migration adapter fails or is missing."""
    pass


# Migration function signature: (payload: dict[str, Any]) -> dict[str, Any]
_MIGRATION_REGISTRY: dict[tuple[str, int, int], Callable[[dict[str, Any]], dict[str, Any]]] = {}


def register_migration_adapter(
    contract_id: str,
    from_version: int,
    to_version: int,
    adapter_fn: Callable[[dict[str, Any]], dict[str, Any]],
) -> None:
    """Register an explicit migration adapter function."""
    key = (contract_id, from_version, to_version)
    _MIGRATION_REGISTRY[key] = adapter_fn


def migrate_artifact_payload(
    contract_id: str,
    from_version: int,
    to_version: int,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Migrate payload from from_version to to_version using a registered adapter."""
    if from_version == to_version:
        return payload

    key = (contract_id, from_version, to_version)
    adapter = _MIGRATION_REGISTRY.get(key)
    if adapter is None:
        raise MigrationAdapterError(
            f"No migration adapter registered for {contract_id} from v{from_version} to v{to_version}."
        )
    return adapter(payload)


# Example migration adapter for S7b (v1 -> v2)
def _migrate_s7b_v1_to_v2(payload: dict[str, Any]) -> dict[str, Any]:
    migrated = dict(payload)
    migrated["schema_version"] = 2
    if "operator_workflow" not in migrated:
        migrated["operator_workflow"] = "SUPERBET_MANUAL_BET_BUILDER"
    if "operator_availability_asserted" not in migrated:
        migrated["operator_availability_asserted"] = False
    return migrated


# Example migration adapter for S8 (v1 -> v2)
def _migrate_s8_v1_to_v2(payload: dict[str, Any]) -> dict[str, Any]:
    migrated = dict(payload)
    migrated["schema_version"] = 2
    if "operator_workflow" not in migrated:
        migrated["operator_workflow"] = "SUPERBET_MANUAL_BET_BUILDER"
    if "idea_groups" not in migrated:
        migrated["idea_groups"] = []
    return migrated


register_migration_adapter("S7B_SUPERBET_MANUAL_MAPPING", 1, 2, _migrate_s7b_v1_to_v2)
register_migration_adapter("S8_SUPERBET_MANUAL_QUOTE_PACK", 1, 2, _migrate_s8_v1_to_v2)
