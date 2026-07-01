# Runtime Inheritance Smoke

- Run ID: `UI_SELECTED_RUNTIME_MODEL_INHERITANCE_REPAIR_D_20260701_134441`
- Branch: `feat/subagent-provider-model-resolution-repair-b`
- Active UI mode: `Code`
- Active UI model: `openai/gpt-5.4`
- Active UI reasoning: `Medium`
- ProviderModelNotFoundError: `false`
- Silent fallback detected: `false`
- Verdict: `PASS`

## Results

- `bet-enricher`: PASS; active_runtime_model=`openai/gpt-5.4`; inherited_parent_model=`true`; explicit_override_used=`false`; artifact=`reports/pipeline_runs/UI_SELECTED_RUNTIME_MODEL_INHERITANCE_REPAIR_D_20260701_134441/bet-enricher_launch_tiny_artifact.md`
- `bet-statistician`: PASS; active_runtime_model=`openai/gpt-5.4`; inherited_parent_model=`true`; explicit_override_used=`false`; artifact=`reports/pipeline_runs/UI_SELECTED_RUNTIME_MODEL_INHERITANCE_REPAIR_D_20260701_134441/bet-statistician_launch_tiny_artifact.md`
- `bet-valuator`: PASS; active_runtime_model=`openai/gpt-5.4`; inherited_parent_model=`true`; explicit_override_used=`false`; artifact=`reports/pipeline_runs/UI_SELECTED_RUNTIME_MODEL_INHERITANCE_REPAIR_D_20260701_134441/bet-valuator_launch_tiny_artifact.md`

## Basis

- Each required smoke subagent launched successfully in this session.
- Each subagent reported `active_runtime_model=openai/gpt-5.4` and `provider_model_not_found_error=false`.
- Required betting-agent files and profile entries contain no explicit model pin after repair, so parent-model inheritance is the only configured path for these launches.
- No conflicting explicit override or silent fallback was observed in the launch results.
