# Sports integrations portfolio audit kit — reviewed v2

## Files

- `SPORTS_INTEGRATIONS_PORTFOLIO_AUDIT_CONTRACT.md` — binding audit contract.
- `KILO_GPT54_PORTFOLIO_AUDIT_MASTER_PROMPT.md` — launcher prompt.
- `FINAL_VALIDATION_REPORT.md` — changes and review findings for this kit; do not copy it into the audited repository unless desired.

## Usage

1. Copy `SPORTS_INTEGRATIONS_PORTFOLIO_AUDIT_CONTRACT.md` to the repository root.
2. Start a fresh Kilo task and mention the contract with `@/SPORTS_INTEGRATIONS_PORTFOLIO_AUDIT_CONTRACT.md`.
3. Use GPT-5.4 reasoning `high` for the controller. `medium` is acceptable only when the contract's per-integration checkpoints are followed strictly.
4. Paste the contents of `KILO_GPT54_PORTFOLIO_AUDIT_MASTER_PROMPT.md`.
5. The audit must not repair production code. It creates a reproducible baseline and remediation backlog.
6. After completion, repair integrations one at a time using a separate live-repair contract and the reasoning level assigned in the backlog.
