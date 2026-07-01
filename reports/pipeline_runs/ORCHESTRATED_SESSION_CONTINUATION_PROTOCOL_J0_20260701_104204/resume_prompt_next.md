TASK_ID=ORCHESTRATED_SESSION_CONTINUATION_PROTOCOL_J0
RUN_ID=ORCHESTRATED_SESSION_CONTINUATION_PROTOCOL_J0_20260701_104204
TARGET_PHASE=J1
STATUS_REQUIRED=PASS_CONTINUATION_REQUIRED

Read first:
- `reports/pipeline_runs/ORCHESTRATED_SESSION_CONTINUATION_PROTOCOL_J0_20260701_104204/session_state.json`
- `reports/pipeline_runs/ORCHESTRATED_SESSION_CONTINUATION_PROTOCOL_J0_20260701_104204/phase_checkpoint.md`
- `reports/pipeline_runs/ORCHESTRATED_SESSION_CONTINUATION_PROTOCOL_J0_20260701_104204/artifact_manifest.json`
- `docs/pipeline/Orchestrated Session Continuation Protocol.md`
- `docs/pipeline/Unified Orchestrated Analyst Session Contract.md`

Execute phase J1 only:
- Run `bet-scanner`
- Run `bet-scout`

Forbidden in J1:
- `bet-enricher`
- `bet-statistician`
- `bet-valuator`
- `bet-challenger`
- `bet-builder`
- `bet-test-engineer`

Required J1 artifacts:
- `scanner_event_universe.json`
- `scout_tipster_opinion_layer.json`
- updated `orchestrator_subagent_manifest.json`
- updated `session_state.json`
- updated `phase_checkpoint.md`
- next `resume_prompt_next.md`

Stop condition:
- If J1 artifacts are complete, write the checkpoint and stop with `PASS_CONTINUATION_REQUIRED`.
- Never return `PASS_FINAL` from J1.
