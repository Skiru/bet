"""Executes a full no-placement analytical smoke check over the sandbox artifacts."""
from __future__ import annotations

import json
import os
from pathlib import Path
from bet.pipeline.analytical_candidate_bridge import build_analytical_candidate_handoff, write_analytical_candidate_handoff


def _quote_ready_count(candidates: list[dict[str, object]]) -> int:
    return sum(1 for candidate in candidates if candidate.get("ready_for_manual_operator_quote_review") is True)


def _all_handoff_candidates(handoff: dict[str, object]) -> list[dict[str, object]]:
    keys = (
        "analytical_ready",
        "blocked_probability_missing",
        "blocked_stats_missing",
        "blocked_identity_missing",
        "review_only_partial_data",
        "research_gap_minimal_hydration",
    )
    combined: list[dict[str, object]] = []
    for key in keys:
        for candidate in handoff.get(key) or []:
            if isinstance(candidate, dict):
                combined.append(candidate)
    return combined


def _resolve_output_path(source_artifact_path: Path) -> Path:
    run_root = os.environ.get("BET_PIPELINE_RUN_ROOT", "").strip()
    if run_root:
        output_root = Path(run_root) / "data"
    else:
        betting_day = source_artifact_path.name[:10] if len(source_artifact_path.name) >= 10 else "unknown-day"
        output_root = Path("/Users/mkoziol/projects/bet/reports/pipeline_runs") / betting_day / "no-placement-smoke"
    output_root.mkdir(parents=True, exist_ok=True)
    return output_root / f"{source_artifact_path.stem}_analytical_candidate_handoff_smoke_replay.json"

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
    
    output_path = _resolve_output_path(val_path)
    write_analytical_candidate_handoff(output_path, handoff)
    analytical_ready = handoff.get("analytical_ready") or []
    all_candidates = _all_handoff_candidates(handoff)
    
    print("\n--- Smoke Run Handoff Summary ---")
    print(f"Handoff Output Path: {output_path}")
    print(f"HYDRATED_COUNT: {sum(1 for candidate in all_candidates if candidate.get('hydration_status') == 'HYDRATED')}")
    print(f"PARTIAL_HYDRATION_COUNT: {sum(1 for candidate in all_candidates if candidate.get('hydration_status') == 'PARTIAL_HYDRATION')}")
    print(f"MINIMAL_HYDRATION_COUNT: {sum(1 for candidate in all_candidates if candidate.get('hydration_status') in {'MINIMAL_HYDRATION', 'DATA_UNAVAILABLE'})}")
    print(f"ANALYZABLE_COUNT: {handoff['counts']['analytical_ready']}")
    print(f"REVIEW_ONLY_PARTIAL_COUNT: {handoff['counts'].get('review_only_partial_data', 0)}")
    print(f"RESEARCH_GAP_MINIMAL_COUNT: {handoff['counts'].get('research_gap_minimal_hydration', 0)}")
    print(f"ANALYTICAL_SUGGESTION_COUNT: {len(analytical_ready)}")
    print(f"MANUAL_OPERATOR_QUOTE_REVIEW_COUNT: {_quote_ready_count(analytical_ready)}")
    print(f"PACKAGE_TYPE: {handoff['package_type']}")
    print(f"READY_FOR_MANUAL_OPERATOR_QUOTE_REVIEW: {_quote_ready_count(analytical_ready) > 0}")
    print(f"Gap Reasons: {json.dumps(handoff['gap_reasons'])}")
    print(f"Priced Candidates count: {handoff['counts']['priced_candidates']}")
    
if __name__ == "__main__":
    main()
