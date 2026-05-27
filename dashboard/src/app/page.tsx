import { KpiCards } from "@/components/kpi-cards";
import { CouponViewer } from "@/components/coupon-viewer";
import { AgentStatus } from "@/components/agent-status";
import { RunPipelineButton } from "@/components/run-pipeline-button";
import { SportBreakdown } from "@/components/sport-breakdown";
import { LMStudioStatus } from "@/components/lmstudio-status";

export default function DashboardPage() {
  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-8">
        <h1 className="text-2xl font-bold text-white">Dashboard</h1>
        <RunPipelineButton />
      </div>

      <div className="space-y-6">
        <KpiCards />

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          <div className="lg:col-span-2">
            <CouponViewer />
          </div>
          <div className="space-y-6">
            <AgentStatus />
            <LMStudioStatus />
            <SportBreakdown />
          </div>
        </div>
      </div>
    </div>
  );
}
