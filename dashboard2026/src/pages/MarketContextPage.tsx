import { FearGreed } from "@/widgets/market/FearGreed";
import { HotMovers } from "@/widgets/market/HotMovers";
import { IVSurface } from "@/widgets/market/IVSurface";
import { LongShortRatio } from "@/widgets/market/LongShortRatio";
import { OpenInterestPanel } from "@/widgets/market/OpenInterestPanel";
import { PutCallRatio } from "@/widgets/market/PutCallRatio";
import { SentimentGauge } from "@/widgets/market/SentimentGauge";
import { Watchlist } from "@/widgets/market/Watchlist";
import { WidgetSlot } from "@/components/WidgetSlot";

export function MarketContextPage() {
  return (
    <div className="space-y-3">
      <header className="rounded border border-border bg-surface px-3 py-2">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-200">
          Market context
        </h2>
        <p className="mt-0.5 text-[11px] text-slate-500">
          watchlist · movers · sentiment composite · F&amp;G · long/short ·
          OI · put/call · IV surface — all read-only, all SCVS-registered.
        </p>
      </header>
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2 xl:grid-cols-3">
        <WidgetSlot widgetKey="market:Watchlist" className="min-h-[360px] xl:col-span-2">
          <Watchlist />
        </WidgetSlot>
        <WidgetSlot widgetKey="market:HotMovers" className="min-h-[360px]">
          <HotMovers />
        </WidgetSlot>
        <WidgetSlot widgetKey="market:SentimentGauge" className="min-h-[300px]">
          <SentimentGauge />
        </WidgetSlot>
        <WidgetSlot widgetKey="market:FearGreed" className="min-h-[300px]">
          <FearGreed />
        </WidgetSlot>
        <WidgetSlot widgetKey="market:PutCallRatio" className="min-h-[300px]">
          <PutCallRatio />
        </WidgetSlot>
        <WidgetSlot widgetKey="market:LongShortRatio" className="min-h-[280px]">
          <LongShortRatio />
        </WidgetSlot>
        <WidgetSlot widgetKey="market:OpenInterestPanel" className="min-h-[280px]">
          <OpenInterestPanel />
        </WidgetSlot>
        <WidgetSlot widgetKey="market:IVSurface" className="min-h-[320px] xl:col-span-3">
          <IVSurface />
        </WidgetSlot>
      </div>
    </div>
  );
}
