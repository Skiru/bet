import json
import sqlite3
from pathlib import Path
from typing import Any

from .contracts import ActivationArtifactPaths


REQUIRED_SQLITE_TABLES = {
    "snapshot_metadata",
    "provider_ids",
    "facts",
    "conflicts",
}


FORBIDDEN_KEYS = {
    "raw_payload",
    "raw_headers",
    "authorization",
    "x-api-key",
    "x-rapidapi-key",
    "cookie",
    "set-cookie",
    "token",
    "api_key",
}


FORBIDDEN_TEXT = (
    "betting decision",
    "recommendation",
    "stake",
    "edge",
    "raw_payload",
    "raw_headers",
    "x-api-key",
    "x-rapidapi-key",
    "set-cookie",
)


def load_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ValueError(f"Required JSON file is missing: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Required JSON object expected: {path}")
    return value


def load_provider_fact_counts(path: Path) -> dict[str, int]:
    data = load_json_object(path)
    counts: dict[str, int] = {}
    for key, value in data.items():
        if key.startswith("meta_"):
            continue
        if isinstance(value, int):
            counts[key] = value
    return counts


def walk_json(value: Any, path: str = "$") -> list[tuple[str, Any]]:
    result: list[tuple[str, Any]] = [(path, value)]
    if isinstance(value, dict):
        for key, child in value.items():
            result.extend(walk_json(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            result.extend(walk_json(child, f"{path}[{index}]"))
    return result


def assert_no_forbidden_payload(value: Any) -> None:
    failures: list[str] = []
    for path, item in walk_json(value):
        if isinstance(item, dict):
            for key in item:
                if key.lower() in FORBIDDEN_KEYS:
                    failures.append(f"forbidden_key:{path}.{key}")
        if isinstance(item, str):
            lower = item.lower()
            for token in FORBIDDEN_TEXT:
                if token in lower:
                    failures.append(f"forbidden_text:{path}:{token}")
    if failures:
        raise ValueError("Forbidden payload markers found: " + ", ".join(failures[:10]))


def validate_sqlite_artifact(path: Path, required_providers: tuple[str, ...]) -> dict[str, Any]:
    if not path.exists():
        raise ValueError(f"SQLite artifact missing: {path}")
    blob = path.read_bytes()
    if len(blob) <= 4096:
        raise ValueError(f"SQLite artifact is too small: {len(blob)} bytes")
    if not blob.startswith(b"SQLite format 3\x00"):
        raise ValueError("SQLite artifact has invalid header")

    conn = sqlite3.connect(path)
    try:
        tables = {row[0] for row in conn.execute("select name from sqlite_master where type='table'")}
        missing_tables = REQUIRED_SQLITE_TABLES - tables
        if missing_tables:
            raise ValueError("SQLite missing tables: " + ", ".join(sorted(missing_tables)))
        provider_rows = {
            row[0]: int(row[1])
            for row in conn.execute("select source, count(*) from facts group by source")
        }
        missing_providers = [provider for provider in required_providers if provider_rows.get(provider, 0) <= 0]
        if missing_providers:
            raise ValueError("SQLite facts missing providers: " + ", ".join(missing_providers))
        return {
            "path": str(path),
            "size_bytes": len(blob),
            "tables": sorted(tables),
            "provider_fact_rows": dict(sorted(provider_rows.items())),
        }
    finally:
        conn.close()


def load_source_bundle(paths: ActivationArtifactPaths, required_providers: tuple[str, ...]) -> dict[str, Any]:
    snapshot = load_json_object(paths.snapshot_path)
    verifier = load_json_object(paths.verifier_path)
    fact_counts = load_provider_fact_counts(paths.provider_fact_counts_path)
    public_proof = load_json_object(paths.public_artifact_proof_path)
    sqlite_summary = validate_sqlite_artifact(paths.sqlite_path, required_providers)
    assert_no_forbidden_payload(snapshot)
    assert_no_forbidden_payload(verifier)
    assert_no_forbidden_payload(public_proof)
    return {
        "snapshot": snapshot,
        "verifier": verifier,
        "provider_fact_counts": fact_counts,
        "public_proof": public_proof,
        "sqlite_summary": sqlite_summary,
    }
