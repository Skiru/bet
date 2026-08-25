import pytest

from bet.pipeline.manifest import PipelineManifestError
from bet.pipeline.stage_conditions import StageConditionContext, StageConditionRegistry


def _context():
    return StageConditionContext(sport="football", manifest_version=1)


def test_registered_condition_returns_typed_result():
    registry = StageConditionRegistry()
    registry.register("football_only", lambda context: context.sport == "football")
    assert registry.evaluate("football_only", _context()) is True


def test_unknown_condition_fails_closed():
    with pytest.raises(PipelineManifestError, match="Unknown stage condition"):
        StageConditionRegistry().evaluate("unknown", _context())


def test_condition_exception_fails_closed():
    registry = StageConditionRegistry()

    def broken(_context):
        raise RuntimeError("boom")

    registry.register("broken", broken)
    with pytest.raises(PipelineManifestError, match="failed closed"):
        registry.evaluate("broken", _context())


def test_non_boolean_condition_fails_closed():
    registry = StageConditionRegistry()
    registry.register("bad_type", lambda _context: "yes")
    with pytest.raises(PipelineManifestError, match="non-boolean"):
        registry.evaluate("bad_type", _context())
