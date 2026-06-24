from __future__ import annotations

import pytest
from dataclasses import replace

from bet.enrichment.multisport_foundation.activation_candidate import (
    ActivationCandidateArtifact,
    build_activation_candidate,
)
from bet.enrichment.multisport_foundation.verifier import verify_activation_candidates


def test_no_activation_candidate_built_from_mapping_not_found() -> None:
    # Under build_activation_candidate, mapping not found maps to BLOCKED_NO_REAL_PROVIDER_ACCESS with activation_candidate=False
    art = build_activation_candidate(
        sport="basketball",
        pass_b_status="BLOCKED_PROVIDER_MAPPING_NOT_FOUND",
        source_keys=(),
        corpus_ids=(),
    )
    assert art.status == "BLOCKED_NO_REAL_PROVIDER_ACCESS"
    assert art.activation_candidate is False
    assert art.production_selectable is False
    assert art.betting_decisions_enabled is False
    assert art.manual_authorization_required is True

    # Assert that manually trying to construct an ACTIVATION_CANDIDATE_SHADOW_ONLY artifact
    # with SOURCE_BOUND_SHADOW_READY but empty source_keys or corpus_ids raises ValueError.
    with pytest.raises(ValueError, match="requires non-empty source_keys and corpus_ids"):
        ActivationCandidateArtifact(
            artifact_id="msc-activation-basketball",
            sport="basketball",
            status="ACTIVATION_CANDIDATE_SHADOW_ONLY",
            source_pass_b_status="SOURCE_BOUND_SHADOW_READY",
            source_shadow_report_path="some_path",
            source_keys=(),
            corpus_ids=(),
            activation_candidate=True,
        )


def test_activation_candidate_shadow_only_requires_valid_pass_b_status() -> None:
    # Assert that manually trying to construct ACTIVATION_CANDIDATE_SHADOW_ONLY with BLOCKED status raises ValueError.
    with pytest.raises(ValueError, match="requires Pass B status to be SOURCE_BOUND_SHADOW_READY"):
        ActivationCandidateArtifact(
            artifact_id="msc-activation-basketball",
            sport="basketball",
            status="ACTIVATION_CANDIDATE_SHADOW_ONLY",
            source_pass_b_status="BLOCKED_PROVIDER_MAPPING_NOT_FOUND",
            source_shadow_report_path="some_path",
            source_keys=("provider",),
            corpus_ids=("corpus-1",),
            activation_candidate=True,
        )


def test_activation_candidate_built_only_from_shadow_ready_with_keys_and_ids() -> None:
    art = build_activation_candidate(
        sport="basketball",
        pass_b_status="SOURCE_BOUND_SHADOW_READY",
        source_keys=("provider",),
        corpus_ids=("corpus-1",),
    )
    assert art.status == "ACTIVATION_CANDIDATE_SHADOW_ONLY"
    assert art.activation_candidate is True
    assert verify_activation_candidates([art]).verdict == "PASS"


def test_activation_candidate_boolean_only_for_shadow_only_status() -> None:
    # If status is not ACTIVATION_CANDIDATE_SHADOW_ONLY, activation_candidate must be False.
    # Trying to set it to True on a BLOCKED status raises ValueError.
    with pytest.raises(ValueError, match="activation_candidate can only be true when status is ACTIVATION_CANDIDATE_SHADOW_ONLY"):
        ActivationCandidateArtifact(
            artifact_id="msc-activation-basketball",
            sport="basketball",
            status="BLOCKED_NO_REAL_PROVIDER_ACCESS",
            source_pass_b_status="BLOCKED_PROVIDER_MAPPING_NOT_FOUND",
            source_shadow_report_path="some_path",
            source_keys=(),
            corpus_ids=(),
            activation_candidate=True,
        )


def test_production_selectable_and_betting_decisions_always_false() -> None:
    art = build_activation_candidate(
        sport="basketball",
        pass_b_status="SOURCE_BOUND_SHADOW_READY",
        source_keys=("provider",),
        corpus_ids=("corpus-1",),
    )
    # Verify that trying to set production_selectable to True raises ValueError.
    with pytest.raises(ValueError, match="production_selectable must always be false"):
        replace(art, production_selectable=True)

    # Verify that trying to set betting_decisions_enabled to True raises ValueError.
    with pytest.raises(ValueError, match="betting_decisions_enabled must always be false"):
        replace(art, betting_decisions_enabled=True)


def test_manual_authorization_required_always_true() -> None:
    art = build_activation_candidate(
        sport="basketball",
        pass_b_status="SOURCE_BOUND_SHADOW_READY",
        source_keys=("provider",),
        corpus_ids=("corpus-1",),
    )
    # Verify that trying to set manual_authorization_required to False raises ValueError.
    with pytest.raises(ValueError, match="manual_authorization_required must always be true"):
        replace(art, manual_authorization_required=False)
