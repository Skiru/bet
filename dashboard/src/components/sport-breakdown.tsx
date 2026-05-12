import { BarChart3 } from "lucide-react";
import { getSportBreakdown } from "@/lib/data";

const SPORT_COLORS: Record<string, string> = {
  football: "bg-green-500",
  basketball: "bg-orange-500",
  tennis: "bg-yellow-500",
  hockey: "bg-blue-500",
  volleyball: "bg-purple-500",
};

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

export function SportBreakdown() {
  const breakdown = getSportBreakdown(today());
  const total = breakdown.reduce((sum, s) => sum + s.count, 0);

  return (
    <div className="rounded-xl border border-border-card bg-bg-card p-5">
      <div className="flex items-center gap-2 mb-3">
        <BarChart3 className="h-4 w-4 text-blue-400" />
        <h3 className="text-sm font-semibold text-text-primary">
          Events by Sport
        </h3>
      </div>
      {breakdown.length === 0 ? (
        <p className="text-sm text-text-secondary">No scan data for today</p>
      ) : (
        <div className="space-y-2">
          {breakdown.map((s) => {
            const pct = total > 0 ? (s.count / total) * 100 : 0;
            const color = SPORT_COLORS[s.sport] ?? "bg-gray-500";
            return (
              <div key={s.sport}>
                <div className="flex items-center justify-between text-sm mb-1">
                  <span className="text-text-secondary capitalize">
                    {s.sport}
                  </span>
                  <span className="text-text-primary font-medium">
                    {s.count}
                  </span>
                </div>
                <div className="h-1.5 rounded-full bg-bg-darkest overflow-hidden">
                  <div
                    className={`h-full rounded-full ${color}`}
                    style={{ width: `${pct}%` }}
                  />
                </div>
              </div>
            );
          })}
          <div className="pt-2 border-t border-border-card text-xs text-text-secondary">
            Total: {total} unique events
          </div>
        </div>
      )}
    </div>
  );
}
