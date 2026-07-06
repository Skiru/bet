# Canonical Pipeline Integration Review

This review analyzes the integration of the S2 Tipster Scraper v2/Certified Shadow into the canonical sports betting pipeline.

## 1. What does manifest S2 point to after branch changes?
In `config/pipeline_manifest.json`, the `S2` step continues to point to the legacy wrapper `scripts/pipeline_steps/s2_tipsters.py` for its `wrapper` and `canonical_script` fields:
- **`wrapper`**: `"scripts/pipeline_steps/s2_tipsters.py"`
- **`canonical_script`**: `"scripts/pipeline_steps/s2_tipsters.py"`

## 2. Is `scripts/pipeline_steps/s2_tipsters.py` still legacy-only?
Yes. The script `scripts/pipeline_steps/s2_tipsters.py` remains legacy-only. It only runs `tipster_aggregator.py` and `tipster_xref.py`, with absolutely no references or support for v2 extractors, handoff mechanisms, or compliance-oriented certified shadow sources (like ZawodTyper).

## 3. Is `s2_tipsters_v2_live_dry_run.py` part of canonical path or sidecar path?
It is part of the **sidecar path**. It is not listed in `config/pipeline_manifest.json`, meaning the main canonical orchestrator flow does not trigger it as a default required pipeline step.

## 4. If sidecar, where is it documented and how does orchestrator call it?
It is documented in `docs/pipeline/Tipster Orchestrator Runbook.md` and `docs/pipeline/ZawodTyper Agent Handoff Contract.md`.
The orchestrator triggers it as a shadow sidecar script by calling:
```fish
.venv-tipster-v2/bin/python scripts/pipeline_steps/s2_tipsters_v2_live_dry_run.py \
  --date YYYY-MM-DD \
  --terms-reviewed-json docs/pipeline/tipster_terms_review.local.json \
  ...
```

## 5. Does `_runner.py` permit live shadow with required ack and sandbox paths?
Yes. `_runner.py` explicitly supports `RuntimeMode.LIVE_SHADOW`. It blocks execution and returns exit code 5 if `allow_live_network` is false or if the `BET_PIPELINE_LIVE_ACK` environment variable is not set to `"I_UNDERSTAND_LIVE_PROVIDER_CALLS"`. Additionally, it resolves sandboxed paths (e.g., `BET_PIPELINE_RUN_ROOT`, `BET_PIPELINE_DATA_DIR`, `BET_PIPELINE_ARTIFACT_DIR`) to guarantee file-isolation.

## 6. Does S3 consume tipster handoff directly, indirectly, or not yet?
Not yet directly. S3 (`s3_stats.py` / `deep_stats_report.py`) consumes the shortlisted candidates/events (`*_s2_shortlist.json` or `*shortlist*.json`) generated in the core DATA phase steps. The tipster handoff artifact serves as contextual sentiment and qualitative evidence, which is side-loaded rather than processed as primary model input.

## 7. Does S4 consume tipster handoff directly, indirectly, or not yet?
Not yet directly. S4 (`s4_valuator.py` / `odds_evaluator.py`) consumes stats and probabilities from S3. Any tipster data consumed at S4 is treated as a manual sanity check layer for sentiment verification and qualitative reasoning, rather than direct valuation or Kelly-sizing mathematical inputs.

## 8. Is production-grade claim TRUE, PARTIAL, or FALSE?
**PARTIAL**. While the v2 crawler, compliance rate limiter, public XHR NP_ajax.php transport, and handoff structures are fully production-grade, audited, and verified, their deployment within the orchestrator is implemented as a shadow sidecar side-by-side with the legacy S2 pipeline steps, rather than a full direct replacement in the canonical `pipeline_manifest.json`.

---
**Reviewer**: Kilo (Autonomous Integration Agent)
**Date**: 2026-07-06
**Status**: VERIFIED
