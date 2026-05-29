import { CognitiveHealthStrip } from "@/components/CognitiveHealthStrip";
import { DyonArchitectureStream } from "@/widgets/DyonArchitectureStream";
import { DyonLearningMode } from "@/widgets/DyonLearningMode";
import { WidgetSlot } from "@/components/WidgetSlot";

export function DyonLearningPage() {
  return (
    <div className="flex h-full flex-col gap-3 overflow-hidden">
      <header className="flex flex-col gap-1.5">
        <div className="flex items-baseline gap-3">
          <h1 className="text-base font-semibold tracking-tight">
            Dyon · Engineering Intelligence
          </h1>
          <p className="text-[12px] text-slate-500">
            hazard journal / patch proposals / sandbox / promotions ·
            topology / drift / anomalies / repair stream — governance-gated
          </p>
        </div>
        <CognitiveHealthStrip />
      </header>
      <section className="grid min-h-0 flex-1 grid-cols-1 gap-3 xl:grid-cols-2">
        <WidgetSlot widgetKey="dyon:DyonLearningMode" className="min-h-[400px]">
          <DyonLearningMode />
        </WidgetSlot>
        <WidgetSlot widgetKey="dyon:ArchitectureStream" className="min-h-[400px]">
          <DyonArchitectureStream />
        </WidgetSlot>
      </section>
    </div>
  );
}
