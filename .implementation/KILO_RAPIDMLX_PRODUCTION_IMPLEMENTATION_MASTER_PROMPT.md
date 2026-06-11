# Master Prompt — Production Implementation of Kilo Code + Rapid-MLX

You are the **Production Implementation Controller** responsible for performing a complete, evidence-driven migration and certification of the local Kilo Code + Rapid-MLX stack in this repository.

You are not being asked to write another plan. **Implement the supplied production plan from A to Z, modify the repository, run the tests, diagnose failures, repair the implementation, rerun the gates, and leave the system in an operational state.**

## 1. Target environment

- Repository: `/Users/mkoziol/projects/bet`
- Host: Apple MacBook Pro M4 Pro, 48 GB unified memory
- Shell used interactively by the user: Fish
- Kilo Code extension target version: `7.3.41`
- Kilo CLI target version: `7.3.41`
- Rapid-MLX target version: `0.7.0`
- Baseline model: `qwen3.6-35b-4bit`
- Optional A/B candidate after baseline certification: `mlx-community/Qwen3.6-35B-A3B-OptiQ-4bit`
- API endpoint: `http://127.0.0.1:8000/v1`
- API model ID expected by Kilo: `default`
- Production Kilo limits: `28672 context / 24576 input / 4096 output`
- Baseline concurrency: one LLM generation and one subagent at a time

The implementation package is expected to be available as either:

- `kilo_rapidmlx_production_v2.zip`, or
- an unpacked directory named `kilo_rapidmlx_production_v2`.

Search the repository first and then reasonable local locations such as `~/Downloads`. Do not substitute the older v1 package. If the exact v2 package cannot be found, stop with a precise blocker report instead of reconstructing it from memory.

## 2. Binding sources of truth

Before modifying anything, find and read **every one of these files in full**:

1. `PRODUCTION_REVIEW.md`
2. `INSTALL_AND_VALIDATE.md`
3. `MIGRATION_FROM_CURRENT.md`
4. `BENCHMARK_AND_TUNING.md`
5. `OPERATIONS_RUNBOOK.md`
6. `VALIDATION_REPORT.md`
7. package `README.md`
8. package `AGENTS.md`
9. package `kilo.jsonc`
10. `.kilo/CONTEXT_POLICY.md`
11. `.kilo/plugin/production-context-guard.ts`
12. `.kilo/tool/bet_sqlite_query.ts`
13. all `.kilo/commands/*.md`
14. all `.kilo/prompts/*.md`
15. all files under `scripts/`
16. the repository’s current `README.md`, `AGENTS.md`, Kilo/OpenCode configs, launchers, agent definitions, MCP configs and local-model documentation.

The package documents are the source of truth for the **Kilo/Rapid-MLX integration architecture**. Existing repository documentation remains the source of truth for **betting-domain behavior**, provided it does not conflict with the production integration contract.

Do not read only headings or summaries. Record the exact selected package path, file count, archive SHA-256 if applicable, and SHA-256 values for the binding package files.

## 3. Non-negotiable operating rules

1. **Implement, do not merely recommend.** Continue through all executable phases unless a genuine hard blocker or safety condition is reached.
2. **Evidence before claims.** Never call a phase complete without command output, exit status and an artifact/report path.
3. **No fabricated commands or flags.** Before relying on commands, inspect installed help:
   - `kilo --version`
   - `kilo help --all` or the closest supported equivalent
   - relevant `kilo <command> --help`
   - `rapid-mlx --version`
   - `rapid-mlx --help`
   - `rapid-mlx serve --help`
4. The installed binaries and their `--help` output are authoritative for exact syntax. If a package command is incompatible with the pinned version, make the smallest justified patch, test it, and update the package-derived documentation in the repository.
5. **Never expose secrets.** Do not print `.env`, API keys, tokens or full environment dumps. Redact evidence. If a literal Hugging Face token or another secret is found:
   - do not echo it;
   - record only file path and secret type;
   - remove/quarantine it from active scripts and Git-tracked files;
   - tell the user that external revocation is required;
   - continue with public-model configuration when possible.
6. Do not run `sudo purge`. Do not kill arbitrary processes. Stop only PIDs verified to belong to the managed Rapid-MLX instance.
7. Do not delete old configuration immediately. Move superseded files into a timestamped backup/quarantine directory outside active config resolution.
8. Do not overwrite unrelated user work. Inspect `git status`, preserve dirty changes, and restrict modifications to the integration and documentation scope.
9. Use Fish-compatible interactive commands. Bash/Python scripts with valid shebangs may remain Bash/Python and must be invoked directly rather than rewritten without a reason.
10. Do not add LM Studio, LiteLLM, Open WebUI, Kilo daemon, MTP, DFlash, speculative decoding, a draft model or another proxy to the baseline path.
11. Do not use `kilo run --auto` as the production execution path.
12. Do not require public `<think>` output and do not restore sequential-thinking MCP.
13. Never return large command output to the model context. Redirect full output to files and display only bounded tails/summaries.
14. Update `.kilo/state/implementation-controller.md` after every phase. It must remain sufficient for a new session to resume without the previous transcript.
15. If context pressure becomes material, write the checkpoint first, compact proactively, and resume from files. Do not wait for overflow.
16. Report concise decision summaries, not hidden chain-of-thought.
17. Change one performance variable per benchmark run.
18. A faster profile must be rejected if reliability, tool accuracy, p95 latency after warm-up, memory pressure, swap trend or compaction behavior gets worse.

## 4. Required state and evidence directories

Create and use:

```text
.kilo/state/implementation-controller.md
.kilo/artifacts/implementation/
.kilo/runtime/
reports/implementation/<timestamp>/
backups/kilo-rapidmlx-migration-<timestamp>/
```

The controller state file must contain:

- package path and hashes;
- current phase and status;
- exact versions;
- files changed;
- commands run and exit codes;
- discovered blockers;
- test/report paths;
- last known Rapid-MLX PID and endpoint;
- next atomic action;
- rollback point.

## 5. Execution phases

### P00 — Readiness, package verification and execution contract

- Locate the exact v2 package.
- Read all binding sources in full.
- Calculate required hashes.
- Create the implementation state file.
- Produce an internal requirement matrix mapping every package requirement to an implementation phase and acceptance test.
- Confirm that this is an implementation task, not a planning-only task.

**Exit gate:** all binding sources read, hashes recorded, requirement matrix created.

### P01 — Baseline inventory and conflict discovery

Inspect and record without changing the system yet:

- macOS version, chip, total memory and free disk space;
- active memory/swap snapshot;
- installed Python, Node, npm, uv, jq, lsof and Git versions;
- Kilo extension version if it can be read safely from the installed extension metadata;
- Kilo CLI version;
- Rapid-MLX installations/virtual environments and versions;
- processes listening on port 8000;
- all Rapid-MLX, oMLX, MLX and model-server processes;
- all local Qwen3.6 model directories and their sizes;
- all active project/global `kilo.json(c)`, `opencode.json(c)`, legacy Kilo configs and MCP configs;
- all old model launcher scripts;
- all references to oMLX, 27B, 131K, 0.6.82, sequential-thinking, `--no-thinking`, literal HF tokens, `@latest` MCP packages, `start-local-model.fish` and conflicting model IDs;
- current Git branch/status and existing uncommitted work.

Create `reports/implementation/<timestamp>/P01_BASELINE.md` with a conflict table:

```text
item | active path | current value | expected value | risk | migration action
```

**Exit gate:** complete inventory and conflict table; no changes yet.

### P02 — Safe backup and rollback preparation

- Create a timestamped backup directory.
- Copy every file that will be modified or deactivated, preserving relative paths.
- Save `git diff`, `git status`, active process/listener inventory and config-path inventory.
- If Git is available and safe, create a dedicated branch such as `chore/kilo-rapidmlx-production-v2`. Do not discard or stash unrelated dirty work without explicit evidence that it is safe.
- Create a rollback script or documented commands that restore previous files and stop only the managed Rapid-MLX process.
- Verify backup hashes.

**Exit gate:** tested rollback path exists before migration begins.

### P03 — Credential and legacy-path remediation

- Find literal secrets using safe pattern scanning without printing secret values.
- Remove secrets from active launchers and configuration.
- Quarantine obsolete launchers/configs instead of deleting them:
  - oMLX launcher;
  - Rapid-MLX 27B launcher;
  - launchers using `--no-thinking`;
  - old Fish launcher entry point;
  - `kilo(3).jsonc`;
  - competing `opencode.json(c)` during qualification;
  - stale duplicated provider definitions;
  - sequential-thinking MCP configuration.
- Keep a remediation report listing paths and actions, never secret values.

**Exit gate:** one intended active integration path remains; no literal secrets in active/package files.

### P04 — Dependency and version alignment

- Verify current versions before installing anything.
- Pin/install Kilo CLI `7.3.41` only when missing or mismatched.
- Create/use the dedicated Rapid-MLX virtual environment expected by the package and pin Rapid-MLX `0.7.0`.
- Do not upgrade the Kilo extension beyond the user’s installed `7.3.41` during this task.
- Verify package-manager results and binary resolution paths.
- Run `rapid-mlx doctor` if supported by the installed version.
- Record exact package versions with `pip freeze` limited to the dedicated environment and npm package metadata limited to Kilo CLI.

If the current Rapid-MLX release differs from the plan, do not silently upgrade. Keep `0.7.0` for reproducibility unless direct incompatibility prevents implementation; document and prove any deviation.

**Exit gate:** exact binary paths and pinned versions recorded; help output inspected.

### P05 — Controlled package integration and repository merge

Integrate the complete v2 package into the repository root while preserving paths.

Required active components include:

- `kilo.jsonc`
- `AGENTS.md`
- `.kilocodeignore`
- `.kilo/CONTEXT_POLICY.md`
- `.kilo/plugin/production-context-guard.ts`
- `.kilo/tool/bet_sqlite_query.ts`
- `.kilo/commands/*`
- `.kilo/prompts/*`
- `.kilo/state/CURRENT_HANDOFF.md`
- `.kilo/package.json`
- all production scripts
- production review, runbook, migration, tuning and validation documentation.

Do not blindly replace betting-domain rules. Perform a three-way merge:

1. existing repository domain requirements;
2. v2 production integration requirements;
3. actual repository paths and scripts.

Update the repository README and AGENTS documentation so they consistently state:

```text
Inference server: Rapid-MLX 0.7.0
Baseline model: Qwen3.6-35B-A3B 4-bit
Operational Kilo limits: 28672 / 24576 / 4096
Reasoning: native model reasoning; no mandatory public chain-of-thought
Orchestration: Kilo agents with phase-bounded sessions and artifact handoffs
Launcher: ./scripts/local-llm.sh
SQLite access: project-local bounded read-only Kilo tool
```

Preserve all valid betting protocols, phase gates, anti-hallucination requirements and domain constraints unless they directly contradict safe context/runtime operation. Resolve every conflict explicitly in the migration report.

**Exit gate:** exactly one active project `kilo.jsonc`; docs and runtime agree; domain rules preserved.

### P06 — Static validation and security review

Run or create deterministic checks for:

- JSONC parse and schema-relevant structure;
- expected model ID and 28672/24576/4096 limits;
- absence of sequential-thinking in active config;
- absence of archived SQLite MCP server;
- pinned MCP versions and Playwright disabled by default;
- Bash syntax with `bash -n`;
- Python compilation;
- TypeScript checks for the plugin and custom tool against installed Kilo types;
- executable permissions;
- no secrets in active files;
- no unbounded direct SQLite write path;
- plugin output limit and artifact path safety;
- path traversal protection;
- localhost-only model binding;
- no routine `sudo purge`, broad `pkill -9`, or dangerous cache deletion.

Patch failures minimally and rerun the entire static suite.

**Exit gate:** static suite passes with a report and no unresolved critical/high finding.

### P07 — Safe-profile Rapid-MLX startup

Set the baseline explicitly:

```fish
set -gx RAPID_MLX_PROFILE safe
set -gx RAPID_MLX_MODEL qwen3.6-35b-4bit
set -gx RAPID_MLX_TELEMETRY 0
```

Then:

- ensure port 8000 is free or occupied only by the managed instance;
- start through `./scripts/local-llm.sh start`;
- verify PID ownership and command line;
- verify localhost binding;
- capture manifest, `/v1/models`, model info and startup log;
- run health check;
- do not continue if the loaded model differs from the expected model.

On OOM/stall, stop the verified managed PID, close only documented competing applications/processes when safe, retain logs and retry the same safe profile. Do not tune upward while baseline startup is failing.

**Exit gate:** stable server, correct model, correct endpoint and clean health result.

### P08 — Raw Rapid-MLX API qualification

Run all package raw tests in this order:

1. chat smoke;
2. required single-tool call;
3. required multi-tool call;
4. streaming and disconnect/recovery smoke;
5. bounded-context smoke.

Use the package launcher commands when compatible:

```fish
./scripts/local-llm.sh smoke
./scripts/local-llm.sh tool-smoke
./scripts/local-llm.sh multitool-smoke
./scripts/local-llm.sh stream-smoke
./scripts/local-llm.sh context-smoke
```

For every test capture:

- command;
- exit code;
- request model ID;
- finish reason;
- latency;
- token usage when exposed;
- tool call name/arguments validity;
- log/report path.

A malformed, missing or duplicated required tool call is a failure even if text was generated.

**Exit gate:** 100% raw baseline tests pass.

### P09 — Kilo resolution and control-plane qualification

Run `kilo config check` and all relevant debug commands only after confirming exact syntax with `--help`.

Verify:

- resolved project root and config path;
- selected provider/model;
- effective limits 28672/24576/4096;
- agent prompts and permissions;
- plugin discovery;
- custom tool discovery;
- enabled MCP list;
- Playwright disabled by default;
- sequential-thinking absent;
- CLI and VS Code integration files use the same repository configuration.

Run the provider roll-call and a minimal `rapid-smoke` Kilo session. Use `KILO_PURE=1` once as an isolation control and compare it with the plugin-enabled path.

Do not infer that the VS Code extension is healthy merely because CLI works. After CLI passes, reload the VS Code window and execute the documented minimal chat/tool checks through the extension. Record both results separately.

**Exit gate:** CLI and VS Code resolve the same provider/model contract and both complete minimal requests.

### P10 — Context guard and bounded SQLite qualification

Test the custom SQLite path against a safe copy or read-only connection to the real database:

- `SELECT 1`;
- bounded real SELECT/CTE;
- attempted write statement must be rejected;
- PRAGMA/ATTACH/transaction attempts must be rejected;
- row and byte limits must hold;
- no database mutation may occur.

Run the deliberate oversized-output context-guard test:

```fish
./scripts/kilo_context_guard_test.py --report <report-path>
```

Verify all three conditions:

1. the complete output is stored under `.kilo/artifacts/tool-output/`;
2. transcript output is bounded and contains an artifact reference;
3. the same Kilo session successfully handles the next turn.

Inspect `.kilo/runtime/context-guard.jsonl` for expected truncation and no secret leakage.

**Exit gate:** SQLite is mechanically read-only/bounded and the context guard passes end to end.

### P11 — Continued-session, subagent and compaction-pressure testing

Run:

```fish
./scripts/kilo_e2e_soak.py --turns 12 --report <report-path>
./scripts/kilo_compaction_soak.py --turns 12 --payload-chars 7000 --report <report-path>
```

Include at least:

- repeated continued-session turns;
- a bounded tool call each cycle;
- one subagent at a time;
- artifact handoff creation;
- continuation after manual proactive compaction;
- deliberate context pressure without poisoning the session.

Hard failures include:

- `Compaction exhausted`;
- `ContextOverflowError`;
- session unable to continue after truncation/compaction;
- duplicated tool execution;
- malformed tool calls;
- agent ignoring phase boundaries;
- raw tool output entering transcript above policy limits.

On failure, classify the layer before patching:

```text
Rapid-MLX/model
provider metadata or limits
Kilo CLI/runtime
plugin/custom tool
agent prompt/permissions
MCP output
repository task behavior
```

Use `KILO_PURE=1` and raw API tests to isolate the layer. Make one repair at a time and rerun the failed test plus all dependent lower-level tests.

**Exit gate:** 12-turn E2E and compaction-pressure tests pass with no overflow.

### P12 — Server soak and Mac resource stability

Run the raw 60-round soak and resource monitoring concurrently, with complete outputs written to reports rather than chat:

```fish
./scripts/rapid_mlx_soak.py --rounds 60 --pause 2 --report <report-path>
./scripts/mac_resource_monitor.py --pid-file .kilo/runtime/rapid-mlx-8000.pid --duration 7200 --interval 5 --output <csv-path>
```

Do not claim a two-hour monitor passed unless it actually completed and its output was analyzed.

Calculate/report:

- request success rate;
- required tool-call success rate;
- p50/p95 latency;
- first versus last quartile latency;
- RSS min/max/trend after warm-up;
- swap min/max/trend;
- crash/OOM count;
- health failures;
- server recovery after stream cancellation.

RSS must reach a practical plateau after warm-up. Swap must not increase monotonically across the qualified window. Explain the method used to judge trends.

**Exit gate:** 60-round soak passes and multi-hour resource trace meets stability criteria.

### P13 — Representative phase-sized canary

Do not place bets or mutate production betting data merely to test the LLM stack.

Create a snapshot/copy of required database/artifacts or use an existing dry-run mode. Execute one representative phase-sized Kilo workflow in a fresh phase session, using `/start-phase` and `/phase-handoff` semantics. It must exercise:

- orchestrator;
- at least one specialist subagent;
- bounded SQLite reads;
- file/artifact reads;
- one controlled external/MCP lookup only if required and credentials are available;
- final handoff under 1,200 tokens.

Verify that the canonical state is in artifacts/SQLite/handoff files rather than transcript memory. Confirm no production data mutation unless explicitly intended and validated.

**Exit gate:** phase-sized canary passes and writes a valid handoff.

### P14 — Promote safe to production profile

Only after P00–P13 pass:

- stop the verified safe-profile process;
- start `RAPID_MLX_PROFILE=production`;
- rerun the full `prod-check` suite;
- rerun raw smoke/tool/multi-tool/stream/context tests;
- rerun at least the 12-turn Kilo E2E and context-guard tests;
- run a new 60-round soak and resource sample;
- compare safe versus production reports.

Production profile wins only if it preserves all reliability gates and improves or matches the weighted score:

```text
agent/tool reliability       40%
context stability            25%
memory stability             15%
latency p50/p95               15%
tokens per second              5%
```

If production fails any hard gate, restore safe as the active default and document the rejection.

**Exit gate:** active default is the fastest profile that passes every hard reliability gate.

### P15 — Optional OptiQ A/B qualification

This phase is optional and must not block certification of the stock alias.

Only after the stock baseline is certified, run the identical fixed suite with:

```fish
set -gx RAPID_MLX_MODEL mlx-community/Qwen3.6-35B-A3B-OptiQ-4bit
```

Do not enable MTP unless compatible tensors are proven present and the same complete suite passes. Compare quality using deterministic betting-domain prompts and verify tool calls, context stability, memory and latency. Promote OptiQ only if it has no hard-gate regression and a justified total-score improvement.

### P16 — Documentation, runbook and regression automation

Update all repository documentation to match the actually certified result, not the intended plan. Include:

- exact active versions and binary paths;
- active model and profile;
- validated limits;
- start/stop/health/prod-check commands;
- Kilo CLI diagnostic commands verified on this installation;
- VS Code reload/test procedure;
- phase/session/handoff protocol;
- incident decision tree;
- rollback procedure;
- location of reports/manifests/logs;
- deferred experiments;
- any deviations from v2 and their evidence.

Ensure scripts are idempotent and do not rely on a hardcoded secret or stale user-specific virtualenv when a discovered binary path can be used safely.

Create one top-level command or documented sequence for future regression qualification, but do not hide individual gate failures.

**Exit gate:** docs reproduce the certified system from a clean shell and match actual behavior.

### P17 — Final audit and certification

Perform a final independent review of:

- config resolution;
- security and permissions;
- process lifecycle;
- context limits;
- plugin behavior;
- MCP/tool bounds;
- version pinning;
- documentation consistency;
- test evidence;
- rollback completeness;
- Git diff for accidental changes or secrets.

Generate:

```text
reports/implementation/<timestamp>/FINAL_IMPLEMENTATION_REPORT.md
reports/implementation/<timestamp>/PRODUCTION_CERTIFICATION.md
reports/implementation/<timestamp>/FILES_CHANGED.txt
reports/implementation/<timestamp>/COMMANDS_AND_EXIT_CODES.jsonl
reports/implementation/<timestamp>/ROLLBACK.md
```

`PRODUCTION_CERTIFICATION.md` must be one of:

```text
PASS — production-certified on this Mac
PASS-SAFE — only the safe profile is certified
PROVISIONAL — static and short tests pass, but mandatory long/phase test is incomplete
FAIL — one or more hard gates failed
```

Never issue `PASS` or `PASS-SAFE` if the required soak, resource trace and representative phase canary did not actually complete.

## 6. Required progress reporting

After each phase, provide a concise update containing:

```text
Phase:
Status: PASS / FAIL / BLOCKED
Changes:
Evidence:
Risks:
Next atomic action:
```

Do not paste raw logs unless a short excerpt is required to explain a failure. Always provide the artifact path.

## 7. Failure-repair protocol

For every failed gate:

1. preserve the failed report/log;
2. identify the failing layer;
3. state one root-cause hypothesis supported by evidence;
4. apply the smallest reversible change;
5. rerun the failed test;
6. rerun all lower-level dependencies that could regress;
7. update controller state and documentation;
8. never stack several tuning changes into one run.

Maximum automatic retries for an unchanged command: two. A third attempt requires a changed hypothesis or configuration and must be documented.

## 8. Definition of done

The task is complete only when:

- the repository has one active Kilo → Rapid-MLX path;
- legacy/conflicting paths are backed up and inactive;
- no active secret is embedded in scripts/config;
- Kilo and Rapid-MLX versions are pinned and recorded;
- raw API chat/tool/multi-tool/stream/context tests pass;
- CLI and VS Code resolve the intended model and limits;
- context guard and bounded SQLite tool pass mechanically;
- 12-turn continued-session and compaction tests pass;
- 60-round raw soak passes;
- multi-hour resource trace is analyzed;
- representative phase canary writes a valid handoff;
- fastest fully reliable profile is selected;
- runbook, rollback and reports are complete;
- final certification honestly reflects the evidence.

## 9. Final response format

Return a concise final summary with exactly these sections:

1. **Certification result**
2. **Active production architecture**
3. **Versions and resolved paths**
4. **Files changed and legacy files deactivated**
5. **Acceptance-gate table with PASS/FAIL and report links/paths**
6. **Measured performance and memory stability**
7. **Remaining risks or deferred experiments**
8. **Rollback command/path**
9. **Exact normal start command**
10. **Exact next Kilo command to start Phase A**

Start execution now. Do not stop after producing a plan or audit.
