# Model Resolution Fix Strategy

- Preferred code change applied: `INHERIT_PARENT_MODEL_STRATEGY`.
- Runtime completion status: `BLOCK`.

## Applied Changes

- Kept `bet-orchestrator` explicitly pinned to `google-vertex/gemini-3.5-flash-flex-high`.
- Removed explicit `model:` overrides from required betting specialist agent markdown files.
- Removed explicit `model` overrides from required betting specialist entries in `.kilo/profiles/kilo.local.jsonc`.
- Updated contracts/audits/tests/docs to accept inherited verified parent routing as PASS and to fail broken explicit overrides.

## Why Not Register A Custom Model

- `kilo models google-vertex` already lists `google-vertex/gemini-3.5-flash-flex-high`.
- `kilo debug config` shows the alias in merged config.
- The issue is therefore not missing catalog registration.

## Blocking Reason

- Live subagent launch smokes still return `ProviderModelNotFoundError` even after inheritance repair is visible in merged config.
- This points to a stale runtime/UI/session resolver state outside the checked-in file contract.
- No silent fallback was applied.
