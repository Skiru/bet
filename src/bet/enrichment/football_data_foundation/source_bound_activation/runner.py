import json
from pathlib import Path
from typing import Any

from .contracts import ActivationPolicy
from .facade import build_football_source_bound_activation_candidate
from .verifier import verify_activation_candidate_payload


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_markdown(path: Path, candidate_json: dict[str, Any], verifier_json: dict[str, Any]) -> None:
    decision = candidate_json["decision"]
    provider_counts = candidate_json["provider_fact_counts"]
    lines = [
        "# Football Source-Bound Activation Candidate",
        "",
        f"- Status: `{decision['status']}`",
        f"- Fixture: `{candidate_json['fixture_slug']}`",
        f"- Production selectable: `{decision['selectable_for_production']}`",
        f"- Manual authorization required: `{decision['manual_authorization_required']}`",
        f"- Production DB write allowed: `{decision['production_db_write_allowed']}`",
        f"- Betting decision allowed: `{decision['betting_decision_allowed']}`",
        f"- Live network allowed: `{decision['live_network_allowed']}`",
        f"- Verifier verdict: `{verifier_json['verdict']}`",
        "",
        "## Provider fact counts",
        "",
        "| Provider | Facts |",
        "|---|---:|",
    ]
    for provider, count in sorted(provider_counts.items()):
        lines.append(f"| `{provider}` | `{count}` |")
    lines.extend(
        [
            "",
            "## Integration policy",
            "",
            "This is a shadow-only activation candidate. It does not enable routing, provider selection, production database writes, or betting decisions.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_activation_candidate(project_root: Path, fixture_slug: str, output_root: Path) -> dict[str, Any]:
    candidate = build_football_source_bound_activation_candidate(
        project_root=project_root,
        fixture_slug=fixture_slug,
        policy=ActivationPolicy.strict_worldcup_acceptance(),
    )
    candidate_json = candidate.to_json()
    verifier_result = verify_activation_candidate_payload(candidate_json)
    verifier_json = verifier_result.to_json()
    output_root.mkdir(parents=True, exist_ok=True)
    candidate_path = output_root / "activation_candidate.json"
    verifier_path = output_root / "activation_candidate_verifier_result.json"
    markdown_path = output_root / "activation_candidate.md"
    inventory_path = output_root / "integration_inventory.json"
    readme_path = output_root / "README.md"
    inventory = {
        "inspected_files_required": [
            "active_enrichment.py",
            "cli.py",
            "enrichment_state.py",
            "persistence_bridge.py",
            "football_service.py",
            "source_bound_shadow/runner.py",
            "source_bound_shadow/verifier.py"
        ],
        "inspected_files": [
            "src/bet/enrichment/football_data_foundation/active_enrichment.py",
            "src/bet/enrichment/football_data_foundation/cli.py",
            "src/bet/enrichment/football_data_foundation/enrichment_state.py",
            "src/bet/enrichment/football_data_foundation/persistence_bridge.py",
            "src/bet/enrichment/football_service.py",
            "src/bet/enrichment/football_data_foundation/source_bound_shadow/runner.py",
            "src/bet/enrichment/football_data_foundation/source_bound_shadow/verifier.py",
            "src/bet/enrichment/football_data_foundation/source_bound_shadow/writer.py"
        ],
        "importable_modules": [
            "bet.enrichment.football_data_foundation.active_enrichment",
            "bet.enrichment.football_data_foundation.cli",
            "bet.enrichment.football_data_foundation.enrichment_state",
            "bet.enrichment.football_data_foundation.persistence_bridge",
            "bet.enrichment.football_service"
        ],
        "existing_cli_or_service_entrypoints": [
            "bet.enrichment.football_data_foundation.cli:main",
            "bet.enrichment.football_service:FootballEnrichmentSnapshot"
        ],
        "existing_db_or_persistence_entrypoints": [
            "bet.enrichment.football_data_foundation.persistence_bridge:ProductionEnrichmentStore",
            "bet.enrichment.football_data_foundation.persistence_bridge:FileBackedProductionEnrichmentStore",
            "bet.enrichment.football_data_foundation.persistence_bridge:ProductionStoreStateAdapter"
        ],
        "safe_integration_choice": "new shadow-only facade module; no existing production route edited",
        "why_no_existing_production_route_was_edited": "Editing active_enrichment.py or football_service.py is strictly forbidden under REQ-010. Furthermore, REQ-003 explicitly states that we must not activate production routing, selectable providers, or edit provider matrices in this phase.",
        "why_no_existing_db_bridge_was_edited": "Editing persistence_bridge.py is forbidden under REQ-010, and REQ-004 bans any writes to the betting/data database during this phase to maintain a strict shadow-only boundary.",
        "activation_candidate_scope": "read accepted source-bound shadow artifacts and expose a fail-closed shadow-only candidate",
        "forbidden_activation_paths_confirmed": [
            ".env",
            "betting/**",
            "config/**",
            "configs/**",
            ".kilo/**",
            "scripts/**",
            "src/bet/db/**",
            "src/bet/pipeline/**",
            "src/bet/scrapers/**",
            "src/bet/api_clients/**",
            "src/bet/enrichment/football/**",
            "src/bet/enrichment/football_data_foundation/live_response_corpus_capture/**",
            "src/bet/enrichment/football_data_foundation/source_bound_shadow/**",
            "src/bet/enrichment/football_data_foundation/fusion/**",
            "src/bet/enrichment/football_data_foundation/certification/**",
            "src/bet/enrichment/football_data_foundation/evidence.py",
            "reports/football_data_foundation/live_response_corpus/**",
            "reports/football_data_foundation/provider_access_rescue/**",
            "reports/football_data_foundation/provider_access_rescue_v2/**",
            "reports/football_data_foundation/provider_operational_binding_v3/**"
        ],
        "future_live_test_entrypoint_contract": {
            "entrypoint": "bet.enrichment.football_data_foundation.source_bound_activation.facade:build_football_source_bound_activation_candidate",
            "parameters": {
                "project_root": "Path",
                "fixture_slug": "str",
                "policy": "ActivationPolicy | None",
                "shadow_root": "Path | None"
            },
            "return_type": "ActivationCandidate"
        }
    }
    _write_json(candidate_path, candidate_json)
    _write_json(verifier_path, verifier_json)
    _write_json(inventory_path, inventory)
    _write_markdown(markdown_path, candidate_json, verifier_json)
    readme_path.write_text(
        "# Source-Bound Activation Candidate\n\n"
        "Shadow-only facade for the accepted football source-bound enrichment bundle.\n",
        encoding="utf-8",
    )
    if verifier_result.verdict != "PASS":
        raise SystemExit(2)
    return {
        "verdict": verifier_result.verdict,
        "activation_status": candidate.decision.status,
        "activation_candidate_path": str(candidate_path),
        "activation_verifier_path": str(verifier_path),
        "integration_inventory_path": str(inventory_path),
        "provider_ids": candidate.provider_ids,
        "provider_fact_counts": candidate.provider_fact_counts,
        "score": candidate.score,
        "conflicts": candidate.conflicts,
        "production_selectable": candidate.decision.selectable_for_production,
        "manual_authorization_required": candidate.decision.manual_authorization_required,
        "production_db_write_allowed": candidate.decision.production_db_write_allowed,
        "betting_decision_allowed": candidate.decision.betting_decision_allowed,
        "live_network_allowed": candidate.decision.live_network_allowed,
    }
