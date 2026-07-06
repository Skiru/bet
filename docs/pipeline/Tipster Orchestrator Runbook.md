# Tipster Orchestrator Runbook

## 1. Overview
The S2 Tipster Scraper v2 runs under a strict, compliance-first orchestrator setup. By default, only safe sources that allow live fetching via robots.txt are processed. Highly dynamic or Polish-specific sentiment sources (like ZawodTyper) are certified as **Certified Shadow Sources** and require an explicit command-line opt-in.

## 2. Command Reference

### Default Production Run (Safe/Core Only)
```fish
.venv-tipster-v2/bin/python scripts/pipeline_steps/s2_tipsters_v2_live_dry_run.py \
  --date 2026-07-06 \
  --terms-reviewed-json docs/pipeline/tipster_terms_review.local.json \
  --max-pages-per-source 1 \
  --out betting/data/2026-07-06_tipster_consensus.json \
  --sqlite-db betting/data/tipsters.sqlite \
  --handoff-out betting/data/2026-07-06_tipster_handoff.json
```

### Certified Shadow Run (Including ZawodTyper)
```fish
.venv-tipster-v2/bin/python scripts/pipeline_steps/s2_tipsters_v2_live_dry_run.py \
  --date 2026-07-06 \
  --terms-reviewed-json docs/pipeline/tipster_terms_review.local.json \
  --include-certified-shadow \
  --max-pages-per-source 3 \
  --out betting/data/2026-07-06_tipster_consensus.json \
  --sqlite-db betting/data/tipsters.sqlite \
  --handoff-out betting/data/2026-07-06_tipster_handoff.json
```

### Offline/Fixture Mode
To test parser behavior deterministically using saved HTML snapshots without any network traffic:
```fish
.venv-tipster-v2/bin/python scripts/pipeline_steps/s2_tipsters_v2.py \
  --date 2026-07-06 \
  --fixture-html-dir tests/fixtures/tipsters/ \
  --include-certified-shadow-fixtures \
  --out betting/data/2026-07-06_tipster_consensus_offline.json \
  --handoff-out betting/data/2026-07-06_tipster_handoff_offline.json
```

## 3. Storage Sinks
All outputs are stored in two locations:
1. **JSON Artifacts:** Full structured consensus, picks list, and block/skip audit metadata.
2. **SQLite Sinks:** Stored in tables `tipster_picks_v2` and `tipster_consensus_v2` for downstream query execution.

## 4. Fail-Closed Protocol
If any run produces zero picks, or if all active sources are blocked/skipped due to compliance checks, the orchestrator triggers `fail_closed=true` and halts the downstream pipeline from running any automated placements.
