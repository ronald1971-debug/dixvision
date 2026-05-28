import { ExchangeFlows } from "@/widgets/onchain/ExchangeFlows";
import { OpenInterestMatrix } from "@/widgets/onchain/OpenInterestMatrix";
import { StablecoinSupply } from "@/widgets/onchain/StablecoinSupply";
import { TVLDashboard } from "@/widgets/onchain/TVLDashboard";
import { WhaleWatcher } from "@/widgets/onchain/WhaleWatcher";
import { WidgetSlot } from "@/components/WidgetSlot";

export function OnChainPage() {
  return (
    <div className="grid h-full grid-cols-1 gap-3 overflow-auto p-3 lg:grid-cols-2 xl:grid-cols-3">
      <WidgetSlot widgetKey="onchain:WhaleWatcher" className="min-h-[360px] xl:col-span-2">
        <WhaleWatcher />
      </WidgetSlot>
      <WidgetSlot widgetKey="onchain:ExchangeFlows" className="min-h-[360px]">
        <ExchangeFlows />
      </WidgetSlot>
      <WidgetSlot widgetKey="onchain:StablecoinSupply" className="min-h-[360px]">
        <StablecoinSupply />
      </WidgetSlot>
      <WidgetSlot widgetKey="onchain:TVLDashboard" className="min-h-[360px] xl:col-span-2">
        <TVLDashboard />
      </WidgetSlot>
      <WidgetSlot widgetKey="onchain:OpenInterestMatrix" className="min-h-[360px] xl:col-span-3">
        <OpenInterestMatrix />
      </WidgetSlot>
    </div>
  );
}
