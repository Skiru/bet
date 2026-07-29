import json
import socket
import contextlib
import tempfile
import urllib.request
try:
    import requests.sessions
except ImportError:
    pass
from pathlib import Path
from typing import Any, Dict, Generator, List

from .contracts import NormalizedFact, NormalizedMatchSnapshot, NetworkProbeResult
from .loader import load_provider_envelopes, load_mapping_metadata
from .normalizers import normalize_envelope
from .fuser import fuse_match_snapshot, get_provider_fact_counts, get_normalization_diagnostics
from .writer import write_shadow_json, write_shadow_sqlite
from .verifier import verify_shadow_bundle

@contextlib.contextmanager
def socket_block_context() -> Generator[dict, None, None]:
    attempts = {"count": 0}
    original_socket = socket.socket
    original_create_connection = socket.create_connection

    def blocked_socket(*args, **kwargs):
        attempts["count"] += 1
        raise RuntimeError("Live network access is forbidden in source-bound shadow!")

    def blocked_create_connection(*args, **kwargs):
        attempts["count"] += 1
        raise RuntimeError("Live network access is forbidden in source-bound shadow!")

    original_urlopen = None
    try:
        original_urlopen = urllib.request.urlopen
        def blocked_urlopen(*args, **kwargs):
            attempts["count"] += 1
            raise RuntimeError("Live network access is forbidden in source-bound shadow!")
        urllib.request.urlopen = blocked_urlopen
    except AttributeError:
        pass

    original_request = None
    try:
        original_request = requests.sessions.Session.request
        def blocked_request(*args, **kwargs):
            attempts["count"] += 1
            raise RuntimeError("Live network access is forbidden in source-bound shadow!")
        requests.sessions.Session.request = blocked_request
    except (NameError, AttributeError):
        pass

    socket.socket = blocked_socket
    socket.create_connection = blocked_create_connection

    try:
        yield attempts
    finally:
        socket.socket = original_socket
        socket.create_connection = original_create_connection
        if original_urlopen is not None:
            urllib.request.urlopen = original_urlopen
        if original_request is not None:
            requests.sessions.Session.request = original_request

def generate_markdown_report(snapshot: NormalizedMatchSnapshot) -> str:
    lines = []
    lines.append(f"# Source-Bound Shadow Snapshot Report")
    lines.append(f"Fixture: {snapshot.fixture_slug}")
    lines.append(f"Status: {snapshot.status}")
    lines.append(f"Competition: {snapshot.competition}")
    lines.append(f"Kickoff (UTC): {snapshot.kickoff_utc}")
    lines.append(f"Venue: {snapshot.venue}")
    lines.append(f"Referee: {snapshot.referee}")
    lines.append(f"Teams: {snapshot.teams.get('home')} vs {snapshot.teams.get('away')}")
    lines.append(f"Score: {snapshot.teams.get('home')} {snapshot.score.get('home')} - {snapshot.score.get('away')} {snapshot.teams.get('away')}")
    lines.append("")
    lines.append("## Provider Mappings")
    for provider, p_id in sorted(snapshot.provider_ids.items()):
        lines.append(f"- {provider}: {p_id}")
    lines.append("")
    lines.append("## Verification Invariants")
    lines.append(f"- Production Selectable: {snapshot.production_selectable}")
    lines.append(f"- Manual Authorization Required: {snapshot.manual_authorization_required}")
    lines.append(f"- Shadow Status: {snapshot.shadow_status}")
    lines.append("")
    lines.append(f"## Facts Included ({len(snapshot.facts)})")
    for fact in snapshot.facts[:20]:
        lines.append(f"- [{fact.source}] {fact.fact_type}.{fact.key} = {fact.value} (SHA256: {fact.body_sha256[:8]}...)")
    if len(snapshot.facts) > 20:
        lines.append(f"- ... and {len(snapshot.facts) - 20} more facts")
    lines.append("")
    lines.append("## Active Conflicts")
    if snapshot.conflicts:
        for conflict in snapshot.conflicts:
            lines.append(f"- {conflict}")
    else:
        lines.append("No active conflicts detected.")
    return "\n".join(lines) + "\n"

def _run_enrichment_flow(
    project_root: Path,
    target_output_root: Path,
    fixture_slug: str,
) -> Dict[str, Any]:
    run_dirs = [
        project_root / "reports/football_data_foundation/live_response_corpus/run_20260623_100018_fe9167",
        project_root / "reports/football_data_foundation/live_response_corpus/run_20260623_104359_4c5781",
        project_root / "reports/football_data_foundation/live_response_corpus/run_v3_20260623_131229",
    ]

    mappings = load_mapping_metadata(run_dirs)

    provider_ids: Dict[str, str] = {}
    for mapping in mappings:
        if mapping.get("fixture_slug") == fixture_slug:
            provider = mapping.get("provider")
            p_id = mapping.get("provider_fixture_id")
            if provider and p_id:
                provider_ids[provider] = p_id

            sportdb_id = mapping.get("sportdb_event_id")
            if sportdb_id:
                provider_ids["sportdb"] = sportdb_id
            highlightly_id = mapping.get("highlightly_match_id")
            if highlightly_id:
                provider_ids["highlightly"] = highlightly_id

    envelopes = load_provider_envelopes(run_dirs)

    facts: List[NormalizedFact] = []
    for env in envelopes:
        p_id = provider_ids.get(env.provider)
        facts.extend(normalize_envelope(env, provider_match_id=p_id))

    snapshot = fuse_match_snapshot(facts, fixture_slug)

    diagnostics = get_normalization_diagnostics(facts)
    fact_counts = get_provider_fact_counts(facts)

    target_output_root.mkdir(parents=True, exist_ok=True)
    snapshot_json_path = target_output_root / "source_bound_shadow_snapshot.json"
    snapshot_md_path = target_output_root / "source_bound_shadow_snapshot.md"
    sqlite_path = target_output_root / "source_bound_shadow.sqlite"
    diagnostics_path = target_output_root / "normalization_diagnostics.json"
    fact_counts_path = target_output_root / "provider_fact_counts.json"
    readme_path = target_output_root / "README.md"

    write_shadow_json(snapshot, snapshot_json_path)

    md_report = generate_markdown_report(snapshot)
    snapshot_md_path.write_text(md_report, encoding="utf-8")

    diagnostics_path.write_text(json.dumps(diagnostics, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    extended_fact_counts = dict(fact_counts)
    extended_fact_counts["meta_as_of"] = "2026-06-23"
    extended_fact_counts["meta_fixture_slug"] = fixture_slug
    extended_fact_counts["meta_phase"] = "FOOTBALL_ENRICHMENT_B6_RAW_LINE_TRUTH_REPAIR"
    fact_counts_path.write_text(json.dumps(extended_fact_counts, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    write_shadow_sqlite(snapshot, sqlite_path, diagnostics)

    readme_content = f"""# Source-Bound Shadow Replay Artifacts

This directory contains the production-grade source-bound shadow enrichment replay for:
`TARGET_FIXTURE_SLUG={fixture_slug}`

Generated on: 2026-06-23

Included files:
- `source_bound_shadow_snapshot.json`: Unified deterministic snapshot.
- `source_bound_shadow_snapshot.md`: Markdown report of snapshot.
- `source_bound_shadow.sqlite`: Isolated report SQLite DB.
- `normalization_diagnostics.json`: Diagnostics of missing optional fields.
- `provider_fact_counts.json`: Detailed fact counts per provider.
"""
    readme_path.write_text(readme_content, encoding="utf-8")

    return {
        "snapshot_json_path": snapshot_json_path,
        "sqlite_path": sqlite_path,
        "diagnostics_path": diagnostics_path,
        "fact_counts_path": fact_counts_path,
    }

def run_source_bound_shadow_enrichment(
    project_root: Path,
    output_root: Path,
    fixture_slug: str,
) -> Dict[str, Any]:
    # 1. Run normal source-bound shadow enrichment to final output directory.
    real_paths = _run_enrichment_flow(project_root, output_root, fixture_slug)

    # 2. Run a second network-blocked probe into a temporary directory, not reports.
    # The temporary probe output is NOT committed (it gets automatically cleaned up by tempfile).
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_output_root = Path(tmp_dir)
        with socket_block_context() as attempts:
            try:
                _run_enrichment_flow(project_root, tmp_output_root, fixture_slug)
                execution_success = True
            except Exception:
                execution_success = False

        probe_result = NetworkProbeResult(
            runner_executed_under_socket_block=execution_success,
            network_attempts_detected=attempts["count"],
            socket_blocking_mode="monkeypatch",
            output_root=str(tmp_output_root),
        )

    # 3. Pass NetworkProbeResult into verifier on the REAL outputs
    verifier_result = verify_shadow_bundle(
        real_paths["snapshot_json_path"],
        real_paths["sqlite_path"],
        real_paths["diagnostics_path"],
        real_paths["fact_counts_path"],
        probe_result,
        expected_fixture_slug=fixture_slug,
    )

    # Write verifier result to final output_root
    verifier_path = output_root / "source_bound_verifier_result.json"
    verifier_path.write_text(json.dumps(verifier_result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    # 4. Return results dictionary matching required parameters
    return {
        "verdict": verifier_result["verdict"],
        "shadow_status": verifier_result.get("shadow_status"),
        "snapshot_path": str(real_paths["snapshot_json_path"]),
        "sqlite_path": str(real_paths["sqlite_path"]),
        "provider_ids": verifier_result["provider_ids"],
        "provider_fact_counts": verifier_result["provider_fact_counts"],
        "score": verifier_result["score_consensus"],
        "conflicts": verifier_result["conflicts"],
        "verifier_path": str(verifier_path),
        "network_probe_check": verifier_result.get("network_probe_check"),
        "fixture_slug_source_check": verifier_result.get("fixture_slug_source_check"),
        "sqlite_table_check": verifier_result.get("sqlite_table_check"),
        "sqlite_row_count_check": verifier_result.get("sqlite_row_count_check"),
        "committed_test_artifact_check": verifier_result.get("committed_test_artifact_check"),
        "public_raw_reviewability_check": verifier_result.get("public_raw_reviewability_check"),
        "public_raw_report_format_check": verifier_result.get("public_raw_report_format_check"),
        "committed_blob_sqlite_check": verifier_result.get("committed_blob_sqlite_check"),
        "public_raw_sqlite_check": verifier_result.get("public_raw_sqlite_check"),
    }
