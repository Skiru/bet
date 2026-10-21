"""epochs.DERIVED_SAMPLE_GATES (operator 2026-10-21, "all markets"): a
football derived joint's sample gate reads its two sides' marginal samples,
not the joint's own market (which SAMPLES never holds - THIN_SAMPLE_FOR_BUILDER
refused every derived football row before)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from bet.sofa import epochs
from bet.sofa.confidence import MIN_BUILDER_SAMPLE, derived_sample_refusal


def test_the_switch_goes_on_with_the_derived_group() -> None:
    at = epochs.DERIVED_SAMPLE_GATES_FROM_UTC
    assert at is not None and at.date().isoformat() == "2026-10-21"
    assert at == epochs.DERIVED_CURVES_FROM_UTC
    assert at == epochs.CARDS_CORRELATION_FROM_UTC
    assert at == epochs.DERIVED_SHEET_MARGINS_FROM_UTC
    assert epochs.derived_sample_gates("2026-10-21", at)
    # a day built before the switch is never re-gated, nor a build before it
    later = datetime(2026, 10, 22, tzinfo=UTC)
    assert not epochs.derived_sample_gates("2026-10-20", later)
    assert not epochs.derived_sample_gates("2026-10-21", at - timedelta(minutes=1))


def test_each_side_needs_the_builder_floor() -> None:
    full = MIN_BUILDER_SAMPLE
    assert derived_sample_refusal([full, full]) is None
    assert derived_sample_refusal([full, full - 1]) == "THIN_SAMPLE_FOR_BUILDER"
    assert derived_sample_refusal([full - 1, 40]) == "THIN_SAMPLE_FOR_BUILDER"
    assert derived_sample_refusal([full]) == "THIN_SAMPLE_FOR_BUILDER"


def test_the_deep_audit_reads_the_sides_of_a_marked_derived_leg() -> None:
    from scripts.sofa.audit_day_deep import shape_gates_failed

    marked = {epochs.DERIVED_SAMPLE_MARKER: [10, 12]}
    # the leg's own values are empty (no sample of the joint): not a failure
    assert shape_gates_failed(marked, 0.5, "OVER", []) == []
    thin = {epochs.DERIVED_SAMPLE_MARKER: [10, 6]}
    assert shape_gates_failed(thin, 0.5, "OVER", []) == ["THIN_SAMPLE_FOR_BUILDER"]
    # an unmarked leg is judged as before
    assert "THIN_SAMPLE_FOR_BUILDER" in shape_gates_failed({}, 0.5, "OVER", [])
