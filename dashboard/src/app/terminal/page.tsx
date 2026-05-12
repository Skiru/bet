import { Terminal as TerminalIcon } from "lucide-react";

export default function TerminalPage() {
  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold text-white mb-8">Pipeline Terminal</h1>

      <div className="rounded-xl border border-border-card bg-bg-darkest p-6 font-mono">
        <div className="flex items-center gap-2 mb-4 pb-3 border-b border-border-card">
          <TerminalIcon className="h-4 w-4 text-success" />
          <span className="text-xs text-text-secondary">
            bet-orchestrator terminal
          </span>
        </div>
        <div className="space-y-1 text-sm text-text-secondary">
          <p>
            <span className="text-success">$</span> Pipeline terminal ready.
          </p>
          <p>
            <span className="text-success">$</span> Click &quot;Run
            Pipeline&quot; to start orchestration.
          </p>
          <p className="animate-pulse text-text-primary">▌</p>
        </div>
      </div>
    </div>
  );
}
