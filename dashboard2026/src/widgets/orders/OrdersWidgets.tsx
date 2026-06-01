import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchRecentFills, fetchOpenOrders, submitOrder, cancelOrder, cancelAllOrders } from "@/api/signals";

type Side = "buy" | "sell";
type OrdType = "market" | "limit" | "stop";

export function OrderEntryForm() {
  const qc = useQueryClient();
  const [symbol, setSymbol] = useState("BTC-USDT");
  const [side, setSide] = useState<Side>("buy");
  const [type, setType] = useState<OrdType>("limit");
  const [qty, setQty] = useState("");
  const [price, setPrice] = useState("");

  const submitM = useMutation({
    mutationFn: () =>
      submitOrder({
        symbol,
        side: side.toUpperCase(),
        type: type.toUpperCase(),
        qty: parseFloat(qty) || 0,
        price: type === "market" ? null : parseFloat(price) || null,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["orders/open"] });
      qc.invalidateQueries({ queryKey: ["fills"] });
      setQty("");
      setPrice("");
    },
  });

  return (
    <div className="flex flex-col gap-3 rounded border border-border bg-surface p-4">
      <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-300">Order Entry</h3>
      <div className="grid grid-cols-2 gap-2">
        <div className="col-span-2">
          <label className="mb-1 block text-[10px] uppercase tracking-widest text-slate-500">Symbol</label>
          <input
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            className="w-full rounded border border-border bg-bg px-2 py-1.5 font-mono text-xs text-slate-200 outline-none focus:border-accent"
          />
        </div>
        <div>
          <label className="mb-1 block text-[10px] uppercase tracking-widest text-slate-500">Side</label>
          <select
            value={side}
            onChange={(e) => setSide(e.target.value as Side)}
            className="w-full rounded border border-border bg-bg px-2 py-1.5 text-xs text-slate-200 outline-none focus:border-accent"
          >
            <option value="buy">BUY</option>
            <option value="sell">SELL</option>
          </select>
        </div>
        <div>
          <label className="mb-1 block text-[10px] uppercase tracking-widest text-slate-500">Type</label>
          <select
            value={type}
            onChange={(e) => setType(e.target.value as OrdType)}
            className="w-full rounded border border-border bg-bg px-2 py-1.5 text-xs text-slate-200 outline-none focus:border-accent"
          >
            <option value="market">MARKET</option>
            <option value="limit">LIMIT</option>
            <option value="stop">STOP</option>
          </select>
        </div>
        <div>
          <label className="mb-1 block text-[10px] uppercase tracking-widest text-slate-500">Qty</label>
          <input
            type="number"
            value={qty}
            onChange={(e) => setQty(e.target.value)}
            placeholder="0.00"
            className="w-full rounded border border-border bg-bg px-2 py-1.5 font-mono text-xs text-slate-200 outline-none focus:border-accent"
          />
        </div>
        {type !== "market" && (
          <div>
            <label className="mb-1 block text-[10px] uppercase tracking-widest text-slate-500">Price</label>
            <input
              type="number"
              value={price}
              onChange={(e) => setPrice(e.target.value)}
              placeholder="0.00"
              className="w-full rounded border border-border bg-bg px-2 py-1.5 font-mono text-xs text-slate-200 outline-none focus:border-accent"
            />
          </div>
        )}
      </div>
      <button
        type="button"
        onClick={() => submitM.mutate()}
        disabled={submitM.isPending || !qty}
        className="rounded border border-accent/60 bg-accent/10 px-4 py-2 text-sm font-medium text-accent hover:bg-accent/20 disabled:opacity-50"
      >
        {submitM.isPending ? "submitting…" : "Submit Order"}
      </button>
    </div>
  );
}

const MOCK_OPEN_ORDERS = [
  { id: "ord-001", symbol: "BTC-USDT", side: "BUY", type: "LIMIT", qty: 0.1, price: 64200, status: "OPEN", ts_utc: "2026-05-31T22:00:00Z" },
  { id: "ord-002", symbol: "ETH-USDT", side: "SELL", type: "STOP", qty: 2.0, price: 3100, status: "OPEN", ts_utc: "2026-05-31T21:55:00Z" },
  { id: "ord-003", symbol: "SOL-USDT", side: "BUY", type: "MARKET", qty: 50, price: null, status: "FILLED", ts_utc: "2026-05-31T21:50:00Z" },
];

export function OpenOrdersTable() {
  const q = useQuery({
    queryKey: ["orders/open"],
    queryFn: ({ signal }) => fetchOpenOrders(signal),
    refetchInterval: 5000,
  });

  const qc = useQueryClient();
  const cancelM = useMutation({
    mutationFn: (id: string) => cancelOrder(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["orders/open"] }),
  });

  const cancelAllM = useMutation({
    mutationFn: ({ signal }: { signal?: AbortSignal } = {}) =>
      cancelAllOrders(signal),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["orders/open"] }),
  });

  const orders = q.data?.orders ?? MOCK_OPEN_ORDERS;

  return (
    <div className="flex flex-col gap-2 rounded border border-border bg-surface p-4">
      <div className="flex items-baseline justify-between">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-300">Open Orders</h3>
        <button
          onClick={() => cancelAllM.mutate()}
          disabled={cancelAllM.isPending}
          className="rounded border border-danger/40 bg-danger/10 px-2 py-1 text-[11px] text-danger hover:bg-danger/20 disabled:opacity-50"
        >
          Cancel All
        </button>
      </div>
      <div className="max-h-64 overflow-auto">
        <table className="w-full text-left text-xs">
          <thead className="text-[10px] uppercase text-slate-500">
            <tr>
              <th className="px-2 py-1.5">Symbol</th>
              <th className="px-2 py-1.5">Side</th>
              <th className="px-2 py-1.5">Type</th>
              <th className="px-2 py-1.5">Qty</th>
              <th className="px-2 py-1.5">Price</th>
              <th className="px-2 py-1.5">Status</th>
              <th className="px-2 py-1.5"></th>
            </tr>
          </thead>
          <tbody>
            {orders.map((o: { id: string; symbol: string; side: string; type: string; qty: number; price: number | null; status: string }) => (
              <tr key={o.id} className="border-t border-border">
                <td className="px-2 py-1.5 font-mono text-slate-200">{o.symbol}</td>
                <td className={`px-2 py-1.5 ${o.side === "BUY" ? "text-ok" : "text-danger"}`}>{o.side}</td>
                <td className="px-2 py-1.5 text-slate-400">{o.type}</td>
                <td className="px-2 py-1.5 font-mono text-slate-300">{o.qty}</td>
                <td className="px-2 py-1.5 font-mono text-slate-400">{o.price ?? "—"}</td>
                <td className={`px-2 py-1.5 ${o.status === "OPEN" ? "text-warn" : "text-ok"}`}>{o.status}</td>
                <td className="px-2 py-1.5">
                  <button
                    onClick={() => cancelM.mutate(o.id)}
                    disabled={cancelM.isPending}
                    className="text-[10px] uppercase tracking-widest text-danger hover:underline disabled:opacity-50"
                  >
                    cancel
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

const MOCK_FILLS = [
  { id: "fill-001", symbol: "BTC-USDT", side: "BUY", qty: 0.05, price: 64350, fee_usd: 1.62, ts_utc: "2026-05-31T22:05:00Z" },
  { id: "fill-002", symbol: "ETH-USDT", side: "SELL", qty: 1.5, price: 3080, fee_usd: 2.30, ts_utc: "2026-05-31T22:04:00Z" },
  { id: "fill-003", symbol: "SOL-USDT", side: "BUY", qty: 100, price: 172.5, fee_usd: 8.62, ts_utc: "2026-05-31T22:03:00Z" },
];

export function FillsTable() {
  const q = useQuery({
    queryKey: ["fills"],
    queryFn: ({ signal }) => fetchRecentFills(20, signal),
    refetchInterval: 5000,
  });

  const fills = q.data?.fills ?? MOCK_FILLS;

  return (
    <div className="flex flex-col gap-2 rounded border border-border bg-surface p-4">
      <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-300">Recent Fills</h3>
      <div className="max-h-64 overflow-auto">
        <table className="w-full text-left text-xs">
          <thead className="text-[10px] uppercase text-slate-500">
            <tr>
              <th className="px-2 py-1.5">Time</th>
              <th className="px-2 py-1.5">Symbol</th>
              <th className="px-2 py-1.5">Side</th>
              <th className="px-2 py-1.5">Qty</th>
              <th className="px-2 py-1.5">Price</th>
              <th className="px-2 py-1.5">Fee</th>
            </tr>
          </thead>
          <tbody>
            {fills.map((f: { id: string; ts_utc: string; symbol: string; side: string; qty: number; price: number; fee_usd: number }) => (
              <tr key={f.id} className="border-t border-border">
                <td className="px-2 py-1.5 font-mono text-slate-500">{f.ts_utc?.split("T")[1]?.split("Z")[0]}</td>
                <td className="px-2 py-1.5 font-mono text-slate-200">{f.symbol}</td>
                <td className={`px-2 py-1.5 ${f.side === "BUY" ? "text-ok" : "text-danger"}`}>{f.side}</td>
                <td className="px-2 py-1.5 font-mono text-slate-300">{f.qty}</td>
                <td className="px-2 py-1.5 font-mono text-slate-400">{f.price.toLocaleString()}</td>
                <td className="px-2 py-1.5 font-mono text-slate-500">${f.fee_usd.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
