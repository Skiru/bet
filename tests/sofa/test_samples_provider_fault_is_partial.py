"""A provider fault that thinned SAMPLES is PARTIAL, never OK (review
2026-10-01)."""

from __future__ import annotations

from scripts.sofa.run_samples import samples_verdict


def test_a_provider_fault_without_carry_over_is_partial() -> None:
    assert samples_verdict(ready=10, n_fixtures=12, unreachable=False,
                           coverage_partial=False, provider_faulted=1) == "PARTIAL"


def test_clean_is_ok_and_nothing_ready_is_failed() -> None:
    assert samples_verdict(ready=10, n_fixtures=12, unreachable=False,
                           coverage_partial=False, provider_faulted=0) == "OK"
    assert samples_verdict(ready=0, n_fixtures=12, unreachable=False,
                           coverage_partial=False, provider_faulted=0) == "FAILED"
