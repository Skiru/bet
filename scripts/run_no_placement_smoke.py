"""Executes a full no-placement analytical smoke check over the sandbox artifacts."""
from __future__ import annotations

import json
from pathlib import Path
from bet.pipeline.analytical_candidate_bridge import build_analytical_candidate_handoff, write_analytical_candidate_handoff

def main() -> None:
    # Resolve sandbox paths
    sandbox_dir = Path("/private/tmp/premerge_probability_release_smoke_a")
    val_path = sandbox_dir / "data" / "2026-06-29_s4_valuation_candidates.json"
    s3_path = sandbox_dir / "data" / "2026-06-29_s3_deep_stats.json"
    shortlist_path = sandbox_dir / "data" / "2026-06-29_s2_shortlist.json"
    
    if not val_path.exists():
        print(f"Error: Sandbox valuation file {val_path} does not exist.")
        return
        
    val_payload = json.loads(val_path.read_text(encoding="utf-8"))
    s3_payload = json.loads(s3_path.read_text(encoding="utf-8")) if s3_path.exists() else None
    shortlist_payload = json.loads(shortlist_path.read_text(encoding="utf-8")) if shortlist_path.exists() else None
    
    print(f"Loaded sandbox candidates: {len(val_payload.get('candidates', []))}")
    
    # Compute handoff
    handoff = build_analytical_candidate_handoff(
        val_payload,
        s3_payload=s3_payload,
        shortlist_payload=shortlist_payload,
        source_artifact_path=str(val_path)
    )
    
    # Ensure correct output directory
    output_dir = Path("/Users/mkoziol/projects/bet/reports/pipeline_runs")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    output_path = output_dir / "analytical_candidate_handoff_smoke_replay.json"
    write_analytical_candidate_handoff(output_path, handoff)
    
    print("\n--- Smoke Run Handoff Summary ---")
    print(f"Handoff Output Path: {output_path}")
    print(f"ANALYZABLE_COUNT: {handoff['counts']['analytical_ready']}")
    print(f"Package Type: {handoff['package_type']}")
    print(f"Gap Reasons: {json.dumps(handoff['gap_reasons'])}")
    print(f"Priced Candidates count: {handoff['counts']['priced_candidates']}")
    
if __name__ == "__main__":
    main()
