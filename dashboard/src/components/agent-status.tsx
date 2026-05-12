export function AgentStatus() {
  return (
    <div className="rounded-xl border border-border-card bg-bg-card p-5">
      <h2 className="text-lg font-semibold text-text-primary mb-4">
        Agent Status
      </h2>
      <div className="flex items-center gap-3">
        <span className="relative flex h-3 w-3">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-success opacity-75" />
          <span className="relative inline-flex h-3 w-3 rounded-full bg-success" />
        </span>
        <span className="text-sm font-medium text-text-primary">
          Ready to Orchestrate
        </span>
      </div>
      <p className="mt-3 text-xs text-text-secondary">
        All agents idle. Pipeline awaiting manual trigger.
      </p>
    </div>
  );
}
