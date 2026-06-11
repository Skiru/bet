# Rapid-MLX + Kilo Code Production Implementation Contract

**Target:** MacBook Pro M4 Pro, 48 GB unified memory, macOS  
**Implementation controller:** Kilo Code using GPT-5.4 with **Medium reasoning**  
**Scope:** production-grade local LLM infrastructure only  
**Baseline model candidate:** Qwen3.6-35B-A3B 4-bit  
**Baseline runtime candidate:** Rapid-MLX v0.7.0  
**Verified Kilo stable baseline at document creation:** v7.3.41  
**Document date:** 2026-06-11

---

## 1. Mission

Build, test, and certify a reliable project-local integration of Rapid-MLX with Kilo Code for a MacBook Pro M4 Pro with 48 GB unified memory.

The completed setup must provide:

- a pinned and reproducible Rapid-MLX installation;
- a safe localhost-only server lifecycle;
- Qwen3.6-35B-A3B 4-bit as the first benchmark candidate;
- explicit memory, context, output, timeout, and concurrency limits;
- project-level Kilo configuration for an OpenAI-compatible local provider;
- reliable streaming, reasoning separation, tool calling, cancellation, and recovery;
- bounded context growth and proactive handoffs;
- health checks, logs, PID/state handling, metrics, and repeatable benchmarks;
- an operational runbook and a machine-readable certification result.

This phase does **not** implement the betting pipeline, database tools, browser automation, sports APIs, or a large multi-agent architecture. Those are later layers and must not be mixed into infrastructure certification.

---

## 2. Non-negotiable execution policy

1. **Execute one certified phase per Kilo session.**
2. At the end of every phase, update the phase ledger, run the required tests, write a result report, and **STOP**.
3. Do not continue to the next phase in the same conversation, even when the phase passes.
4. Never trust old Rapid-MLX, Kilo, model, launcher, or agent configuration merely because it exists.
5. Never run `git reset --hard`, `git clean`, destructive checkout commands, or delete untracked files.
6. Do not modify global Kilo configuration unless project-level configuration is technically impossible and the reason is documented.
7. Do not invent Rapid-MLX flags or Kilo schema fields. Verify them against:
   - installed command help;
   - installed package source/schema;
   - current official documentation;
   - the pinned release source.
8. Do not enable MTP, DFlash, suffix decoding, TurboQuant, KV/prefix-cache quantization, tool-logits bias, cloud routing, multimodal dependencies, or concurrency greater than one in the raw baseline.
9. Do not optimize tokens per second before correctness and stability pass.
10. Never expose the service on LAN interfaces. Bind to `127.0.0.1` only.
11. The implementation controller remains GPT-5.4 Medium. The local Qwen model is a system under test and must not implement or approve its own infrastructure.
12. Preserve evidence. Every material conclusion must point to a command output, log, benchmark artifact, or exact source revision.

---

## 3. Required repository outputs

Adapt paths only when the repository already has a clear convention. Record every deviation.

```text
.kilo/
  agents/
    local-executor.md
    local-analyst.md
  skills/
    local-llm-operations/
      SKILL.md
  # project plugins only if they are required and supported

config/local-llm/
  rapid-mlx.env.example
  versions.lock

scripts/local-llm/
  install.sh
  start.sh
  stop.sh
  restart.sh
  status.sh
  health.sh
  smoke.sh
  benchmark.py
  collect_metrics.sh

docs/local-llm/
  README.md
  OPERATIONS.md
  TROUBLESHOOTING.md
  IMPLEMENTATION_REPORT.md
  CERTIFICATION.md
  sources.md

var/local-llm/                 # runtime-only; add to .gitignore
  pid/
  logs/
  state/
  results/

kilo.jsonc                     # only after schema and precedence are verified
```

Also create:

```text
.local-llm-phase.json
```

It must contain at least:

```json
{
  "schema_version": "1.0",
  "current_phase": "P0",
  "status": "not_started",
  "last_verified_commit": null,
  "rapid_mlx_version": null,
  "kilo_version": null,
  "model_alias": null,
  "model_repository": null,
  "model_revision": null,
  "certification_artifact": null,
  "open_risks": []
}
```

Do not commit runtime logs, PID files, downloaded model weights, secrets, caches, or virtual environments.

---

## 4. Target baseline

The following is the initial hypothesis, not an unquestionable truth.

| Area | Initial baseline |
|---|---|
| Runtime | Rapid-MLX v0.7.0, pinned after verification |
| Model | `qwen3.6-35b-4bit` alias |
| Exact model | Record resolved Hugging Face repository and revision |
| API | OpenAI-compatible chat completions |
| Address | `127.0.0.1:8000` or a documented free project-specific port |
| Concurrent local generations | 1 |
| Prefix cache | Enabled |
| Prefill step | 2048 |
| GPU memory utilization | Start at 0.70 |
| Server default maximum output | 8192 |
| Tool parser | Automatic Qwen3.6 parser unless testing proves it wrong |
| Reasoning parser | Automatic Qwen3 parser unless testing proves it wrong |
| MTP | Off |
| DFlash | Off; not supported for the 35B baseline |
| Suffix decoding | Off |
| TurboQuant | Off |
| Cache quantization | Off |
| Tool-logits bias | Off |
| Cloud routing | Off |
| Multimodal | Off |
| Telemetry | Force-disabled |
| Kilo total context | 65536 |
| Kilo input limit | 49152 |
| Kilo output limit | 8192 |
| Compaction | Enabled and verified |
| Context handoff target | 40K input tokens or earlier |

If the installed Rapid-MLX v0.7.0 CLI does not expose an assumed setting, do not emulate it with an unrelated flag. Document the discrepancy and use the safest supported behavior.

---

## 5. Phase workflow

## P0 — Discovery, source verification, and safety snapshot

### Goal

Prove the actual machine, repository, installed tools, current configuration precedence, model availability, and official stable versions before changing anything.

### Required actions

1. Read the repository README, root `AGENTS.md`, existing Kilo files, scripts, and local-LLM documentation in full.
2. Confirm:
   - Apple Silicon architecture;
   - macOS version;
   - chip and physical memory;
   - available disk space;
   - current memory pressure and swap baseline.
3. Confirm Git state. The branch must be clean before modifications. If it is not clean, do not discard anything; report and stop.
4. Record:
   - `kilo --version`;
   - `kilo debug paths`;
   - `kilo debug config` before changes;
   - `rapid-mlx --version`;
   - `rapid-mlx --help`;
   - `rapid-mlx serve --help`;
   - `rapid-mlx models` when available;
   - `rapid-mlx doctor`;
   - Python and package-manager versions;
   - active listeners on the intended port;
   - active Rapid-MLX/oMLX/MLX processes.
5. Re-check the latest **stable** Rapid-MLX and Kilo releases from official sources. Do not adopt a pre-release automatically.
6. Compare a newer stable release, if present, with v0.7.0/v7.3.41. Pin the newer release only when its release notes and relevant issues do not introduce a known regression for local OpenAI-compatible tool calling.
7. Locate all existing global and project Kilo/Rapid-MLX files. Copy metadata and hashes into the report. Do not overwrite or delete them.
8. Resolve whether the target model is already present. Record exact path, repository, quantization, size, revision/commit where available, and whether MTP tensors exist. Do not assume the alias resolves to a particular checkpoint.
9. Produce a proposed file-change list and risk list.

### P0 acceptance gate

- clean Git state confirmed;
- actual versions and help output archived;
- current resolved Kilo config archived;
- exact stable version decision justified;
- model identity/provenance resolved or download plan approved by available disk check;
- no files changed except P0 reports and phase ledger.

### P0 STOP

Update `.local-llm-phase.json`, write `docs/local-llm/IMPLEMENTATION_REPORT.md`, summarize evidence, and stop.

---

## P1 — Pinned Rapid-MLX raw baseline

### Goal

Install or isolate a reproducible Rapid-MLX runtime and prove raw inference before Kilo integration.

### Installation policy

Prefer an isolated, pinned Python 3.12 environment owned outside tracked source or inside a gitignored runtime directory. A system Homebrew installation may be reused only when it can be version-pinned and reproduced. Record the chosen method and why.

Never run a remote one-line installer without first reviewing the downloaded script.

### Required actions

1. Pin the selected Rapid-MLX version in `config/local-llm/versions.lock`.
2. Install text-only dependencies; do not install vision/audio extras.
3. Run `rapid-mlx doctor` and archive the complete result.
4. Resolve/download `qwen3.6-35b-4bit` only after disk and model-provenance checks.
5. Start the server manually for baseline testing using only verified CLI flags.
6. Force:
   - `127.0.0.1` binding;
   - telemetry disabled;
   - cloud routing disabled;
   - output limit 8192;
   - prefill step 2048;
   - GPU memory utilization 0.70 when supported;
   - all experimental optimizations off.
7. Record exact startup command, environment, package freeze, model identity, startup time, and initial memory state.
8. Test the API directly, without Kilo.

### Mandatory raw API tests

- health/readiness;
- simple non-streamed chat;
- streamed chat;
- two-turn conversation;
- repeated stable-prefix request to observe cache behavior;
- reasoning-enabled request when the API supports it;
- reasoning-disabled request when the API supports it;
- required single tool call;
- sequential three-tool chain using harmless mock tools;
- invalid/missing tool argument rejection in the client harness;
- output-limit truncation detection;
- client cancellation during generation;
- successful request immediately after cancellation;
- graceful shutdown and restart;
- port-conflict behavior;
- unexpected server termination and stale-state handling.

### P1 acceptance gate

- raw API works without Kilo;
- server binds only to localhost;
- exact model and version are recorded;
- no malformed tool call is executed;
- cancellation does not poison the next request;
- output truncation is visible;
- no server crash during the smoke sequence;
- memory pressure is not sustained red;
- no experimental optimization is enabled.

### P1 STOP

Persist raw results, update the ledger, and stop.

---

## P2 — Operational server lifecycle

### Goal

Create safe, idempotent operational scripts for daily use.

### Required launcher properties

`start.sh` must:

- use the pinned executable, not whichever binary appears first on `PATH`;
- load a validated environment file without `eval`;
- reject unknown or invalid values;
- verify Apple Silicon, free disk, model availability, port availability, and existing PID/state;
- bind to `127.0.0.1`;
- force telemetry off;
- start one server instance only;
- create a new timestamped log;
- capture PID and process-start identity safely;
- wait for real readiness using an API request, not merely an open TCP port;
- fail with a non-zero exit and diagnostic on timeout;
- clean stale PID state without killing unrelated processes;
- never silently kill a process that it did not start.

`stop.sh` must:

- verify that the PID belongs to the recorded Rapid-MLX process;
- send graceful termination first;
- wait a bounded time;
- terminate the owned process group only when necessary;
- remove state only after process termination is confirmed.

`status.sh` must report:

- process state;
- PID and uptime;
- bound address/port;
- model alias and resolved model;
- Rapid-MLX version;
- readiness;
- latest log;
- process RSS;
- system memory pressure and swap snapshot.

`health.sh` must perform:

1. process ownership check;
2. API readiness check;
3. minimal chat completion;
4. optional tool-call probe in deep mode.

### Logging

- do not log prompts or tool arguments by default;
- redact authorization headers and environment values;
- use timestamped logs and a stable `latest.log` reference;
- implement bounded retention or a documented cleanup command;
- preserve crash logs used by certification.

### P2 acceptance gate

- repeated start is idempotent;
- repeated stop is safe;
- stale PID test passes;
- occupied port test passes;
- killed-server recovery passes;
- startup timeout is bounded;
- all shell scripts pass `shellcheck` when available;
- scripts work from a path containing spaces;
- no secrets appear in logs.

### P2 STOP

Persist lifecycle test results, update the ledger, and stop.

---

## P3 — Minimal project-level Kilo integration

### Goal

Connect Kilo to the certified raw server without relying on global or inferred configuration.

### Required actions

1. Re-read the current official Kilo custom-model schema and installed schema.
2. Determine actual project/global/environment precedence using `kilo debug config`.
3. Create the smallest valid project-level `kilo.jsonc`.
4. Configure an OpenAI-compatible provider that points to the localhost Rapid-MLX endpoint.
5. Map the Kilo-facing model name to the model identifier accepted by Rapid-MLX. Verify the outgoing identifier with logs or a controlled request.
6. Explicitly declare:
   - text-only modalities;
   - tool calling support;
   - reasoning support only when validated;
   - total context 65536;
   - input limit 49152;
   - output limit 8192.
7. Enable Kilo compaction and pruning using only verified schema keys. Set a proactive threshold near 65–70% of the operational input limit.
8. Capture `kilo debug config` after changes and confirm all intended values.
9. Create only two minimal local-model agents:
   - `local-executor`: short actions, tools, bounded output, no deep analysis;
   - `local-analyst`: reasoning and synthesis, no raw shell auto-approval.
10. Create one small Skill for local-LLM operations. Do not load the complete betting methodology into root instructions.
11. Keep raw Bash on ask/deny. Do not use `--auto` for certification.
12. Test through Kilo CLI first. Test VS Code only after CLI succeeds.

### Important session-safety rule

Do not replace the model/provider used by the active GPT-5.4 implementation session. Test the new local provider in a separate Kilo CLI process or clean test workspace.

### Mandatory Kilo tests

- provider connection;
- simple chat;
- streamed response;
- local model selected explicitly;
- single harmless tool call;
- sequential tool calls;
- reasoning response;
- non-thinking/low-thinking executor behavior when supported;
- visible output-limit handling;
- resolved context/input/output limits;
- manual `/compact` in a disposable session;
- automatic compaction in a synthetic session;
- continuation after compaction;
- cancellation and next-request recovery;
- CLI and VS Code smoke parity.

### P3 acceptance gate

- project config wins without modifying global config;
- `kilo debug config` shows non-zero explicit limits;
- Kilo does not send unsupported parameters;
- tool calls are parsed as tools, not plain text;
- output-limit exhaustion is visible;
- compaction works in the disposable test;
- no `ContextOverflowError` or `Compaction exhausted` occurs;
- active GPT-5.4 implementation session remains unaffected.

### P3 STOP

Persist resolved config and test results, update the ledger, and stop.

---

## P4 — Reliability and context certification

### Goal

Prove that the baseline is suitable for long, sequential local-agent work on this machine.

### Test matrix

Run at least:

- 50 required single-tool requests;
- 20 sequential three-tool chains;
- 20 streamed responses;
- 10 cancellation/recovery cycles;
- 10 server restart/recovery cycles;
- repeated-prefix cache test with at least 20 repetitions;
- synthetic prompt sizes near 8K, 16K, 32K, 40K, and 48K input tokens;
- one 60-minute mixed-workload soak;
- one test while VS Code, Kilo, a browser, and normal database tools are running.

The tool harness must validate JSON Schema and suppress duplicate tool IDs/idempotency keys before execution.

### Observe

- prompt and output tokens;
- TTFT;
- prompt throughput;
- generation throughput;
- finish reason;
- parser errors;
- malformed/partial/duplicate tool calls;
- cache behavior;
- request duration;
- process RSS;
- memory pressure;
- swap before/after;
- server restarts;
- context utilization;
- compaction count and continuation quality.

Do not claim that MLX metrics from a separate Python process represent the server. Use server instrumentation when available, process-tree metrics, and macOS system memory pressure.

### Hard P4 gates

- 100% of malformed tool arguments blocked by the harness;
- zero duplicate tool executions;
- zero silent partial tool executions;
- at least 99% valid required single-tool calls;
- at least 98% valid sequential chains;
- 100% successful post-cancellation recovery;
- zero `ContextOverflowError`;
- zero `Compaction exhausted`;
- zero server crash during the soak;
- no sustained red memory pressure;
- no monotonic unbounded swap growth;
- no orphaned child process;
- no request binds beyond localhost.

If a gate fails, diagnose and fix the baseline before any optimization.

### P4 STOP

Write the reliability report, update the ledger, and stop.

---

## P5 — Controlled optimization

### Goal

Improve latency or memory only after the baseline has passed P4.

### Method

Change exactly one variable per experiment. Repeat the same benchmark corpus. Retain a change only when it produces a reproducible benefit without quality or reliability regression.

### Candidate order

1. prefill step 4096;
2. prefill step 8192;
3. GPU memory utilization 0.65 versus 0.70 versus 0.75;
4. suffix decoding;
5. tool-logits bias;
6. prefix-cache quantization;
7. MTP only if the exact checkpoint contains required tensors;
8. Qwen3.6-35B-A3B 6-bit as a quality candidate;
9. Qwen3.6-27B dense candidate in a separate run.

### Explicit exclusions

- Do not enable DFlash for Qwen3.6-35B-A3B.
- Do not combine optimizations until each has passed individually.
- Do not retain an optimization only because it raises tokens per second.
- Do not exceed one local generation at a time.

### Retention rule

An optimization may be retained only when:

- tool reliability does not decline;
- reasoning/answer quality does not decline on the fixed corpus;
- cancellation recovery still passes;
- context tests still pass;
- memory pressure does not worsen materially;
- median latency or memory use improves by a meaningful amount;
- results reproduce in at least three runs.

### P5 STOP

Write an A/B table showing retained and rejected settings, update the ledger, and stop.

---

## P6 — Final production certification

### Goal

Freeze the smallest reliable configuration and provide an operational handoff.

### Required final deliverables

1. `config/local-llm/versions.lock` with exact versions and model identity.
2. Reproducible install/start/stop/status/health commands.
3. Final project-level Kilo configuration.
4. Minimal local executor and analyst agents.
5. Test harness and benchmark corpus.
6. Final metrics and acceptance-gate table.
7. Rollback procedure.
8. Upgrade procedure that requires re-certification.
9. Troubleshooting guide for:
   - model load failure;
   - memory pressure;
   - context overflow;
   - compaction exhaustion;
   - unsupported request parameter;
   - tool call emitted as text;
   - malformed or duplicated tool call;
   - stalled reasoning;
   - cancellation failure;
   - stale PID or occupied port.
10. `docs/local-llm/CERTIFICATION.md` with explicit PASS/FAIL for every gate.

### Production-ready definition

The setup is production-ready for local research only when:

- versions and model revision are pinned;
- server is localhost-only;
- lifecycle scripts are idempotent and safe;
- Kilo limits are explicit and resolved correctly;
- baseline and final test results are reproducible;
- all P4 hard gates pass;
- every retained optimization passed isolated A/B tests;
- context and handoff procedures are documented;
- no agent can place bets or perform financial operations;
- the final Git diff is reviewed and contains no secrets, caches, model weights, runtime logs, or unrelated changes.

### P6 STOP

Present the final summary, file list, exact commands, metrics, remaining risks, and recommended next project phase. Do not begin betting-pipeline integration.

---

## 6. Required agent behavior during every phase

The GPT-5.4 Medium implementation controller must:

1. State the current phase and its acceptance gate before changing files.
2. Inspect before editing.
3. Keep changes small and reviewable.
4. Validate shell, JSON, JSONC, Python, and Markdown files with appropriate tools.
5. Run tests itself; do not merely describe them.
6. Preserve full command output in artifacts while summarizing it in chat.
7. Distinguish verified facts, observed local behavior, and assumptions.
8. Never report success while a required test is skipped.
9. On failure:
   - preserve evidence;
   - identify the narrowest cause;
   - make the smallest fix;
   - rerun the failed test and relevant regressions.
10. Before STOP, perform a final diff review for:
    - accidental secrets;
    - destructive commands;
    - global configuration changes;
    - unsupported flags;
    - missing error handling;
    - unbounded output;
    - missing cleanup;
    - stale documentation;
    - unrelated modifications.

---

## 7. Standard phase report format

Every phase report must contain:

```markdown
# Phase Px Report

## Status
PASS | FAIL | BLOCKED

## Environment fingerprint
- Git commit:
- macOS:
- Apple chip / RAM:
- Kilo version:
- Rapid-MLX version:
- Model alias:
- Resolved repository/revision:

## Files changed

## Commands executed

## Tests and results
| Test | Result | Evidence artifact |
|---|---|---|

## Metrics

## Failures and fixes

## Security and scope review

## Open risks

## Acceptance gate
| Gate | PASS/FAIL | Evidence |
|---|---|---|

## Exact next phase
```

---

## 8. Official sources to re-check during implementation

Use current official sources as the primary authority:

- Rapid-MLX repository and releases: `https://github.com/raullenchai/Rapid-MLX`
- Kilo repository and releases: `https://github.com/Kilo-Org/kilocode`
- Kilo custom model documentation: `https://kilo.ai/docs/code-with-ai/agents/custom-models`
- Kilo context condensing documentation: `https://kilo.ai/docs/customize/context/context-condensing`
- Kilo CLI reference: `https://kilo.ai/docs/code-with-ai/platforms/cli-reference`
- Kilo plugins documentation: `https://kilo.ai/docs/automate/extending/plugins`
- Qwen3.6-35B-A3B model card: `https://huggingface.co/Qwen/Qwen3.6-35B-A3B`

Record the retrieval date and exact release/tag or commit used. Source code and installed `--help` output override stale secondary tutorials.
