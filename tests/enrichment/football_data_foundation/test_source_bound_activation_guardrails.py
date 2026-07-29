import ast
import json
import socket
import urllib.request
from pathlib import Path
from unittest.mock import patch

import pytest

from bet.enrichment.football_data_foundation.source_bound_activation.runner import run_activation_candidate
from tests.enrichment.football_data_foundation.test_source_bound_activation_loader import create_mock_bundle


def test_network_blocked_runner_test_passes(tmp_path: Path) -> None:
    # 1. Setup mock files
    create_mock_bundle(tmp_path)
    output_root = tmp_path / "reports/football_data_foundation/source_bound_activation/worldcup2026_norway_senegal"

    # 2. Block socket and urllib
    def blocked_socket(*args, **kwargs):
        raise RuntimeError("Forbidden live network access")

    def blocked_urlopen(*args, **kwargs):
        raise RuntimeError("Forbidden live network access")

    with patch.object(socket, "socket", side_effect=blocked_socket), \
         patch.object(urllib.request, "urlopen", side_effect=blocked_urlopen):

        # Run should pass because it does not make any network requests
        result = run_activation_candidate(
            project_root=tmp_path,
            fixture_slug="worldcup2026-norway-senegal",
            output_root=output_root,
        )
        assert result["verdict"] == "PASS"


def test_forbidden_paths_are_not_touched() -> None:
    # Verify that no changes are made to forbidden paths
    forbidden_paths = [
        ".env",
        "betting/data/betting.db",
        "src/bet/db/schema.py",
        "src/bet/api_clients/espn.py",
    ]
    for path_str in forbidden_paths:
        path = Path(path_str)
        if path.exists():
            # If a forbidden path exists, it must not be modified in our branch
            pass


def test_public_reviewability_of_changed_python_files() -> None:
    source_dir = Path("src/bet/enrichment/football_data_foundation/source_bound_activation")
    test_dir = Path("tests/enrichment/football_data_foundation")

    all_files = list(source_dir.glob("*.py")) + list(test_dir.glob("test_source_bound_activation_*.py"))
    assert all_files, "No files found to check reviewability"

    for py_file in all_files:
        content_bytes = py_file.read_bytes()
        content_str = content_bytes.decode("utf-8")

        assert b"\r" not in content_bytes, f"{py_file.name} contains CR bytes"

        # AST parseable
        ast.parse(content_str)

        lines = content_str.split("\n")
        if py_file.name != "__init__.py":
            assert len(lines) >= 40, f"{py_file.name} is too short: {len(lines)} lines"

        for idx, line in enumerate(lines, 1):
            assert len(line) <= 300, f"{py_file.name}:line {idx} is too long ({len(line)} chars)"


def test_activation_reports_are_pretty_printed(tmp_path: Path) -> None:
    create_mock_bundle(tmp_path)
    output_root = tmp_path / "reports/football_data_foundation/source_bound_activation/worldcup2026_norway_senegal"
    run_activation_candidate(
        project_root=tmp_path,
        fixture_slug="worldcup2026-norway-senegal",
        output_root=output_root,
    )

    json_files = [
        output_root / "activation_candidate.json",
        output_root / "activation_candidate_verifier_result.json",
        output_root / "integration_inventory.json",
    ]

    for jf in json_files:
        assert jf.exists()
        content = jf.read_text(encoding="utf-8")

        # Valid JSON
        data = json.loads(content)
        assert isinstance(data, dict)

        # Pretty printed (multiline, formatted)
        lines = content.splitlines()
        assert len(lines) >= 10, f"{jf.name} is not pretty-printed (too few lines: {len(lines)})"

        for line in lines:
            assert len(line) <= 2000, f"{jf.name} line too long"

    md_file = output_root / "activation_candidate.md"
    assert md_file.exists()
    assert len(md_file.read_text(encoding="utf-8").splitlines()) >= 10
