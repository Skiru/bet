from __future__ import annotations

import pytest
from dataclasses import replace

from bet.enrichment.multisport_foundation.live_observation import (
    LiveObservationArtifact,
    build_live_observation,
)
from bet.enrichment.multisport_foundation.verifier import verify_live_observations


def test_status_mapping_not_found_maps_to_no_real_provider_access() -> None:
    art = build_live_observation(
        sport="cs2",
        pass_b_status="BLOCKED_PROVIDER_MAPPING_NOT_FOUND",
        source_keys=(),
        corpus_ids=(),
    )
    assert art.status == "BLOCKED_NO_REAL_PROVIDER_ACCESS"
    assert verify_live_observations([art]).verdict == "PASS"


def test_status_terms_or_scope_maps_to_terms_or_scope() -> None:
    art = build_live_observation(
        sport="cs2",
        pass_b_status="BLOCKED_PROVIDER_TERMS_OR_SCOPE",
        source_keys=(),
        corpus_ids=(),
    )
    assert art.status == "BLOCKED_PROVIDER_TERMS_OR_SCOPE"
    assert verify_live_observations([art]).verdict == "PASS"


def test_mapping_insufficient_maps_to_observed_but_live_shadow_blocked() -> None:
    art = build_live_observation(
        sport="cs2",
        pass_b_status="REAL_PROVIDER_ACCESS_OBSERVED_BUT_MAPPING_INSUFFICIENT",
        source_keys=(),
        corpus_ids=(),
    )
    assert art.status == "REAL_PROVIDER_ACCESS_OBSERVED_BUT_LIVE_SHADOW_BLOCKED_INSUFFICIENT_MAPPING"
    assert verify_live_observations([art]).verdict == "PASS"


def test_live_call_made_and_provider_access_attempted_must_be_false() -> None:
    art = build_live_observation(
        sport="cs2",
        pass_b_status="BLOCKED_PROVIDER_MAPPING_NOT_FOUND",
        source_keys=(),
        corpus_ids=(),
    )
    assert art.live_call_made is False
    assert art.provider_access_attempted is False

    with pytest.raises(ValueError, match="live_call_made must be false"):
        replace(art, live_call_made=True)

    with pytest.raises(ValueError, match="provider_access_attempted must be false"):
        replace(art, provider_access_attempted=True)


def test_production_selectable_and_betting_decisions_always_false() -> None:
    art = build_live_observation(
        sport="cs2",
        pass_b_status="BLOCKED_PROVIDER_MAPPING_NOT_FOUND",
        source_keys=(),
        corpus_ids=(),
    )
    assert art.production_selectable is False
    assert art.betting_decisions_enabled is False

    with pytest.raises(ValueError, match="production_selectable must always be false"):
        replace(art, production_selectable=True)

    with pytest.raises(ValueError, match="betting_decisions_enabled must always be false"):
        replace(art, betting_decisions_enabled=True)


def test_observation_mode_fail_closed_only() -> None:
    art = build_live_observation(
        sport="cs2",
        pass_b_status="BLOCKED_PROVIDER_MAPPING_NOT_FOUND",
        source_keys=(),
        corpus_ids=(),
    )
    assert art.observation_mode == "fail_closed_no_live_call"

    with pytest.raises(ValueError, match="observation_mode must be fail_closed_no_live_call"):
        replace(art, observation_mode="live_mode")
