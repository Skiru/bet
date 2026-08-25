"""Allowlisted, side-effect-free stage condition predicates."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass(frozen=True)
class StageConditionContext:
    sport: str
    event_format: str | None = None
    market_families: tuple[str, ...] = ()
    provider_capabilities: tuple[str, ...] = ()
    runtime_configuration: dict[str, object] = field(default_factory=dict)
    manifest_version: int = 1


StageConditionPredicate = Callable[[StageConditionContext], bool]


class StageConditionRegistry:
    def __init__(self) -> None:
        self._predicates: dict[str, StageConditionPredicate] = {}

    def register(self, condition_id: str, predicate: StageConditionPredicate) -> None:
        if not condition_id or condition_id in self._predicates:
            raise ValueError(f"Invalid or duplicate condition_id: {condition_id}")
        self._predicates[condition_id] = predicate

    def contains(self, condition_id: str) -> bool:
        return condition_id in self._predicates

    def evaluate(self, condition_id: str, context: StageConditionContext) -> bool:
        from bet.pipeline.manifest import PipelineManifestError

        predicate = self._predicates.get(condition_id)
        if predicate is None:
            raise PipelineManifestError(f"Unknown stage condition: {condition_id}")
        try:
            result = predicate(context)
        except Exception as exc:
            raise PipelineManifestError(
                f"Stage condition {condition_id} failed closed: {exc}"
            ) from exc
        if not isinstance(result, bool):
            raise PipelineManifestError(
                f"Stage condition {condition_id} returned non-boolean result"
            )
        return result


GLOBAL_STAGE_CONDITION_REGISTRY = StageConditionRegistry()
