import { ApprovalQueueWidget } from "@/widgets/governance/ApprovalQueueWidget";
import { AuditLedgerViewer } from "@/widgets/governance/AuditLedgerViewer";
import { DriftOraclePanel } from "@/widgets/governance/DriftOraclePanel";
import { HazardMonitorGrid } from "@/widgets/governance/HazardMonitorGrid";
import { PromotionGatesPanel } from "@/widgets/governance/PromotionGatesPanel";
import { SCVSLivenessGrid } from "@/widgets/governance/SCVSLivenessGrid";
import { StrategyRegistryFSM } from "@/widgets/governance/StrategyRegistryFSM";
import { WidgetSlot } from "@/components/WidgetSlot";

export function GovernancePage() {
  return (
    <section className="flex h-full flex-col">
      <header className="mb-3">
        <h1 className="text-lg font-semibold tracking-tight">
          Governance
        </h1>
        <p className="mt-1 text-xs text-slate-400">
          Six Tier-1 surfaces: promotion gates, drift oracle, operator
          approval queue, audit ledger / DecisionTrace browser,
          strategy lifecycle FSM, SCVS source liveness + hazard
          monitor. All read directly from the canonical ledger; the
          decision buttons in the approval queue route back through
          the ledger so every operator action is itself recorded.
        </p>
      </header>
      <div className="grid flex-1 grid-cols-1 gap-3 overflow-auto pb-6 lg:grid-cols-2 xl:grid-cols-3">
        <WidgetSlot widgetKey="governance:PromotionGatesPanel" className="min-h-[320px]">
          <PromotionGatesPanel />
        </WidgetSlot>
        <WidgetSlot widgetKey="governance:DriftOraclePanel" className="min-h-[320px]">
          <DriftOraclePanel />
        </WidgetSlot>
        <WidgetSlot widgetKey="governance:StrategyRegistryFSM" className="min-h-[320px]">
          <StrategyRegistryFSM />
        </WidgetSlot>
        <WidgetSlot widgetKey="governance:ApprovalQueueWidget" className="min-h-[320px]">
          <ApprovalQueueWidget />
        </WidgetSlot>
        <WidgetSlot widgetKey="governance:AuditLedgerViewer" className="min-h-[320px] lg:col-span-2 xl:col-span-2">
          <AuditLedgerViewer />
        </WidgetSlot>
        <WidgetSlot widgetKey="governance:SCVSLivenessGrid" className="min-h-[320px] lg:col-span-2 xl:col-span-2">
          <SCVSLivenessGrid />
        </WidgetSlot>
        <WidgetSlot widgetKey="governance:HazardMonitorGrid" className="min-h-[320px]">
          <HazardMonitorGrid />
        </WidgetSlot>
      </div>
    </section>
  );
}
