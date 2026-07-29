import json
from pathlib import Path

from bet.enrichment.football_data_foundation.source_bound_activation.runner import run_activation_candidate
from tests.enrichment.football_data_foundation.test_source_bound_activation_loader import create_mock_bundle


def test_runner_writes_only_activation_reports(tmp_path: Path) -> None:
    # 1. Setup mock source bound shadow files
    create_mock_bundle(tmp_path)

    # 2. Run activation candidate
    output_root = tmp_path / "reports/football_data_foundation/source_bound_activation/worldcup2026_norway_senegal"
    result = run_activation_candidate(
        project_root=tmp_path,
        fixture_slug="worldcup2026-norway-senegal",
        output_root=output_root,
    )

    # 3. Assert verdict is PASS
    assert result["verdict"] == "PASS"
    assert result["activation_status"] == "ACTIVATION_CANDIDATE_SHADOW_ONLY"

    # 4. Verify exact output files are written and no other files are in output_root
    expected_files = {
        "activation_candidate.json",
        "activation_candidate.md",
        "activation_candidate_verifier_result.json",
        "integration_inventory.json",
        "README.md"
    }

    actual_files = {p.name for p in output_root.iterdir() if p.is_file()}
    assert actual_files == expected_files

    # 5. Verify the files are pretty printed JSON and contains valid values
    candidate_json = json.loads((output_root / "activation_candidate.json").read_text(encoding="utf-8"))
    assert candidate_json["decision"]["status"] == "ACTIVATION_CANDIDATE_SHADOW_ONLY"
    assert candidate_json["decision"]["selectable_for_production"] is False

    verifier_json = json.loads((output_root / "activation_candidate_verifier_result.json").read_text(encoding="utf-8"))
    assert verifier_json["verdict"] == "PASS"

    inventory_json = json.loads((output_root / "integration_inventory.json").read_text(encoding="utf-8"))
    assert inventory_json["safe_integration_choice"] == "new shadow-only facade module; no existing production route edited"
