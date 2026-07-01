// Provenance-only metadata retained to document the duplicate-tool repair.
// This file must not register the bet_artifact_write tool.

export const BET_ARTIFACT_WRITE_PLUGIN_PROVENANCE = {
  tool_name: "bet_artifact_write",
  registers_tool_name: false,
  status: "disabled_duplicate_registration",
  previous_plugin_version: "pipeline-runs-allowlist-a1a00ff",
  active_source: ".kilo/tool/bet_artifact_write.ts",
  single_source_strategy: "STANDALONE_TOOL_SINGLE_SOURCE",
  supports_reports_pipeline_runs: true,
  allowed_report_roots: ["reports/betting-demo", "reports/betting", "reports/pipeline_runs"],
} as const
