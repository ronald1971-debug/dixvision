import { AggressorRatio } from "@/widgets/orderflow/AggressorRatio";
import { CVDChart } from "@/widgets/orderflow/CVDChart";
import { DOMClickLadder } from "@/widgets/orderflow/DOMClickLadder";
import { FootprintChart } from "@/widgets/orderflow/FootprintChart";
import { LiquidityHeatmap } from "@/widgets/orderflow/LiquidityHeatmap";
import { SweepIcebergMonitor } from "@/widgets/orderflow/SweepIcebergMonitor";
import { WidgetSlot } from "@/components/WidgetSlot";

export function OrderFlowPage() {
  return (
    <div className="flex h-full flex-col gap-3 overflow-auto p-3">
      <header className="rounded border border-border bg-surface px-3 py-2">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-200">
          Order-flow edge
        </h2>
        <p className="mt-1 text-[11px] leading-snug text-slate-400">
          Bookmap-class depth + footprint + CVD + aggressor ratio + sweep /
          iceberg / block detector + click-to-stage DOM ladder. All staged
          orders pass through the operator-approval edge (INV-72) before the
          execution engine sees them.
        </p>
      </header>
      <div className="grid grid-cols-1 gap-3 xl:grid-cols-3">
        <WidgetSlot widgetKey="orderflow:LiquidityHeatmap" className="xl:col-span-2 h-[420px]">
          <LiquidityHeatmap />
        </WidgetSlot>
        <WidgetSlot widgetKey="orderflow:DOMClickLadder" className="h-[420px]">
          <DOMClickLadder />
        </WidgetSlot>
        <WidgetSlot widgetKey="orderflow:FootprintChart" className="h-[320px]">
          <FootprintChart />
        </WidgetSlot>
        <WidgetSlot widgetKey="orderflow:CVDChart" className="h-[320px]">
          <CVDChart />
        </WidgetSlot>
        <WidgetSlot widgetKey="orderflow:AggressorRatio" className="h-[320px]">
          <AggressorRatio />
        </WidgetSlot>
        <WidgetSlot widgetKey="orderflow:SweepIcebergMonitor" className="h-[320px] xl:col-span-3">
          <SweepIcebergMonitor />
        </WidgetSlot>
      </div>
    </div>
  );
}
