import { useState } from "react";

import { fetchMode } from "@/api/dashboard";
import { useQuery } from "@tanstack/react-query";

import { apiUrl } from "@/api/base";
import { getAutonomyMode } from "@/state/autonomy";
import { pushToast } from "@/ui/toast";

/**
 * Order form (PR-#2 spec §3.x).
 *
 * Order types: market / limit / stop-limit / OCO / bracket.
 * Mode-aware: disabled in LOCKED / SAFE; in CANARY notional clamped
 * by the mode-effect table; in PAPER the form simulates without
 * sending (system-mode SHADOW was demolished by SHADOW-DEMOLITION-02
 * in PR #221 — PAPER now supplies the observe-only behaviour).
 * Autonomy-aware: in USER_CONTROLLED every submit prompts
 * a confirm dialog, in SEMI_AUTO submit goes via approval queue, in
 * FULL_AUTO submit fires immediately within the active envelope.
 */
type OrderType = "market" | "limit" | "stop-limit" | "oco" | "bracket";
type Side = "buy" | "sell";

const ORDER_TYPES: readonly OrderType[] = [
  "market",
  "limit",
  "stop-limit",
  "oco",
  "bracket",
];

export interface OrderFormProps {
  symbol: string;
}

export function OrderForm({ symbol }: OrderFormProps) {
  const { data } = useQuery({
    queryKey: ["dashboard", "mode"],
    queryFn: ({ signal }) => fetchMode(signal),
    refetchInterval: 2_000,
  });
  const mode = data?.current_mode ?? "SAFE";
  const isLocked = data?.is_locked ?? false;
  const orderingDisabled =
    mode === "LOCKED" || mode === "SAFE" || isLocked;

  const [type, setType] = useState<OrderType>("limit");
  const [side, setSide] = useState<Side>("buy");
  const [size, setSize] = useState<string>("");
  const [price, setPrice] = useState<string>("");
  const [stopPrice, setStopPrice] = useState<string>("");
  const [tpPrice, setTpPrice] = useState<string>("");
  const [reduceOnly, setReduceOnly] = useState(false);
  const [postOnly, setPostOnly] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (orderingDisabled || isSubmitting) return;

    setIsSubmitting(true);
    try {
      const autonomy = getAutonomyMode();
      const response = await fetch(apiUrl("/api/dashboard/action/intent"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          objective: "trade",
          risk_mode: autonomy,
          horizon: "intra-minute",
          focus: [symbol],
          reason: `${type} ${side} ${size}`,
          order_params: {
            symbol,
            type,
            side,
            size: Number(size || 0),
            price: price ? Number(price) : null,
            stop_price: stopPrice ? Number(stopPrice) : null,
            tp_price: tpPrice ? Number(tpPrice) : null,
            reduce_only: reduceOnly,
            post_only: postOnly,
          },
        }),
      });

      if (!response.ok) {
        const errorText = await response.text();
        pushToast(`Order submission failed: ${response.statusText}`, {
          tone: "error",
          ttl_ms: 5000,
        });
        console.error("Order submission error:", errorText);
        return;
      }

      pushToast(`${side.toUpperCase()} order submitted`, {
        tone: "success",
        ttl_ms: 3000,
      });

      // Reset form on success
      setSize("");
      setPrice("");
      setStopPrice("");
      setTpPrice("");
    } catch (error) {
      pushToast(`Order submission error: ${error instanceof Error ? error.message : "Unknown error"}`, {
        tone: "error",
        ttl_ms: 5000,
      });
      console.error("Order submission exception:", error);
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <form
      onSubmit={submit}
      className="flex h-full flex-col rounded border border-border bg-surface text-sm"
    >
      <header className="flex items-baseline justify-between border-b border-border px-3 py-2">
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-300">
            Order · {symbol}
          </h3>
          <p className="mt-0.5 text-[11px] text-slate-500">
            mode {mode} · autonomy gate via approval edge
          </p>
        </div>
        <span
          className={`rounded border px-1.5 py-0.5 font-mono text-[10px] uppercase ${
            orderingDisabled
              ? "border-amber-500/40 bg-amber-500/10 text-amber-300"
              : "border-accent/40 bg-accent/10 text-accent"
          }`}
        >
          {orderingDisabled ? "disabled" : "armed"}
        </span>
      </header>
      <div className="flex flex-wrap gap-1 border-b border-border px-3 py-2 font-mono text-[11px] uppercase tracking-wider">
        {ORDER_TYPES.map((t) => (
          <button
            key={t}
            type="button"
            className={`rounded border px-2 py-1 ${
              t === type
                ? "border-accent bg-accent text-bg"
                : "border-border bg-bg text-slate-400 hover:text-accent"
            }`}
            onClick={() => setType(t)}
            disabled={isSubmitting}
          >
            {t}
          </button>
        ))}
      </div>
      <div className="flex-1 space-y-2 overflow-auto p-3">
        <div className="flex gap-1">
          <button
            type="button"
            className={`flex-1 rounded border px-2 py-1.5 font-mono text-[12px] uppercase tracking-wider ${
              side === "buy"
                ? "border-emerald-500 bg-emerald-500/15 text-emerald-300"
                : "border-border bg-bg text-slate-400"
            }`}
            onClick={() => setSide("buy")}
            disabled={isSubmitting}
          >
            buy
          </button>
          <button
            type="button"
            className={`flex-1 rounded border px-2 py-1.5 font-mono text-[12px] uppercase tracking-wider ${
              side === "sell"
                ? "border-red-500 bg-red-500/15 text-red-300"
                : "border-border bg-bg text-slate-400"
            }`}
            onClick={() => setSide("sell")}
            disabled={isSubmitting}
          >
            sell
          </button>
        </div>
        <Field label="Size">
          <input
            type="number"
            value={size}
            step={0.0001}
            onChange={(e) => setSize(e.target.value)}
            className="w-full rounded border border-border bg-bg px-2 py-1 font-mono text-[12px]"
            placeholder="0"
            disabled={isSubmitting}
          />
        </Field>
        {type !== "market" && (
          <Field label="Price">
            <input
              type="number"
              value={price}
              step={0.0001}
              onChange={(e) => setPrice(e.target.value)}
              className="w-full rounded border border-border bg-bg px-2 py-1 font-mono text-[12px]"
              disabled={isSubmitting}
            />
          </Field>
        )}
        {(type === "stop-limit" || type === "oco" || type === "bracket") && (
          <Field label="Stop">
            <input
              type="number"
              value={stopPrice}
              step={0.0001}
              onChange={(e) => setStopPrice(e.target.value)}
              className="w-full rounded border border-border bg-bg px-2 py-1 font-mono text-[12px]"
              disabled={isSubmitting}
            />
          </Field>
        )}
        {(type === "oco" || type === "bracket") && (
          <Field label="Take-profit">
            <input
              type="number"
              value={tpPrice}
              step={0.0001}
              onChange={(e) => setTpPrice(e.target.value)}
              className="w-full rounded border border-border bg-bg px-2 py-1 font-mono text-[12px]"
              disabled={isSubmitting}
            />
          </Field>
        )}
        <div className="flex gap-3 font-mono text-[11px] uppercase tracking-wider text-slate-400">
          <label className="flex items-center gap-1">
            <input
              type="checkbox"
              checked={reduceOnly}
              onChange={(e) => setReduceOnly(e.target.checked)}
              disabled={isSubmitting}
            />
            reduce-only
          </label>
          <label className="flex items-center gap-1">
            <input
              type="checkbox"
              checked={postOnly}
              onChange={(e) => setPostOnly(e.target.checked)}
              disabled={isSubmitting}
            />
            post-only
          </label>
        </div>
      </div>
      <footer className="border-t border-border p-2">
        <button
          type="submit"
          disabled={orderingDisabled || isSubmitting}
          className={`w-full rounded border px-3 py-2 font-mono text-[12px] uppercase tracking-wider ${
            orderingDisabled || isSubmitting
              ? "border-border bg-bg text-slate-500"
              : side === "buy"
                ? "border-emerald-500 bg-emerald-500 text-bg"
                : "border-red-500 bg-red-500 text-bg"
          }`}
        >
          {orderingDisabled ? "ordering disabled" : isSubmitting ? "submitting..." : `submit ${side}`}
        </button>
      </footer>
    </form>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="flex flex-col gap-0.5">
      <span className="font-mono text-[10px] uppercase tracking-wider text-slate-500">
        {label}
      </span>
      {children}
    </label>
  );
}
