import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import type { TradingFormsPayload } from "@/api/signals";
import { fetchTradingForms, submitOrder, activateStrategy, pauseStrategy, cancelAllOrders } from "@/api/signals";

const FORM_LIST = ["SPOT", "MARGIN", "PERP", "FUTURES", "OPTIONS", "DEX_SWAP", "DEX_LP"] as const;

function FormTile({
  name,
  q,
}: {
  name: (typeof FORM_LIST)[number];
  q: { data?: TradingFormsPayload };
}) {
  const data = q.data?.forms?.find((f: { form: string }) => f.form === name);
  const queryClient = useQueryClient();

  const trade = useMutation({
    mutationFn: () =>
      submitOrder({ symbol: `${name}-USD`, side: "BUY", qty: 1, price: 0 }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["forms"] }),
  });

  const activate = useMutation({
    mutationFn: () => activateStrategy(name.toLowerCase()),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["forms"] }),
  });

  const pause = useMutation({
    mutationFn: () => pauseStrategy(name.toLowerCase()),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["forms"] }),
  });

  if (!data)
    return (
      <div className="flex h-40 items-center justify-center rounded border border-border bg-surface text-xs text-slate-500">
        Loading {name}…
      </div>
    );

  return (
    <div className="flex h-40 flex-col gap-2 rounded border border-border bg-surface p-3">
      <div className="flex items-baseline justify-between">
        <span className="text-sm font-semibold uppercase tracking-wider">{name}</span>
        <span className="text-[10px] uppercase tracking-widest text-slate-500">INDIRA</span>
      </div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
        <span className="text-slate-500">signals:</span>
        <span className="font-mono text-right text-slate-200">{data.signals}</span>
        <span className="text-slate-500">fill rate:</span>
        <span className="font-mono text-right text-slate-200">{data.fill_rate_pct}%</span>
        <span className="text-slate-500">exp:</span>
        <span className="font-mono text-right text-slate-200">${data.exposure_usd.toLocaleString()}</span>
        <span className="text-slate-500">PnL:</span>
        <span className={`font-mono text-right ${data.pnl_usd >= 0 ? "text-ok" : "text-danger"}`}>
          {data.pnl_usd >= 0 ? "+" : ""}${data.pnl_usd.toLocaleString()}
        </span>
        <span className="text-slate-500">adapters:</span>
        <span className="font-mono text-right text-slate-200">{data.adapters_ready}</span>
      </div>
      <div className="mt-auto flex gap-1.5">
        <button
          onClick={() => trade.mutate()}
          disabled={trade.isPending}
          className="rounded border border-accent/60 bg-accent/10 px-2 py-1 text-[11px] font-medium text-accent hover:bg-accent/20 disabled:opacity-50"
        >
          TRADE
        </button>
        <button
          onClick={() => activate.mutate()}
          disabled={activate.isPending}
          className="rounded border border-ok/60 bg-ok/10 px-2 py-1 text-[11px] font-medium text-ok hover:bg-ok/20 disabled:opacity-50"
        >
          ACTIVE
        </button>
        <button
          onClick={() => pause.mutate()}
          disabled={pause.isPending}
          className="rounded border border-warn/60 bg-warn/10 px-2 py-1 text-[11px] font-medium text-warn hover:bg-warn/20 disabled:opacity-50"
        >
          PAUSE
        </button>
      </div>
    </div>
  );
}

export function FormsPage() {
  const q = useQuery({
    queryKey: ["forms"],
    queryFn: ({ signal }) => fetchTradingForms(signal),
    refetchInterval: 5000,
  });

  const cancelAll = useMutation({
    mutationFn: ({ signal }: { signal?: AbortSignal } = {}) =>
      cancelAllOrders(signal),
  });

  return (
    <section className="flex h-full flex-col">
      <header className="mb-4 flex items-baseline justify-between">
        <div>
          <h1 className="text-lg font-semibold tracking-tight">
            INDIRA Trading Forms
            <span className="ml-2 rounded border border-border bg-bg px-2 py-0.5 font-mono text-[11px] uppercase tracking-widest text-slate-400">LIVE</span>
          </h1>
          <p className="mt-1 text-xs text-slate-400">
            7 trading forms — SPOT / MARGIN / PERP / FUTURES / OPTIONS / DEX_SWAP / DEX_LP
          </p>
        </div>
        <button
          onClick={() => cancelAll.mutate()}
          disabled={cancelAll.isPending}
          className="rounded border border-danger/40 bg-danger/10 px-3 py-1.5 text-xs text-danger hover:bg-danger/20 disabled:opacity-50"
        >
          Cancel All Orders
        </button>
      </header>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {FORM_LIST.map((name) => (
          <FormTile key={name} name={name} q={q} />
        ))}
      </div>
    </section>
  );
}
