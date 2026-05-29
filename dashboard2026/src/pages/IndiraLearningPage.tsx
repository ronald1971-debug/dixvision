import { CognitiveHealthStrip } from "@/components/CognitiveHealthStrip";
import { IndiraCognitiveStream } from "@/widgets/IndiraCognitiveStream";
import { IndiraConsciousnessPanel } from "@/widgets/IndiraConsciousnessPanel";
import { IndiraLearningMode } from "@/widgets/IndiraLearningMode";
import { WidgetSlot } from "@/components/WidgetSlot";

export function IndiraLearningPage() {
  return (
    <div className="flex h-full flex-col gap-3 overflow-hidden">
      <header className="flex flex-col gap-1.5">
        <div className="flex items-baseline gap-3">
          <h1 className="text-base font-semibold tracking-tight">
            Indira · Cognitive Intelligence
          </h1>
          <p className="text-[12px] text-slate-500">
            consciousness stream · causal chains · behavioral clusters · observation sessions ·
            philosophy / trader feed / proposals — governance-gated
          </p>
        </div>
        <CognitiveHealthStrip />
      </header>
      {/* Primary: consciousness stream with causal / cluster / session tabs */}
      <WidgetSlot widgetKey="indira:ConsciousnessPanel" className="min-h-0 flex-1">
        <IndiraConsciousnessPanel />
      </WidgetSlot>
      {/* Secondary: learning mode + SSE cognitive stream */}
      <section className="grid h-64 shrink-0 grid-cols-1 gap-3 xl:grid-cols-2">
        <WidgetSlot widgetKey="indira:IndiraLearningMode" className="h-full">
          <IndiraLearningMode />
        </WidgetSlot>
        <WidgetSlot widgetKey="indira:CognitiveStream" className="h-full">
          <IndiraCognitiveStream />
        </WidgetSlot>
      </section>
    </div>
  );
}
