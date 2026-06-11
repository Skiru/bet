# Model Lock Policy

## Locked Model

**Model ID:** `mlx-community/Qwen3.6-35B-A3B-4bit`
**Lock Date:** 2026-06-09
**Validated By:** Contract execution P00-P17

## Change Policy

DO NOT change this model without:

1. Running full benchmark suite (`tools/local-llm/harness/`)
2. Verifying tool call reliability ≥98%
3. Testing Kilo prefix cache speedup ≥5x
4. Checking memory stability under load
5. Updating all configuration files
6. Creating git commit with rollback point
7. Approval from system owner

## Validation Evidence

All gates passed per contract:

- P05: Baseline validated (71.94 tok/s)
- P07: Cache proven (12.4x speedup)
- P08: Comparison complete (Standard > OptiQ)
- P09: MTP compatibility checked (documented)
- P12: Soak test passed (0 crashes)

## Rollback

```fish
git checkout <commit-before-model-change>
./scripts/start-local-model.fish
```
