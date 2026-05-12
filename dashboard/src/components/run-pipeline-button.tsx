"use client";

import { Play } from "lucide-react";

export function RunPipelineButton() {
  return (
    <button
      onClick={() => alert("Pipeline trigger coming soon — use the Copilot agent to orchestrate.")}
      className="flex items-center gap-2 rounded-lg bg-success px-4 py-2 text-sm font-semibold text-white shadow-md transition-colors hover:bg-success/85 active:bg-success/70"
    >
      <Play className="h-4 w-4" />
      Run Pipeline
    </button>
  );
}
