from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from dataclasses import replace
from bet.enrichment.multisport_foundation.provider_corpus import build_blocked_corpus_record
from bet.enrichment.multisport_foundation.source_bound_shadow import build_source_bound_shadow
from bet.enrichment.multisport_foundation.verifier import verify_shadow_artifacts


def test_blocked_provider_states_are_valid_shadow_artifacts() -> None:
    record = build_blocked_corpus_record("pandascore", "cs2", "BLOCKED_NO_CREDENTIALS", "matches", "missing PANDASCORE_API_KEY")
    artifact = build_source_bound_shadow("cs2", [record], ("fixture_identity", "participants"))
    assert artifact.status == "REAL_PROVIDER_ACCESS_OBSERVED_BUT_MAPPING_INSUFFICIENT"
    assert artifact.production_selectable is False
    assert artifact.betting_decisions_enabled is False
    result = verify_shadow_artifacts([artifact])
    assert result.verdict == "PASS", result.to_json()


def test_source_bound_shadow_ready_requires_real_sources_and_corpus_ids() -> None:
    record = build_blocked_corpus_record("pandascore", "valorant", "SOURCE_BOUND_SHADOW_READY", "matches", "source-bound replay sample")
    record = replace(record, participant_evidence=("team_one", "team_two"))
    artifact = build_source_bound_shadow("valorant", [record], ("fixture_identity", "participants"))
    assert artifact.status == "SOURCE_BOUND_SHADOW_READY"
    assert artifact.source_keys == ("pandascore",)
    assert artifact.corpus_ids
    assert verify_shadow_artifacts([artifact]).verdict == "PASS"


def test_source_bound_shadow_artifact_fails_if_production_selectable() -> None:
    artifact = build_source_bound_shadow("tennis", [], ("fixture_identity", "participants"))
    mutated = replace(artifact, production_selectable=True)
    result = verify_shadow_artifacts([mutated])
    assert result.verdict == "FAIL"
    assert any("production_selectable_forbidden" in item for item in result.failed_requirements)
