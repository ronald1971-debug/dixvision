import { DrawdownCurve } from "@/widgets/positions/DrawdownCurve";
import { ExposureBreakdown } from "@/widgets/positions/ExposureBreakdown";
import { FillsHistory } from "@/widgets/positions/FillsHistory";
import { FundingHistory } from "@/widgets/positions/FundingHistory";
import { IntradayPnLCurve } from "@/widgets/positions/IntradayPnLCurve";
import { OpenOrdersPanel } from "@/widgets/positions/OpenOrdersPanel";
import { RiskParityAllocator } from "@/widgets/positions/RiskParityAllocator";
import { WidgetSlot } from "@/components/WidgetSlot";

export function PositionsPage() {
  return (
    <div className="grid h-full grid-cols-1 gap-3 overflow-auto p-3 lg:grid-cols-2 xl:grid-cols-3">
      <WidgetSlot widgetKey="positions:IntradayPnLCurve" className="min-h-[320px] xl:col-span-2">
        <IntradayPnLCurve />
      </WidgetSlot>
      <WidgetSlot widgetKey="positions:DrawdownCurve" className="min-h-[320px]">
        <DrawdownCurve />
      </WidgetSlot>
      <WidgetSlot widgetKey="positions:OpenOrdersPanel" className="min-h-[360px] xl:col-span-2">
        <OpenOrdersPanel />
      </WidgetSlot>
      <WidgetSlot widgetKey="positions:ExposureBreakdown" className="min-h-[360px]">
        <ExposureBreakdown />
      </WidgetSlot>
      <WidgetSlot widgetKey="positions:FillsHistory" className="min-h-[360px] xl:col-span-2">
        <FillsHistory />
      </WidgetSlot>
      <WidgetSlot widgetKey="positions:FundingHistory" className="min-h-[360px]">
        <FundingHistory />
      </WidgetSlot>
      <WidgetSlot widgetKey="positions:RiskParityAllocator" className="min-h-[360px] xl:col-span-3">
        <RiskParityAllocator />
      </WidgetSlot>
    </div>
  );
}
