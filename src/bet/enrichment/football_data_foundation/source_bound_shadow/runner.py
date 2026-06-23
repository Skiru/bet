import json
from pathlib import Path
from typing import Any, Dict, List

from .contracts import NormalizedFact, NormalizedMatchSnapshot
from .loader import load_provider_envelopes, load_mapping_metadata
from .normalizers import normalize_envelope
from .fuser import fuse_match_snapshot, get_provider_fact_counts, get_normalization_diagnostics
from .writer import write_shadow_json, write_shadow_sqlite
from .verifier import verify_shadow_bundle

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

def run_source_bound_shadow_enrichment(
    project_root: Path,
    output_root: Path,
    fixture_slug: str,
) -> Dict[str, Any]:
    # 1. Define run dirs relative to project root
    run_dirs = [
        project_root / "reports/football_data_foundation/live_response_corpus/run_20260623_100018_fe9167",
        project_root / "reports/football_data_foundation/live_response_corpus/run_20260623_104359_4c5781",
        project_root / "reports/football_data_foundation/live_response_corpus/run_v3_20260623_131229",
    ]
    
    # 2. Load Mapping Candidate Metadata
    mappings = load_mapping_metadata(run_dirs)
    
    # Build provider -> fixture ID lookup
    provider_ids: Dict[str, str] = {}
    for mapping in mappings:
        if mapping.get("fixture_slug") == fixture_slug:
            provider = mapping.get("provider")
            p_id = mapping.get("provider_fixture_id")
            if provider and p_id:
                provider_ids[provider] = p_id
            
            # V3 shape
            sportdb_id = mapping.get("sportdb_event_id")
            if sportdb_id:
                provider_ids["sportdb"] = sportdb_id
            highlightly_id = mapping.get("highlightly_match_id")
            if highlightly_id:
                provider_ids["highlightly"] = highlightly_id

    # 3. Load Provider Envelopes
    envelopes = load_provider_envelopes(run_dirs)
    
    # 4. Normalize Envelopes
    facts: List[NormalizedFact] = []
    for env in envelopes:
        p_id = provider_ids.get(env.provider)
        facts.extend(normalize_envelope(env, provider_match_id=p_id))

    # 5. Fuse snapshot
    snapshot = fuse_match_snapshot(facts)
    
    # 6. Generate diagnostics and counts
    diagnostics = get_normalization_diagnostics(facts)
    fact_counts = get_provider_fact_counts(facts)
    
    # 7. Write outputs
    output_root.mkdir(parents=True, exist_ok=True)
    snapshot_json_path = output_root / "source_bound_shadow_snapshot.json"
    snapshot_md_path = output_root / "source_bound_shadow_snapshot.md"
    sqlite_path = output_root / "source_bound_shadow.sqlite"
    diagnostics_path = output_root / "normalization_diagnostics.json"
    fact_counts_path = output_root / "provider_fact_counts.json"
    readme_path = output_root / "README.md"
    verifier_path = output_root / "source_bound_verifier_result.json"

    # Write snapshot JSON
    write_shadow_json(snapshot, snapshot_json_path)
    
    # Write snapshot MD
    md_report = generate_markdown_report(snapshot)
    snapshot_md_path.write_text(md_report, encoding="utf-8")
    
    # Write diagnostics and fact counts
    diagnostics_path.write_text(json.dumps(diagnostics, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    fact_counts_path.write_text(json.dumps(fact_counts, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    
    # Write isolated SQLite
    write_shadow_sqlite(snapshot, sqlite_path, diagnostics)
    
    # Write README.md
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
- `source_bound_verifier_result.json`: Pass B verifier output.
"""
    readme_path.write_text(readme_content, encoding="utf-8")

    # 8. Run Verifier
    verifier_result = verify_shadow_bundle(
        snapshot_json_path,
        sqlite_path,
        diagnostics_path,
        fact_counts_path
    )
    
    # Write verifier result
    verifier_path.write_text(json.dumps(verifier_result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    
    # 9. Return summary dict
    return {
        "verdict": verifier_result["verdict"],
        "shadow_status": verifier_result.get("shadow_status"),
        "snapshot_path": str(snapshot_json_path),
        "sqlite_path": str(sqlite_path),
        "provider_ids": verifier_result["provider_ids"],
        "provider_fact_counts": verifier_result["provider_fact_counts"],
        "score": verifier_result["score_consensus"],
        "conflicts": verifier_result["conflicts"],
        "verifier_path": str(verifier_path),
    }
