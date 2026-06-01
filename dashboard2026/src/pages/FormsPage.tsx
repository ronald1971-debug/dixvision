import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Layers,
  TrendingUp,
  TrendingDown,
  Activity,
  XCircle,
  Pause,
  Play,
} from "lucide-react";

import {
  fetchTradingForms,
  fetchOpenOrders,
  fetchRecentFills,
  cancelAllOrders,
  pauseAllStrategies,
  cancelOrder,
  type TradingFormMetrics,
  type TradingForm,
  type OpenOrder,
  type Fill,
} from "@/api/signals";

// ============================================================
// TRADING FORM TILE
// ============================================================

const FORM_COLORS: Record<TradingForm, string> = {
  SPOT: "border-ok/40",
  MARGIN: "border-warn/40",
  PERP: "border-accent/40",
  FUTURES: "border-info/40",
  OPTIONS: "border-danger/40",
  DEX_SWAP: "border-ok/40",
  DEX_LP: "border-accent/40",
};

function TradingFormTile({
  form,
  onTrade,
}: {
  form: TradingFormMetrics;
  onTrade: (form: TradingForm) => void;
}) {
  const isProfitable = form.pnl_usd >= 0;

  return (
    <div
      className={`flex flex-col rounded border bg-surface p-4 transition-colors hover:bg-surface-raised ${
        form.enabled ? FORM_COLORS[form.form] : "border-border opacity-60"
      }`}
    >
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-sm font-semibold">{form.form}</h3>
        {form.enabled ? (
          <span className="rounded bg-ok/20 px-1.5 py-0.5 text-[10px] font-medium text-ok">
            ACTIVE
          </span>
        ) : (
          <span className="rounded bg-text-disabled/20 px-1.5 py-0.5 text-[10px] font-medium text-text-disabled">
            DISABLED
          </span>
        )}
      </div>

      <div className="space-y-1.5">
        <div className="flex items-center justify-between text-xs">
          <span className="text-text-secondary">signals:</span>
          <span className="font-mono text-text-primary">{form.active_signals}</span>
        </div>

        <div className="flex items-center justify-between text-xs">
          <span className="text-text-secondary">fill rate:</span>
          <span className="font-mono text-text-primary">{form.fill_rate_percent.toFixed(1)}%</span>
        </div>

        <div className="flex items-center justify-between text-xs">
          <span className="text-text-secondary">exposure:</span>
          <span className="font-mono text-text-primary">
            ${form.exposure_usd.toLocaleString()}
          </span>
        </div>

        <div className="flex items-center justify-between text-xs">
          <span className="text-text-secondary">PnL:</span>
          <span
            className={`flex items-center gap-1 font-mono ${
              isProfitable ? "text-ok" : "text-danger"
            }`}
          >
            {isProfitable ? (
              <TrendingUp className="h-3 w-3" />
            ) : (
              <TrendingDown className="h-3 w-3" />
            )}
            {isProfitable ? "+" : ""}${form.pnl_usd.toLocaleString()}
          </span>
        </div>

        <div className="flex items-center justify-between text-xs">
          <span className="text-text-secondary">adapters:</span>
          <span className="font-mono text-[10px] text-text-primary">
            {form.active_adapters.length > 0 ? form.active_adapters.join(", ") : "none"}
          </span>
        </div>
      </div>

      <button
        type="button"
        onClick={() => onTrade(form.form)}
        disabled={!form.enabled}
        className="mt-3 w-full rounded border border-accent bg-accent/10 px-3 py-1.5 text-xs font-medium text-accent transition-colors hover:bg-accent/20 disabled:cursor-not-allowed disabled:opacity-50"
      >
        TRADE
      </button>
    </div>
  );
}

// ============================================================
// TRADING FORMS GRID
// ============================================================

function TradingFormsGrid({
  forms,
  onTrade,
}: {
  forms: TradingFormMetrics[];
  onTrade: (form: TradingForm) => void;
}) {
  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-7">
      {forms.map((form) => (
        <TradingFormTile key={form.form} form={form} onTrade={onTrade} />
      ))}
    </div>
  );
}

// ============================================================
// QUICK ACTIONS BAR
// ============================================================

function QuickActionsBar() {
  const queryClient = useQueryClient();

  const cancelAllMutation = useMutation({
    mutationFn: cancelAllOrders,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["open-orders"] });
    },
  });

  const pauseAllMutation = useMutation({
    mutationFn: pauseAllStrategies,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["trading-forms"] });
    },
  });

  return (
    <div className="flex items-center gap-3 rounded border border-border bg-surface px-4 py-3">
      <span className="text-xs font-medium text-text-secondary">Quick Actions:</span>
      <button
        type="button"
        onClick={() => cancelAllMutation.mutate()}
        disabled={cancelAllMutation.isPending}
        className="flex items-center gap-1.5 rounded border border-danger/40 bg-danger/10 px-3 py-1.5 text-xs font-medium text-danger transition-colors hover:bg-danger/20 disabled:opacity-50"
      >
        <XCircle className="h-3.5 w-3.5" />
        {cancelAllMutation.isPending ? "Cancelling..." : "Cancel All Orders"}
      </button>
      <button
        type="button"
        onClick={() => pauseAllMutation.mutate()}
        disabled={pauseAllMutation.isPending}
        className="flex items-center gap-1.5 rounded border border-warn/40 bg-warn/10 px-3 py-1.5 text-xs font-medium text-warn transition-colors hover:bg-warn/20 disabled:opacity-50"
      >
        <Pause className="h-3.5 w-3.5" />
        {pauseAllMutation.isPending ? "Pausing..." : "Pause All Strategies"}
      </button>
    </div>
  );
}

// ============================================================
// OPEN ORDERS TABLE
// ============================================================

function OpenOrdersTable({ orders }: { orders: OpenOrder[] }) {
  const queryClient = useQueryClient();

  const cancelMutation = useMutation({
    mutationFn: cancelOrder,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["open-orders"] });
    },
  });

  if (orders.length === 0) {
    return (
      <div className="rounded border border-border bg-surface p-4">
        <h3 className="mb-2 text-sm font-semibold">Open Orders</h3>
        <p className="text-sm text-text-secondary">No open orders</p>
      </div>
    );
  }

  return (
    <div className="rounded border border-border bg-surface p-4">
      <h3 className="mb-3 text-sm font-semibold">Open Orders ({orders.length})</h3>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-border text-left text-text-secondary">
              <th className="pb-2 pr-4">Symbol</th>
              <th className="pb-2 pr-4">Side</th>
              <th className="pb-2 pr-4">Type</th>
              <th className="pb-2 pr-4 text-right">Price</th>
              <th className="pb-2 pr-4 text-right">Qty</th>
              <th className="pb-2 pr-4 text-right">Filled</th>
              <th className="pb-2 pr-4">Status</th>
              <th className="pb-2">Action</th>
            </tr>
          </thead>
          <tbody>
            {orders.map((order) => (
              <tr key={order.order_id} className="border-b border-border/50">
                <td className="py-2 pr-4 font-mono">{order.symbol}</td>
                <td
                  className={`py-2 pr-4 font-medium ${
                    order.side === "BUY" ? "text-ok" : "text-danger"
                  }`}
                >
                  {order.side}
                </td>
                <td className="py-2 pr-4 text-text-secondary">{order.order_type}</td>
                <td className="py-2 pr-4 text-right font-mono">
                  {order.price !== null ? `$${order.price.toLocaleString()}` : "-"}
                </td>
                <td className="py-2 pr-4 text-right font-mono">{order.quantity}</td>
                <td className="py-2 pr-4 text-right font-mono">{order.filled_quantity}</td>
                <td className="py-2 pr-4">
                  <span
                    className={`rounded px-1.5 py-0.5 text-[10px] ${
                      order.status === "OPEN"
                        ? "bg-info/20 text-info"
                        : order.status === "PARTIALLY_FILLED"
                          ? "bg-warn/20 text-warn"
                          : "bg-text-disabled/20 text-text-disabled"
                    }`}
                  >
                    {order.status}
                  </span>
                </td>
                <td className="py-2">
                  <button
                    type="button"
                    onClick={() => cancelMutation.mutate(order.order_id)}
                    disabled={cancelMutation.isPending}
                    className="rounded border border-danger/40 px-2 py-0.5 text-[10px] text-danger hover:bg-danger/10"
                  >
                    Cancel
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ============================================================
// RECENT FILLS TABLE
// ============================================================

function RecentFillsTable({ fills }: { fills: Fill[] }) {
  if (fills.length === 0) {
    return (
      <div className="rounded border border-border bg-surface p-4">
        <h3 className="mb-2 text-sm font-semibold">Recent Fills</h3>
        <p className="text-sm text-text-secondary">No recent fills</p>
      </div>
    );
  }

  return (
    <div className="rounded border border-border bg-surface p-4">
      <h3 className="mb-3 text-sm font-semibold">Recent Fills ({fills.length})</h3>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-border text-left text-text-secondary">
              <th className="pb-2 pr-4">Time</th>
              <th className="pb-2 pr-4">Symbol</th>
              <th className="pb-2 pr-4">Side</th>
              <th className="pb-2 pr-4 text-right">Price</th>
              <th className="pb-2 pr-4 text-right">Qty</th>
              <th className="pb-2 pr-4 text-right">Fee</th>
              <th className="pb-2 pr-4">Adapter</th>
            </tr>
          </thead>
          <tbody>
            {fills.map((fill) => (
              <tr key={fill.fill_id} className="border-b border-border/50">
                <td className="py-2 pr-4 font-mono text-text-secondary">
                  {new Date(fill.timestamp_utc).toLocaleTimeString()}
                </td>
                <td className="py-2 pr-4 font-mono">{fill.symbol}</td>
                <td
                  className={`py-2 pr-4 font-medium ${
                    fill.side === "BUY" ? "text-ok" : "text-danger"
                  }`}
                >
                  {fill.side}
                </td>
                <td className="py-2 pr-4 text-right font-mono">
                  ${fill.price.toLocaleString()}
                </td>
                <td className="py-2 pr-4 text-right font-mono">{fill.quantity}</td>
                <td className="py-2 pr-4 text-right font-mono text-text-secondary">
                  {fill.fee} {fill.fee_currency}
                </td>
                <td className="py-2 pr-4 text-[10px] text-text-secondary">
                  {fill.adapter_id}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ============================================================
// QUICK ORDER PANEL
// ============================================================

function QuickOrderPanel({
  selectedForm,
  onClose,
}: {
  selectedForm: TradingForm | null;
  onClose: () => void;
}) {
  const [symbol, setSymbol] = useState("");
  const [side, setSide] = useState<"BUY" | "SELL">("BUY");
  const [quantity, setQuantity] = useState("");

  if (!selectedForm) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-bg/80">
      <div className="w-full max-w-md rounded border border-border bg-surface p-6">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-semibold">Quick Order - {selectedForm}</h3>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 hover:bg-bg"
          >
            <XCircle className="h-5 w-5" />
          </button>
        </div>

        <div className="space-y-4">
          <div>
            <label className="mb-1 block text-xs text-text-secondary">Symbol</label>
            <input
              type="text"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value.toUpperCase())}
              placeholder="BTC/USDT"
              className="w-full rounded border border-border bg-bg px-3 py-2 text-sm focus:border-accent focus:outline-none"
            />
          </div>

          <div>
            <label className="mb-1 block text-xs text-text-secondary">Side</label>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setSide("BUY")}
                className={`flex-1 rounded py-2 text-sm font-medium ${
                  side === "BUY"
                    ? "bg-ok text-bg"
                    : "border border-border bg-bg text-text-primary"
                }`}
              >
                <Play className="mr-1 inline h-3 w-3" /> BUY
              </button>
              <button
                type="button"
                onClick={() => setSide("SELL")}
                className={`flex-1 rounded py-2 text-sm font-medium ${
                  side === "SELL"
                    ? "bg-danger text-bg"
                    : "border border-border bg-bg text-text-primary"
                }`}
              >
                <Activity className="mr-1 inline h-3 w-3" /> SELL
              </button>
            </div>
          </div>

          <div>
            <label className="mb-1 block text-xs text-text-secondary">Quantity</label>
            <input
              type="number"
              value={quantity}
              onChange={(e) => setQuantity(e.target.value)}
              placeholder="0.00"
              className="w-full rounded border border-border bg-bg px-3 py-2 text-sm focus:border-accent focus:outline-none"
            />
          </div>

          <div className="flex gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 rounded border border-border py-2 text-sm hover:bg-bg"
            >
              Cancel
            </button>
            <button
              type="button"
              className="flex-1 rounded bg-accent py-2 text-sm font-medium text-bg hover:bg-accent/90"
            >
              Submit Market Order
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ============================================================
// FORMS PAGE
// ============================================================

export function FormsPage() {
  const [selectedForm, setSelectedForm] = useState<TradingForm | null>(null);

  const {
    data: forms,
    isPending: formsPending,
    isError: formsError,
    error: formsErr,
    refetch: refetchForms,
    isFetching: formsFetching,
  } = useQuery({
    queryKey: ["trading-forms"],
    queryFn: ({ signal }) => fetchTradingForms(signal),
    refetchInterval: 2_000,
  });

  const { data: orders } = useQuery({
    queryKey: ["open-orders"],
    queryFn: ({ signal }) => fetchOpenOrders(signal),
    refetchInterval: 2_000,
  });

  const { data: fills } = useQuery({
    queryKey: ["recent-fills"],
    queryFn: ({ signal }) => fetchRecentFills(signal),
    refetchInterval: 5_000,
  });

  return (
    <section className="flex h-full flex-col">
      <header className="mb-4 flex items-baseline justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-lg font-semibold tracking-tight">
            <Layers className="h-5 w-5 text-accent" />
            INDIRA Trading Forms{" "}
            <span className="ml-2 rounded border border-border bg-bg px-2 py-0.5 font-mono text-[11px] uppercase tracking-widest text-text-secondary">
              LIVE
            </span>
          </h1>
          <p className="mt-1 text-xs text-text-secondary">
            Per-trading-form execution tiles. INDIRA domain - the dashboard is
            the execution interface.
          </p>
        </div>
        <button
          type="button"
          onClick={() => refetchForms()}
          disabled={formsFetching}
          className="rounded border border-border bg-surface px-3 py-1.5 text-xs hover:border-accent disabled:opacity-50"
        >
          {formsFetching ? "refreshing..." : "refresh"}
        </button>
      </header>

      {formsPending && <p className="text-sm text-text-secondary">Loading...</p>}

      {formsError && (
        <div className="rounded border border-danger/40 bg-danger/10 p-3 text-sm text-danger">
          {(formsErr as Error).message}
        </div>
      )}

      {forms && (
        <div className="space-y-6 overflow-auto pb-6">
          <TradingFormsGrid forms={forms} onTrade={setSelectedForm} />

          <QuickActionsBar />

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            {orders && <OpenOrdersTable orders={orders} />}
            {fills && <RecentFillsTable fills={fills} />}
          </div>
        </div>
      )}

      <QuickOrderPanel
        selectedForm={selectedForm}
        onClose={() => setSelectedForm(null)}
      />
    </section>
  );
}
