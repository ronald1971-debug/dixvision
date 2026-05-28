import { CorrelationMatrix } from "@/widgets/risk/CorrelationMatrix";
import { GreeksPanel } from "@/widgets/risk/GreeksPanel";
import { LiqCalc } from "@/widgets/risk/LiqCalc";
import { OptionsChain } from "@/widgets/risk/OptionsChain";
import { ScenarioBook } from "@/widgets/risk/ScenarioBook";
import { WidgetSlot } from "@/components/WidgetSlot";

export function RiskPage() {
  return (
    <section className="flex h-full flex-col">
      <header className="mb-3 flex items-baseline justify-between">
        <div>
          <h1 className="text-lg font-semibold tracking-tight">
            Risk &amp; Greeks{" "}
            <span className="ml-2 rounded border border-border bg-bg px-2 py-0.5 font-mono text-[11px] uppercase tracking-widest text-slate-400">
              CROSS-ASSET
            </span>
          </h1>
          <p className="mt-1 text-xs text-slate-400">
            Option chain, portfolio Greeks, liquidation distance,
            scenario book, and correlation matrix. All widgets feed the
            governance promotion gates and are subject to the same
            kill-switch as the execution path.
          </p>
        </div>
      </header>
      <div className="grid flex-1 grid-cols-1 gap-3 overflow-auto pb-6 md:grid-cols-2 xl:grid-cols-6">
        <WidgetSlot widgetKey="risk:OptionsChain" className="md:col-span-2 xl:col-span-3 xl:row-span-2">
          <OptionsChain />
        </WidgetSlot>
        <WidgetSlot widgetKey="risk:GreeksPanel" className="xl:col-span-3">
          <GreeksPanel />
        </WidgetSlot>
        <WidgetSlot widgetKey="risk:LiqCalc" className="xl:col-span-3">
          <LiqCalc />
        </WidgetSlot>
        <WidgetSlot widgetKey="risk:ScenarioBook" className="md:col-span-2 xl:col-span-3">
          <ScenarioBook />
        </WidgetSlot>
        <WidgetSlot widgetKey="risk:CorrelationMatrix" className="md:col-span-2 xl:col-span-3">
          <CorrelationMatrix />
        </WidgetSlot>
      </div>
    </section>
  );
}
