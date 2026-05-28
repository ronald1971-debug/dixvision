import { AlgoOrderBuilder } from "@/widgets/trading/AlgoOrderBuilder";
import { BasketOrderEditor } from "@/widgets/trading/BasketOrderEditor";
import { ConditionalBracketBuilder } from "@/widgets/trading/ConditionalBracketBuilder";
import { OrderHotkeysPanel } from "@/widgets/trading/OrderHotkeysPanel";
import { PreTradeSlippageSim } from "@/widgets/trading/PreTradeSlippageSim";
import { WidgetSlot } from "@/components/WidgetSlot";

export function TradingPage() {
  return (
    <div className="grid h-full grid-cols-1 gap-3 overflow-auto p-3 lg:grid-cols-2 xl:grid-cols-3">
      <WidgetSlot widgetKey="trading:AlgoOrderBuilder" className="min-h-[360px] xl:col-span-2">
        <AlgoOrderBuilder />
      </WidgetSlot>
      <WidgetSlot widgetKey="trading:ConditionalBracketBuilder" className="min-h-[360px]">
        <ConditionalBracketBuilder />
      </WidgetSlot>
      <WidgetSlot widgetKey="trading:BasketOrderEditor" className="min-h-[360px] xl:col-span-2">
        <BasketOrderEditor />
      </WidgetSlot>
      <WidgetSlot widgetKey="trading:PreTradeSlippageSim" className="min-h-[360px]">
        <PreTradeSlippageSim />
      </WidgetSlot>
      <WidgetSlot widgetKey="trading:OrderHotkeysPanel" className="min-h-[360px] xl:col-span-3">
        <OrderHotkeysPanel />
      </WidgetSlot>
    </div>
  );
}
