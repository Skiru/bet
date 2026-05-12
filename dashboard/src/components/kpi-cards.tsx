import { Wallet, Radar, FileStack, Activity } from "lucide-react";
import {
  getBankroll,
  getEventsScanned,
  getActiveCoupons,
  getPipelineStatus,
} from "@/lib/data";

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

export async function KpiCards() {
  const bankroll = getBankroll();
  const eventsScanned = getEventsScanned(today());
  const activeCoupons = getActiveCoupons();
  const pipelineStatus = getPipelineStatus();

  const cards = [
    {
      label: "Bankroll PLN",
      value: `${bankroll.toFixed(2)}`,
      icon: Wallet,
      color: "text-accent",
    },
    {
      label: "Events Scanned",
      value: `${eventsScanned}`,
      icon: Radar,
      color: "text-blue-400",
    },
    {
      label: "Active Coupons",
      value: `${activeCoupons}`,
      icon: FileStack,
      color: "text-amber-400",
    },
    {
      label: "Pipeline Status",
      value: pipelineStatus,
      icon: Activity,
      color:
        pipelineStatus === "Running"
          ? "text-success"
          : pipelineStatus === "Complete"
            ? "text-success"
            : "text-text-secondary",
    },
  ];

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {cards.map((card) => (
        <div
          key={card.label}
          className="rounded-xl border border-border-card bg-bg-card p-5"
        >
          <div className="flex items-center justify-between">
            <span className="text-sm text-text-secondary">{card.label}</span>
            <card.icon className={`h-5 w-5 ${card.color}`} />
          </div>
          <p className="mt-2 text-2xl font-bold text-white">{card.value}</p>
        </div>
      ))}
    </div>
  );
}
