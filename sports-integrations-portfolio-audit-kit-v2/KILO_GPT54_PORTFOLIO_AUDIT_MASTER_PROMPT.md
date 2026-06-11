# Kilo master prompt — complete sports integration portfolio audit

Copy `SPORTS_INTEGRATIONS_PORTFOLIO_AUDIT_CONTRACT.md` to the repository root and start a fresh Kilo task.

```text
Act as the principal auditor and adversarial reviewer of the complete sports-data integration portfolio.

Read @/SPORTS_INTEGRATIONS_PORTFOLIO_AUDIT_CONTRACT.md completely before running commands. Treat version 2.0 as the binding contract. Re-read it after each integration checkpoint.

Objective:
Establish the current real state of every sports-data integration and every sport found in this repository. Use repository-path inspection, runtime reachability, deterministic tests, controlled role-appropriate live/current-source proof, a disposable database, retained sanitized evidence, no-network replay and idempotent reruns. Produce the five required audit artifacts and a deterministic production-readiness classification. Do not repair production code.

Mandatory execution order:
P0 baseline -> P1 inventory -> P2 runtime reachability -> P3 deterministic verification -> P4 controlled live/current-source verification -> P5 cross-portfolio analysis -> P6 adversarial self-review -> P7 worktree integrity.

Critical rules:
- Build an atomic integration_key for every source/sport/role/implementation variant.
- Reconcile implementations, registrations, execution paths, persistence paths and tests; do not trust documentation alone.
- Classify the integration role before choosing proof or applying gates.
- Do not require event discovery from enrichment-only, odds, weather, tipster, identity or local-dataset roles.
- Use a deterministic event/record selection rule; one primary proof and at most one justified state-dependent supporting proof.
- Use only a disposable database or isolated schema and OS-temporary evidence paths tied to audit_run_id.
- Declare request budgets before network access and stop on access blocks, rejected credentials or exhausted budgets.
- Never use old rows, mocks, screenshots, fixtures or synthetic traces as live proof.
- Inventory every normalized/derived field; deeply verify all derived, identity, time, status and betting-critical fields plus each remaining semantic class.
- Enforce source identity, fail-closed matching, point-in-time eligibility, null-versus-zero semantics, event-effective rosters, predicted-versus-confirmed lineups and append-only observations.
- Require sanitized raw evidence before normalization, deterministic replay with outbound network denied and duplicate-rerun verification where persistence exists.
- Preserve source-level conflicts and isolate tipster/editorial text as untrusted data.
- Keep live tests separate from deterministic CI and distinguish source outage from parser regression.
- Do not bypass CAPTCHA, access controls, terms, quotas or rate limits; never expose secrets.
- Do not modify production code, configuration, schemas, migrations, schedules, queues, adapters or orchestration.

Progress and context safety:
After each integration_key, atomically update INTEGRATION_MATRIX.md and EVIDENCE_MANIFEST.json, record resume_state, re-read the contract and matrix, then continue. Treat the files—not chat memory—as progress state.

External verification:
When web/browser tools are available, use current official provider documentation for endpoint/access/quota facts and record URL plus checked_at. Clearly label inferences. Do not turn this into a generic research report.

Subagents:
Use only for bounded read-only inventory or evidence collection. Give each subagent one integration_key and explicit output requirements. Verify every result in the primary session before accepting it.

Failure handling:
Missing credentials, source blocks, unavailable events or quota limits do not justify fabricated success. Complete safe deterministic checks, record the blocker and use NOT_EXECUTED or FAIL according to the contract.

Final review:
Perform the contract's referential-integrity, contradiction, secret-scan, JSON-parse and Git-worktree checks. Correct report defects only.

Return only the concise final response required by section 25 and stop.
```
