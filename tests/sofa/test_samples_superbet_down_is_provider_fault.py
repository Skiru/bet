"""A fixture whose every Superbet listing raised is a provider fault, not NO_PRICE.

`fetch_available_metrics` swallowed every listing error and returned the empty
set, so SAMPLES blocked the fixture NO_PRICE ("No priced markets on Superbet").
NO_PRICE is deliberately not a provider fault, so `carry_over_on_provider_fault`
then dropped the fixture's previous good sample on a re-run during a Superbet
outage (reviewer's sim, 2026-10-02).
"""

from __future__ import annotations

from typing import Any

import pytest

from bet.sofa.config import SofaConfig
from bet.sofa.contracts import Fixture, FixtureSamples, GapReason
from bet.sofa.errors import ProviderError
from bet.sofa.samples import fetch_available_metrics, process_fixture_samples
from scripts.sofa.run_samples import carry_over_on_provider_fault


class SuperbetDown:
    def event_odds(self, sid: str) -> dict[str, Any]:
        raise ConnectionError("superbet 503")


class NoSofa:
    def __getattr__(self, name: str) -> Any:
        raise AssertionError("Sofascore was asked")


def _fixture(ids: list[str]) -> Fixture:
    return Fixture.model_construct(
        sofascore_event_id=77, superbet_event_ids=ids, sport="football"
    )


def test_every_listing_raising_is_a_provider_error() -> None:
    with pytest.raises(ProviderError, match="every Superbet listing failed"):
        fetch_available_metrics(_fixture(["1", "2"]), SuperbetDown())  # type: ignore[arg-type]


def test_no_listings_at_all_is_still_nothing_priced() -> None:
    assert fetch_available_metrics(_fixture([]), SuperbetDown()) == set()  # type: ignore[arg-type]


def test_fixture_is_blocked_provider_error_and_keeps_previous_sample() -> None:
    fresh = process_fixture_samples(
        _fixture(["1"]),
        NoSofa(),  # type: ignore[arg-type]
        None,  # type: ignore[arg-type]
        SuperbetDown(),  # type: ignore[arg-type]
        SofaConfig.from_env(),
        None,
    )
    assert fresh.readiness == "BLOCKED"
    assert [g.reason for g in fresh.gaps] == [GapReason.PROVIDER_ERROR]

    previous = FixtureSamples.model_construct(
        sofascore_event_id=77,
        readiness="READY",
        metrics={"corners_total": object()},
        gaps=[],
        players={},
    )
    kept, carried = carry_over_on_provider_fault(fresh, previous)
    assert carried is True
    assert kept.metrics == previous.metrics
