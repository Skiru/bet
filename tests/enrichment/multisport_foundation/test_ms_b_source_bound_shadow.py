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
    assert artifact.status == "BLOCKED_NO_CREDENTIALS"
    assert artifact.production_selectable is False
    assert artifact.betting_decisions_enabled is False
    assert artifact.manual_authorization_required is True
    result = verify_shadow_artifacts([artifact])
    assert result.verdict == "PASS", result.to_json()


def test_various_blocked_corpus_records_statuses() -> None:
    # BLOCKED_PROVIDER_ACCESS
    rec_access = build_blocked_corpus_record("pandascore", "cs2", "BLOCKED_PROVIDER_ACCESS", "matches", "access denied")
    art_access = build_source_bound_shadow("cs2", [rec_access], ("fixture_identity", "participants"))
    assert art_access.status == "BLOCKED_PROVIDER_ACCESS"
    assert art_access.production_selectable is False
    assert art_access.betting_decisions_enabled is False
    assert art_access.manual_authorization_required is True
    assert verify_shadow_artifacts([art_access]).verdict == "PASS"

    # BLOCKED_PROVIDER_TERMS_OR_SCOPE
    rec_terms = build_blocked_corpus_record("pandascore", "cs2", "BLOCKED_PROVIDER_TERMS_OR_SCOPE", "matches", "terms limit")
    art_terms = build_source_bound_shadow("cs2", [rec_terms], ("fixture_identity", "participants"))
    assert art_terms.status == "BLOCKED_PROVIDER_TERMS_OR_SCOPE"
    assert art_terms.production_selectable is False
    assert art_terms.betting_decisions_enabled is False
    assert art_terms.manual_authorization_required is True
    assert verify_shadow_artifacts([art_terms]).verdict == "PASS"

    # REAL_PROVIDER_ACCESS_OBSERVED_BUT_MAPPING_INSUFFICIENT explicitly
    rec_mapping = build_blocked_corpus_record("pandascore", "cs2", "REAL_PROVIDER_ACCESS_OBSERVED_BUT_MAPPING_INSUFFICIENT", "matches", "mapping insufficient")
    art_mapping = build_source_bound_shadow("cs2", [rec_mapping], ("fixture_identity", "participants"))
    assert art_mapping.status == "REAL_PROVIDER_ACCESS_OBSERVED_BUT_MAPPING_INSUFFICIENT"
    assert art_mapping.production_selectable is False
    assert art_mapping.betting_decisions_enabled is False
    assert art_mapping.manual_authorization_required is True
    assert verify_shadow_artifacts([art_mapping]).verdict == "PASS"


def test_source_bound_shadow_report_generation() -> None:
    from bet.enrichment.multisport_foundation.source_bound_shadow import write_source_bound_shadow_status_by_sport_report
    path = "/tmp/source_bound_shadow_status_by_sport.json"
    written_path = write_source_bound_shadow_status_by_sport_report(path)
    assert Path(written_path).exists()

    with open(written_path, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    expected_sports = {"basketball", "volleyball", "hockey", "tennis", "cs2", "dota2", "valorant"}
    assert set(data.keys()) == expected_sports

    # Check formatting: pretty printed with 2 space indent (checking characters)
    raw_content = Path(written_path).read_text(encoding="utf-8")
    assert "\n  " in raw_content
    # Check no raw secrets/headers/tokens/API keys/cookies
    cleaned_data = {}
    for sp, info in data.items():
        cleaned_info = {}
        for k, v in info.items():
            if k == "manual_authorization_required":
                continue
            if isinstance(v, str) and len(v) >= 32:
                from bet.enrichment.multisport_foundation.fail_closed import PASS_B_STATUSES
                if v in PASS_B_STATUSES:
                    v = "<valid_status>"
            cleaned_info[k] = v
        cleaned_data[sp] = cleaned_info
    from bet.enrichment.multisport_foundation.provider_corpus import contains_raw_secret
    assert not contains_raw_secret(cleaned_data)

    for sport, info in data.items():
        assert info["sport"] == sport
        assert info["status"] == "BLOCKED_PROVIDER_MAPPING_NOT_FOUND"
        assert info["source_keys"] == []
        assert info["corpus_ids"] == []
        assert info["blocked_reason"] == "No usable provider corpus record exists for this sport."
        assert info["manual_authorization_required"] is True
        assert info["production_selectable"] is False
        assert info["betting_decisions_enabled"] is False
        assert isinstance(info["unknown_fields"], list)
        assert len(info["unknown_fields"]) >= 4


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
