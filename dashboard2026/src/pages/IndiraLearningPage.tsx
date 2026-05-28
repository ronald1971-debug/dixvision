import { IndiraLearningMode } from "@/widgets/IndiraLearningMode";
import { WidgetSlot } from "@/components/WidgetSlot";

export function IndiraLearningPage() {
  return (
    <div className="flex h-full flex-col gap-3">
      <header className="flex items-baseline gap-3">
        <h1 className="text-base font-semibold tracking-tight">
          Indira · Learning Mode
        </h1>
        <p className="text-[12px] text-slate-500">
          philosophy library / trader feed / proposals / shadow eval / corpus —
          governance-gated
        </p>
      </header>
      <section className="flex-1">
        <WidgetSlot widgetKey="indira:IndiraLearningMode">
          <IndiraLearningMode />
        </WidgetSlot>
      </section>
    </div>
  );
}
