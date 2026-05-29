import { CognitiveHealthStrip } from "@/components/CognitiveHealthStrip";
import { DyonArchitectureStream } from "@/widgets/DyonArchitectureStream";
import { DyonLearningMode } from "@/widgets/DyonLearningMode";
import { DyonWorkspace } from "@/widgets/DyonWorkspace";
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
            repository graph · drift monitor · dead code · mutation queue · sandbox ·
            governance approval · patch validation — live engineering workspace
          </p>
        </div>
        <CognitiveHealthStrip />
      </header>
      {/* Primary: 8-panel engineering workspace */}
      <WidgetSlot widgetKey="dyon:Workspace" className="min-h-0 flex-1">
        <DyonWorkspace />
      </WidgetSlot>
      {/* Secondary: hazard journal + architecture stream */}
      <section className="grid h-64 shrink-0 grid-cols-1 gap-3 xl:grid-cols-2">
        <WidgetSlot widgetKey="dyon:DyonLearningMode" className="h-full">
          <DyonLearningMode />
        </WidgetSlot>
        <WidgetSlot widgetKey="dyon:ArchitectureStream" className="h-full">
          <DyonArchitectureStream />
        </WidgetSlot>
      </section>
    </div>
  );
}
