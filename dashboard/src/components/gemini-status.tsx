import { Sparkles } from "lucide-react";
import { getGeminiConfig } from "@/lib/data";

export function GeminiStatus() {
  const config = getGeminiConfig();

  return (
    <div className="rounded-xl border border-border-card bg-bg-card p-5">
      <div className="flex items-center gap-2 mb-3">
        <Sparkles className="h-4 w-4 text-purple-400" />
        <h3 className="text-sm font-semibold text-text-primary">
          Gemini Integration
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
            {config.enabled ? "Active" : "Not Configured"}
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
              <span className="text-text-secondary">Daily Limit</span>
              <span className="text-text-primary">
                {config.dailyLimit.toLocaleString()} req
              </span>
            </div>
            <div className="mt-3 pt-3 border-t border-border-card">
              <p className="text-xs text-text-secondary">
                Feature flags: --use-gemini, --news, --gemini
              </p>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
