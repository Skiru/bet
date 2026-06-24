from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from bet.enrichment.multisport_foundation.source_inventory import FOOTBALL_ERA_SOURCE_KEYS, TARGET_SPORTS, build_source_inventory, source_inventory_report_payload
from bet.enrichment.multisport_foundation.verifier import verify_source_inventory


def test_every_football_source_is_accounted_for() -> None:
    keys = {entry.source_key for entry in build_source_inventory()}
    assert set(FOOTBALL_ERA_SOURCE_KEYS) <= keys
    assert len(keys) == len(FOOTBALL_ERA_SOURCE_KEYS)


def test_every_source_has_transfer_decision() -> None:
    for entry in build_source_inventory():
        assert entry.transfer_decision in {"transfer_direct", "transfer_as_pattern", "football_only_reference", "deferred_probe_only", "blocked_terms_or_access", "not_applicable_to_target_sports"}


def test_no_probe_source_can_be_production_selectable() -> None:
    for entry in build_source_inventory():
        if entry.transfer_decision in {"deferred_probe_only", "blocked_terms_or_access"}:
            assert "production_dependency_without_terms_review" in entry.forbidden_uses
            assert "claiming_source_bound_shadow_ready" in entry.forbidden_uses


def test_football_only_sources_do_not_block_multisport() -> None:
    for entry in build_source_inventory():
        if entry.transfer_decision == "football_only_reference":
            assert entry.target_sports == ()
            assert "blocking_multisport_pass_when_unavailable" in entry.forbidden_uses


def test_direct_multisport_sources_have_target_sports() -> None:
    for entry in build_source_inventory():
        if entry.transfer_decision == "transfer_direct":
            assert set(entry.target_sports) <= set(TARGET_SPORTS)
            assert entry.target_sports


def test_esports_sources_have_terms_review_policy() -> None:
    for entry in build_source_inventory():
        if entry.source_family == "esports_multisport_addition":
            assert entry.terms_or_access_review_required is True
            assert "terms_review_proof" in entry.allowed_proof_levels


def test_no_source_has_no_proof_policy() -> None:
    for entry in build_source_inventory():
        assert entry.allowed_proof_levels
        assert "no_proof" not in entry.allowed_proof_levels


def test_source_inventory_report_is_pretty_sorted_json() -> None:
    payload = source_inventory_report_payload()
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    assert "\n  " in rendered
    assert payload["source_count"] == len(FOOTBALL_ERA_SOURCE_KEYS)


def test_inventory_verifier_passes() -> None:
    result = verify_source_inventory()
    assert result.verdict == "PASS", result.to_json()
