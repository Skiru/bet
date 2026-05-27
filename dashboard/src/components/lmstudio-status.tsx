import { Sparkles } from "lucide-react";
import { getLMStudioConfig } from "@/lib/data";

export function LMStudioStatus() {
  const config = getLMStudioConfig();

  return (
    <div className="rounded-xl border border-border-card bg-bg-card p-5">
      <div className="flex items-center gap-2 mb-3">
        <Sparkles className="h-4 w-4 text-purple-400" />
        <h3 className="text-sm font-semibold text-text-primary">
          LM Studio Integration
        </h3>
      </div>
      <div className="space-y-2 text-sm">
        <div className="flex items-center justify-between">
          <span className="text-text-secondary">Status</span>
          <span
            className={
              config.enabled ? "text-success font-medium" : "text-text-secondary"
            }
          >
            {config.enabled ? "Configured" : "Not Configured"}
          </span>
        </div>
        {config.enabled && (
          <>
            <div className="flex items-center justify-between">
              <span className="text-text-secondary">Model</span>
              <span className="text-text-primary font-mono text-xs">
                {config.model}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-text-secondary">Endpoint</span>
              <span className="text-text-primary font-mono text-xs">
                {config.baseUrl}
              </span>
            </div>
            <div className="mt-3 pt-3 border-t border-border-card">
              <p className="text-xs text-text-secondary">
                Roo Code + Continue.dev connect to this endpoint for agentic chat and autocomplete.
              </p>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
