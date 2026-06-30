# Artifact Hygiene Final Gate Precheck Review

TASK_ID=ARTIFACT_HYGIENE_AND_FINAL_FUNCTIONAL_GATE_RETRY_A

## Precheck

Branch: `feat/live-session-discovery-root-cause-repair-b`
HEAD: `a745c3b447d099c77cd6f62c25305d42bdc9306d`
Origin: `a745c3b447d099c77cd6f62c25305d42bdc9306d`

Exact git status before action:

```text
 M .kilo/artifacts/analyzability_prefilter_report.json
?? .kilo/artifacts/full_analytical_package_quality_review.md
?? .kilo/artifacts/full_analytical_session_input_selection.md
?? .kilo/artifacts/full_analytical_session_lane_trace.md
?? .kilo/artifacts/full_analytical_session_smoke_report.md
?? .kilo/artifacts/full_analytical_session_status_safety.md
?? .kilo/bundles/
?? reports/agent-config/artifact-writer-audit/audit-2026-06-29.jsonl
?? reports/pipeline_runs/2026-06-28/
?? reports/pipeline_runs/2026-06-29/
?? reports/pipeline_runs/pipeline_runs_backup/
```

Exact diff summary:

```text
.kilo/artifacts/analyzability_prefilter_report.json | 27 ++++++++++++++++++----
1 file changed, 22 insertions(+), 5 deletions(-)
```

Dirty artifact classification: `TRACKED_BASELINE_ARTIFACT_OVERWRITTEN_BY_RUNTIME`

## Findings

- The tracked file at `.kilo/artifacts/analyzability_prefilter_report.json` is a baseline/test fixture committed at `HEAD`.
- The working-copy diff replaced the baseline candidate with runtime-style candidate content, including `cand-safe` and `cand-partial` rows and `REVIEW_ONLY_PARTIAL_DATA` status.
- `src/bet/pipeline/analytical_candidate_bridge.py` hard-coded the runtime report write target to the tracked fixture path.
- No raw secret values from `config/api_keys.json` were detected in `.kilo/artifacts`, `reports`, or `/tmp` during the bounded scan. `SECRET_ARTIFACT_DIFF_VERDICT=PASS`.

## Baseline Or Runtime

- File role: baseline/test artifact.
- Why it changed: runtime bridge execution wrote live analyzability output into the tracked fixture path.
- Secrets in diff: none detected.

## Safe Resolution

- Fix runtime output hygiene so analyzability reports write to runtime-scoped artifact directories, preferring `BET_PIPELINE_ARTIFACT_DIR` and otherwise deriving a sibling `artifacts/` directory from the source run path.
- Restore `.kilo/artifacts/analyzability_prefilter_report.json` with a targeted file-only restore from `HEAD`.
- Keep the tracked fixture stable unless a future contract/test intentionally updates it.
