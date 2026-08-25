import json
import sqlite3
from pathlib import Path

import pytest

from bet.enrichment.football_data_foundation.source_bound_activation.contracts import ActivationArtifactPaths
from bet.enrichment.football_data_foundation.source_bound_activation.loader import (
    load_source_bundle,
    validate_sqlite_artifact,
)


REQUIRED_PROVIDERS = (
    "api-football",
    "football-data-org",
    "espn-baseline",
    "sportdb",
    "highlightly",
)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_sqlite(path: Path, providers: dict | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute("create table snapshot_metadata (key text, value text)")
        conn.execute("create table provider_ids (source text, provider_id text)")
        conn.execute("create table facts (source text, fact_type text, key text, value text)")
        conn.execute("create table conflicts (kind text, details text)")
        conn.execute("insert into snapshot_metadata values ('fixture_slug', 'worldcup2026-norway-senegal')")
        rows = providers or {p: 1 for p in REQUIRED_PROVIDERS}
        for provider, count in rows.items():
            conn.execute("insert into provider_ids values (?, ?)", (provider, "123"))
            for i in range(count):
                conn.execute("insert into facts values (?, 'summary', ?, '{}')", (provider, f"fact_{i}"))
        conn.commit()
    finally:
        conn.close()


def create_mock_bundle(root: Path, score: dict | None = None, fact_counts: dict | None = None, shadow_status: str | None = None) -> ActivationArtifactPaths:
    fixture_slug = "worldcup2026-norway-senegal"
    shadow_root = root / "reports/football_data_foundation/source_bound_shadow"
    paths = ActivationArtifactPaths.from_shadow_root(shadow_root, fixture_slug)

    counts = fact_counts or {p: 10 for p in REQUIRED_PROVIDERS}
    snapshot = {
        "fixture_slug": fixture_slug,
        "provider_ids": {p: "mock_id" for p in REQUIRED_PROVIDERS},
        "provider_fact_counts": counts,
        "score": score or {"home": 3, "away": 2},
        "conflicts": [],
        "shadow_status": shadow_status or "SHADOW_ENRICHMENT_READY_FOR_MANUAL_REVIEW",
        "production_selectable": False,
        "manual_authorization_required": True,
    }
    verifier = {"verdict": "PASS"}
    public_proof = {"verdict": "PASS"}

    write_json(paths.snapshot_path, snapshot)
    write_json(paths.verifier_path, verifier)
    write_json(paths.provider_fact_counts_path, counts)
    write_json(paths.public_artifact_proof_path, public_proof)
    write_sqlite(paths.sqlite_path, counts)

    return paths


def test_loader_reads_accepted_shadow_artifacts(tmp_path: Path) -> None:
    paths = create_mock_bundle(tmp_path)
    bundle = load_source_bundle(paths, REQUIRED_PROVIDERS)
    assert bundle["snapshot"]["fixture_slug"] == "worldcup2026-norway-senegal"
    assert bundle["verifier"]["verdict"] == "PASS"
    assert bundle["provider_fact_counts"]["api-football"] == 10


def test_loader_validates_sqlite_required_tables_and_provider_rows(tmp_path: Path) -> None:
    paths = create_mock_bundle(tmp_path)
    summary = validate_sqlite_artifact(paths.sqlite_path, REQUIRED_PROVIDERS)
    assert "facts" in summary["tables"]
    assert summary["provider_fact_rows"]["api-football"] == 10


def test_sqlite_validator_fails_missing_provider(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "shadow.sqlite"
    write_sqlite(sqlite_path, providers={"api-football": 1})
    with pytest.raises(ValueError, match="SQLite facts missing providers"):
        validate_sqlite_artifact(sqlite_path, REQUIRED_PROVIDERS)
