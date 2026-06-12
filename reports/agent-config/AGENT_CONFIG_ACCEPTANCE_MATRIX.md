# Phase 4A Acceptance Matrix

| Gate | Status | Evidence | Justification |
|---|---|---|---|
| Active configuration surfaces inventoried | PASS | `reports/agent-config/ACTIVE_SURFACE_INVENTORY.md` | Auto-loaded project and global override surfaces enumerated |
| Historical `.implementation` files not treated as active | PASS | `reports/agent-config/ACTIVE_SURFACE_INVENTORY.md` | Non-active locations explicitly excluded |
| Broken DB tool removed from active runtime | PASS | `archive/deferred-kilo-tools/bet_sqlite_query.ts` | No longer present under `.kilo/tool/` |
| Database capability correctly marked DEFERRED | PASS | `reports/agent-config/CAPABILITY_MATRIX.md` | Deferred and inactive by phase design |
| Real scripts correctly marked DEFERRED | PASS | `reports/agent-config/CAPABILITY_MATRIX.md` | Only fixture executor remains active |
| Fixture executor unchanged | PASS | `config/bet-script-operations.json` | Manifest still fixture-only |
| Web and MCP disabled | PASS | `kilo.jsonc`, `reports/agent-config/diagnostics/phase4a-20260612T111336Z/phase4a-mcp-list.txt`, `.kilo/agents/*.md` | Canonical agents deny web/MCP; all MCP servers disabled |
| Artifact writer schema fixed | PASS | `.kilo/tool/bet_artifact_write.ts` | Uses `tool.schema.enum(["markdown", "json"])` |
| Artifact writer loads in fresh runtime | PASS | `reports/agent-config/diagnostics/phase4a-20260612T111336Z/phase4a-config-check.txt` | Fresh `kilo config check` succeeds with no schema warning |
| Artifact writer mechanical tests pass | PASS | `reports/agent-config/artifact-writer-qualification-20260612T111336Z.json` | 21/21 qualification checks passed |
| Artifact writer path and symlink protections pass | PASS | `reports/agent-config/artifact-writer-qualification-20260612T111336Z.json` | Traversal, encoded traversal, absolute path, and symlink escape rejected |
| Artifact writer CAS tests pass | PASS | `reports/agent-config/artifact-writer-qualification-20260612T111336Z.json` | Missing hash, wrong hash, and correct hash overwrite cases validated |
| Artifact writer cancellation and concurrency tests pass | PASS | `reports/agent-config/artifact-writer-qualification-20260612T111336Z.json` | Cancelled write leaves no artifact; only one concurrent create succeeds |
| Direct-write bypass absent | PASS | `reports/agent-config/diagnostics/phase4a-20260612T111336Z/phase4a-agent-orchestrator.txt`, `reports/agent-config/diagnostics/phase4a-20260612T111336Z/phase4a-agent-builder.txt` | Resolved tools show `edit/write=false` and `bet_artifact_write=true` only where expected |
| Zero ask permissions | PASS | `reports/agent-config/diagnostics/phase4a-20260612T111336Z/phase4a-perms.txt` | Phase 4A validator reports `FAIL: 0` |
| Question denied | PASS | `reports/agent-config/diagnostics/phase4a-20260612T111336Z/phase4a-perms.txt` | All 13 canonical betting agents deny `question` |
| Unknown tools fail closed | PASS | `reports/agent-config/diagnostics/phase4a-20260612T111336Z/phase4a-perms.txt` | Validator enforces denied web/MCP surfaces and no fallback broadening |
| Orchestrator task allowlist exact | PASS | `.kilo/agents/bet-orchestrator.md`, `reports/agent-config/diagnostics/phase4a-20260612T111336Z/phase4a-perms.txt` | Exactly 12 specialists allowed |
| Specialists cannot delegate | PASS | `.kilo/agents/*.md`, `reports/agent-config/diagnostics/phase4a-20260612T111336Z/phase4a-perms.txt` | All specialists have `task: deny` |
| All 13 agents valid | PASS | `reports/agent-config/diagnostics/phase4a-20260612T111336Z/phase4a-static.txt`, `reports/agent-config/diagnostics/phase4a-20260612T111336Z/phase4a-agent-count.txt` | Static validator passes; diagnostics enumerate 13 canonical agents |
| Skills valid | PASS | `reports/agent-config/diagnostics/phase4a-20260612T111336Z/phase4a-static.txt` | Static validator confirms 2 project skills |
| Fresh resolved diagnostics pass | PASS | `reports/agent-config/diagnostics/phase4a-20260612T111336Z/phase4a-config-check.txt`, `reports/agent-config/diagnostics/phase4a-20260612T111336Z/phase4a-debug-paths.txt`, `reports/agent-config/diagnostics/phase4a-20260612T111336Z/phase4a-mcp-list.txt`, `reports/agent-config/diagnostics/phase4a-20260612T111336Z/phase4a-agent-orchestrator.txt`, `reports/agent-config/diagnostics/phase4a-20260612T111336Z/phase4a-agent-builder.txt`, `reports/agent-config/diagnostics/phase4a-20260612T111336Z/phase4a-agent-scanner.txt`, `reports/agent-config/diagnostics/phase4a-20260612T111336Z/phase4a-agent-engineer.txt` | Fresh startup/config/paths/MCP diagnostics succeeded and resolved betting-agent tools match Phase 4A scope |
| Rapid-MLX and Phase 3 fingerprint unchanged | PASS | `kilo.jsonc`, `reports/agent-config/STATE.md` | Model route unchanged; no runtime-model drift introduced |
