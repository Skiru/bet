"""Tests for verifying documentation matches authoritative manifest and control plane contracts."""

from __future__ import annotations

import json
import re
from pathlib import Path


def test_documentation_truth():
    """Mechanically verify README.md and ARCHITECTURE.md match authoritative contracts."""
    root = Path(__file__).resolve().parents[1]

    # 1. Load Authoritative Manifest
    manifest_path = root / "config/pipeline_manifest.json"
    assert manifest_path.exists(), "Manifest config/pipeline_manifest.json must exist"
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    steps = manifest.get("steps", [])
    step_ids = [step["id"] for step in steps]

    # 2. Load Documents
    readme_path = root / "README.md"
    assert readme_path.exists(), "README.md must exist"
    readme_content = readme_path.read_text(encoding="utf-8")

    arch_path = root / "ARCHITECTURE.md"
    assert arch_path.exists(), "ARCHITECTURE.md must exist"
    arch_content = arch_path.read_text(encoding="utf-8")

    mismatches = []

    # Check S0-S10 step names & presence
    for sid in step_ids:
        if sid not in readme_content:
            mismatches.append(f"README.md missing step ID reference: {sid}")
        if sid not in arch_content:
            mismatches.append(f"ARCHITECTURE.md missing step ID reference: {sid}")

    # Verify S1e, S7b, S8 exact descriptions in README.md
    s1e_pattern = r"s1e.*canonical materialized event-universe ledger"
    if not re.search(s1e_pattern, readme_content, re.IGNORECASE):
        mismatches.append(
            "README.md must describe S1e as canonical materialized event-universe ledger"
        )

    s7b_pattern = r"s7b.*manual superbet market/line mapping"
    if not re.search(s7b_pattern, readme_content, re.IGNORECASE):
        mismatches.append(
            "README.md must describe S7b as manual Superbet market/line mapping"
        )

    s8_pattern = r"s8.*manual superbet quote pack"
    if not re.search(s8_pattern, readme_content, re.IGNORECASE):
        mismatches.append("README.md must describe S8 as manual Superbet quote pack")

    # One canonical runner identified
    runner_pattern = r"scripts/pipeline_steps/run_daily_pipeline\.py"
    if not re.search(runner_pattern, readme_content, re.IGNORECASE):
        mismatches.append(
            "README.md must identify scripts/pipeline_steps/run_daily_pipeline.py as the canonical runner"
        )

    if not re.search(runner_pattern, arch_content, re.IGNORECASE):
        mismatches.append(
            "ARCHITECTURE.md must identify scripts/pipeline_steps/run_daily_pipeline.py as the canonical runner"
        )

    # No generic sN.py operational instruction in README
    if "sN.py" in readme_content:
        mismatches.append(
            "README.md contains generic sN.py instruction, which is forbidden"
        )

    # No suggestion of automatic operator interaction
    for forbidden_word in [
        "automatic placement",
        "automated placement",
        "automate bookmaker",
    ]:
        if (
            forbidden_word in readme_content.lower()
            and "no" not in readme_content.lower().split(forbidden_word)[0]
        ):
            mismatches.append(
                f"README.md contains forbidden automation suggestion: '{forbidden_word}'"
            )

    # ARCHITECTURE.md must NOT contain obsolete structures or future targets
    for legacy in [
        "target structure",
        "target layout",
        "betclic.py",
        "namespace fragmentation",
        "future migration plans",
    ]:
        if legacy in arch_content.lower():
            mismatches.append(
                f"ARCHITECTURE.md contains obsolete or future-target reference: '{legacy}'"
            )

    # ARCHITECTURE.md must describe required domains
    required_sections = [
        "current package layering",
        "canonical runner and manifest",
        "artifact, lock and resume infrastructure",
        "db schema",
        "historical migration versus active schema distinction",
        "provider registry",
        "seven-agent and four-skill control plane",
        "boundaries",
        "generated-data policy",
        "run lifecycle",
    ]
    for section in required_sections:
        if section not in arch_content.lower():
            mismatches.append(f"ARCHITECTURE.md missing required section: '{section}'")

    # Assert no mismatches found
    assert mismatches == [], f"Documentation truth mismatches found: {mismatches}"
