import { Backtester } from "@/widgets/testing/Backtester";
import { CalibrationReliability } from "@/widgets/testing/CalibrationReliability";
import { ChampionChallenger } from "@/widgets/testing/ChampionChallenger";
import { EquityCurveStudio } from "@/widgets/testing/EquityCurveStudio";
import { ForwardTester } from "@/widgets/testing/ForwardTester";
import { MonteCarloPaths } from "@/widgets/testing/MonteCarloPaths";
import { ParameterSweep } from "@/widgets/testing/ParameterSweep";
import { RegimeShiftBoard } from "@/widgets/testing/RegimeShiftBoard";
import { ReplayHarness } from "@/widgets/testing/ReplayHarness";
import { WalkForwardHarness } from "@/widgets/testing/WalkForwardHarness";
import { WidgetSlot } from "@/components/WidgetSlot";

export function TestingPage() {
  return (
    <section className="flex h-full flex-col">
      <header className="mb-3 flex items-baseline justify-between">
        <div>
          <h1 className="text-lg font-semibold tracking-tight">
            Testing &amp; Evaluation{" "}
            <span className="ml-2 rounded border border-border bg-bg px-2 py-0.5 font-mono text-[11px] uppercase tracking-widest text-slate-400">
              LAB
            </span>
          </h1>
          <p className="mt-1 text-xs text-slate-400">
            Backtest, forward-test, walk-forward, replay, and regime-shift
            harnesses. Every run is governed by the same audit ledger and
            promotion gates as live trading — there is no untracked
            evaluation surface.
          </p>
        </div>
      </header>
      <div className="flex-1 overflow-auto pb-6">
        <div className="grid gap-3 lg:grid-cols-2">
          <WidgetSlot widgetKey="testing:Backtester" className="lg:col-span-2">
            <Backtester />
          </WidgetSlot>
          <WidgetSlot widgetKey="testing:EquityCurveStudio" className="min-h-[360px] lg:col-span-2">
            <EquityCurveStudio />
          </WidgetSlot>
          <WidgetSlot widgetKey="testing:ChampionChallenger" className="min-h-[360px]">
            <ChampionChallenger />
          </WidgetSlot>
          <WidgetSlot widgetKey="testing:CalibrationReliability" className="min-h-[360px]">
            <CalibrationReliability />
          </WidgetSlot>
          <WidgetSlot widgetKey="testing:ParameterSweep" className="min-h-[360px]">
            <ParameterSweep />
          </WidgetSlot>
          <WidgetSlot widgetKey="testing:MonteCarloPaths" className="min-h-[360px]">
            <MonteCarloPaths />
          </WidgetSlot>
          <WidgetSlot widgetKey="testing:ForwardTester">
            <ForwardTester />
          </WidgetSlot>
          <WidgetSlot widgetKey="testing:WalkForwardHarness">
            <WalkForwardHarness />
          </WidgetSlot>
          <WidgetSlot widgetKey="testing:ReplayHarness">
            <ReplayHarness />
          </WidgetSlot>
          <WidgetSlot widgetKey="testing:RegimeShiftBoard">
            <RegimeShiftBoard />
          </WidgetSlot>
        </div>
      </div>
    </section>
  );
}
