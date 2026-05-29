import { CognitiveHealthStrip } from "@/components/CognitiveHealthStrip";
import { IndiraCognitiveStream } from "@/widgets/IndiraCognitiveStream";
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
            philosophy / trader feed / proposals / shadow eval / corpus ·
            thought / belief / memory / causal stream — governance-gated
          </p>
        </div>
        <CognitiveHealthStrip />
      </header>
      <section className="grid min-h-0 flex-1 grid-cols-1 gap-3 xl:grid-cols-2">
        <WidgetSlot widgetKey="indira:IndiraLearningMode" className="min-h-[400px]">
          <IndiraLearningMode />
        </WidgetSlot>
        <WidgetSlot widgetKey="indira:CognitiveStream" className="min-h-[400px]">
          <IndiraCognitiveStream />
        </WidgetSlot>
      </section>
    </div>
  );
}
