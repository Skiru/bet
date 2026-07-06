# Loop 3 — Pipeline & Orchestrator Review

## 1. Safe Defaults
- **Verification:** By default, running `s2_tipsters_v2_live_dry_run.py` resolves active sources to `("forebet", "predictz")`. 
- **Result:** SAFE. Legacies and shadow-live candidates (like ZawodTyper) are completely excluded from default core dry-runs, preventing unauthorized external traffic during routine execution.

## 2. Certified Shadow Opt-In
- **Verification:** Passing `--include-certified-shadow` expands the source pool to automatically include sources defined under `CERTIFIED_SHADOW_SOURCE_IDS = ("zawodtyper",)`.
- **Result:** PASS. Opt-in is explicit, simple, and isolated.

## 3. Explicit S3/S4 Handoff
- **Verification:** Passing `--handoff-out` writes a completely separate handoff file in `tipster_evidence_handoff_v1` format.
- **Result:** PASS. Downstream steps (S3/S4) have a clear and formal evidence schema to read without needing to parse complex raw crawler JSON payloads.

## 4. Agent Use Decisions readability
- **Verification:** The handoff contains an explicit `"agent_use_decisions"` list for every event group, conveying precise directives like `["USE_AS_CONTEXT"]` or `["NEEDS_MANUAL_REVIEW"]`.
- **Result:** PASS. Downstream agents can directly read these decisions to alter execution behavior or flag issues.

## 5. Other Sources Rescue Paths
- **Verification:** No sources are discarded or marked as "rejected" broad-brush. Instead, they are structured into a full Rescue Matrix with clear priority, allowed probe types, and next development passes.
- **Result:** PASS. All sources are treated with professional code diligence.
