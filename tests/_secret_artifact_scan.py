from __future__ import annotations

import json
from pathlib import Path


_PLACEHOLDER_TOKENS = ("your_key", "placeholder", "dummy", "test_key", "testkey", "example")
_SCAN_PATTERNS = (
    "*.md",
    "*.json",
    "*.jsonl",
    "*.log",
    "*hydration*",
    "*provider*",
    "*smoke*",
    "*stdout*",
    "*stderr*",
    "s4.txt",
    "s5.txt",
    "s8.txt",
)


def load_local_secret_values(keys_path: Path) -> list[str]:
    payload = json.loads(keys_path.read_text(encoding="utf-8"))
    secret_values: list[str] = []

    def _collect(value: object) -> None:
        if isinstance(value, dict):
            for nested in value.values():
                _collect(nested)
            return
        if isinstance(value, list):
            for nested in value:
                _collect(nested)
            return
        if not isinstance(value, str):
            return
        normalized = value.strip()
        if len(normalized) < 8:
            return
        lowered = normalized.lower()
        if any(token in lowered for token in _PLACEHOLDER_TOKENS):
            return
        secret_values.append(normalized)

    _collect(payload)
    return sorted(set(secret_values))


def iter_real_artifact_scan_paths(repo_root: Path) -> list[Path]:
    roots = [
        repo_root / ".kilo" / "artifacts",
        repo_root / "reports",
        Path("/tmp"),
    ]
    found: dict[str, Path] = {}
    for root in roots:
        if not root.exists():
            continue
        for pattern in _SCAN_PATTERNS:
            for candidate in root.rglob(pattern):
                if not candidate.is_file():
                    continue
                candidate_str = str(candidate)
                if root == Path("/tmp"):
                    if "/pytest-" in candidate_str or "/pytest-of-" in candidate_str:
                        continue
                    if candidate.name == "api_keys.json":
                        continue
                found.setdefault(str(candidate.resolve()), candidate)
    return sorted(found.values(), key=lambda path: str(path))


def assert_no_raw_secret_values_in_real_artifacts(repo_root: Path, secret_values: list[str]) -> None:
    for artifact_path in iter_real_artifact_scan_paths(repo_root):
        content = artifact_path.read_text(encoding="utf-8", errors="ignore")
        for secret_value in secret_values:
            if secret_value in content:
                raise AssertionError(f"Raw secret leaked in artifact/log file: {artifact_path}")
