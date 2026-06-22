from __future__ import annotations

import re
from pathlib import Path

FIXTURES_DIR = (
    Path(__file__).parent.parent.parent
    / "fixtures"
    / "enrichment"
    / "football_data_foundation"
    / "pass2"
)
SRC_DIR = (
    Path(__file__).parent.parent.parent.parent
    / "src"
    / "bet"
    / "enrichment"
    / "football_data_foundation"
)


def test_guardrails_fixtures_no_secrets() -> None:
    secret_pat = re.compile(
        r"(?:sk-[a-zA-Z0-9]{32,})|(?:AIzaSy[a-zA-Z0-9-_]{35})",
        re.IGNORECASE,
    )
    for path in FIXTURES_DIR.glob("**/*"):
        if path.is_file() and path.suffix in {".json", ".txt", ".csv"}:
            content = path.read_text(encoding="utf-8")
            assert not secret_pat.search(content), f"Secret found in fixture {path}"


def test_guardrails_no_raw_payloads_in_claims() -> None:
    # Check that our implemented pass2 source files don't define forbidden raw keys in claims
    forbidden_keys_pattern = re.compile(
        r'"(?:raw|payload|raw_payload|response_body|html|json_raw|raw_json|raw_html)"\s*:'
    )
    for path in SRC_DIR.glob("**/*.py"):
        if any(name in path.name for name in ("pass2_parsers", "pass2_replay", "current_live")):
            content = path.read_text(encoding="utf-8")
            assert not forbidden_keys_pattern.search(content), f"Forbidden raw key found in {path}"


def test_guardrails_no_prototype_in_versions() -> None:
    for path in SRC_DIR.glob("**/*.py"):
        if any(name in path.name for name in ("pass2_parsers", "pass2_replay", "current_live")):
            content = path.read_text(encoding="utf-8")
            assert "prototype-v2" not in content, f"Found 'prototype-v2' version string in {path}"
