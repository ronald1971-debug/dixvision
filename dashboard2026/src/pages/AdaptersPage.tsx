import { useQuery } from "@tanstack/react-query";
import { fetchAdapterHealth } from "@/api/signals";

const CEX_ADAPTERS = ["binance", "coinbase", "kraken"] as const;
const DEX_ADAPTERS = ["uniswap", "raydium"] as const;

function AdapterCard({
  name,
  venue,
  state,
  lastTickMs,
  throughput,
  rejects,
}: {
  name: string;
  venue: string;
  state: string;
  lastTickMs: number;
  throughput: number;
  rejects: number;
}) {
  const stateColor =
    state === "READY" ? "text-ok border-ok/30"
    : state === "CONNECTING" ? "text-warn border-warn/30"
    : state === "DEGRADED" ? "text-warn border-warn/30"
    : state === "HALTED" ? "text-danger border-danger/30"
    : "text-slate-400 border-border";

  const relative = (ms: number) => {
    if (ms < 1000) return `${ms}ms`;
    if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
    return `${(ms / 60000).toFixed(1)}m`;
  };

  return (
    <div className="flex flex-col gap-2 rounded border border-border bg-surface p-3">
      <div className="flex items-baseline justify-between">
        <span className="text-sm font-semibold">{name}</span>
        <span className={`rounded border px-1.5 py-0.5 text-[10px] uppercase tracking-widest ${stateColor}`}>
          {state}
        </span>
      </div>
      <span className="text-[10px] uppercase tracking-widest text-slate-500">{venue}</span>
      <div className="flex flex-wrap gap-1">
        {venue === "CEX"
          ? ["SPOT", "MARGIN", "PERP", "FUTURES", "OPTIONS"].map((f) => (
              <span key={f} className="rounded border border-border bg-bg/60 px-1.5 py-0.5 font-mono text-[10px] text-slate-300">{"✓"}</span>
            ))
          : ["DEX_SWAP", "DEX_LP"].map((f) => (
              <span key={f} className="rounded border border-border bg-bg/60 px-1.5 py-0.5 font-mono text-[10px] text-slate-300">{"✓"}</span>
            ))}
      </div>
      <div className="mt-auto grid grid-cols-3 gap-2 text-xs">
        <div>
          <span className="block text-slate-500">last tick</span>
          <span className="font-mono text-slate-200">{relative(lastTickMs)}</span>
        </div>
        <div>
          <span className="block text-slate-500">throughput</span>
          <span className="font-mono text-slate-200">{throughput.toLocaleString()}/min</span>
        </div>
        <div>
          <span className="block text-slate-500">rejects</span>
          <span className={`font-mono ${rejects > 5 ? "text-warn" : "text-slate-200"}`}>{rejects}</span>
        </div>
      </div>
    </div>
  );
}

export function AdaptersPage() {
  const q = useQuery({
    queryKey: ["adapters"],
    queryFn: ({ signal }) => fetchAdapterHealth(signal),
    refetchInterval: 5000,
  });

  const adapters = q.data?.adapters ?? [];

  return (
    <section className="flex h-full flex-col">
      <header className="mb-4">
        <h1 className="text-lg font-semibold tracking-tight">
          DYON Adapter Health
          <span className="ml-2 rounded border border-border bg-bg px-2 py-0.5 font-mono text-[11px] uppercase tracking-widest text-slate-400">LIVE</span>
        </h1>
        <p className="mt-1 text-xs text-slate-400">
          CEX/DEX adapter connection state + last-tick age + throughput
        </p>
      </header>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="flex flex-col gap-3">
          <h2 className="text-xs font-semibold uppercase tracking-widest text-slate-500">CEX Adapters</h2>
          {CEX_ADAPTERS.map((name) => {
            const a = adapters.find((x: { name: string }) => x.name === name);
            if (!a)
              return (
                <AdapterCard
                  key={name}
                  name={name}
                  venue="CEX"
                  state="UNKNOWN"
                  lastTickMs={0}
                  throughput={0}
                  rejects={0}
                />
              );
            return (
              <AdapterCard
                key={a.name}
                name={a.name}
                venue={a.venue}
                state={a.state}
                lastTickMs={a.last_tick_ms}
                throughput={a.throughput_per_min}
                rejects={a.rejects}
              />
            );
          })}
        </div>

        <div className="flex flex-col gap-3">
          <h2 className="text-xs font-semibold uppercase tracking-widest text-slate-500">DEX Adapters</h2>
          {DEX_ADAPTERS.map((name) => {
            const a = adapters.find((x: { name: string }) => x.name === name);
            if (!a)
              return (
                <AdapterCard
                  key={name}
                  name={name}
                  venue="DEX"
                  state="UNKNOWN"
                  lastTickMs={0}
                  throughput={0}
                  rejects={0}
                />
              );
            return (
              <AdapterCard
                key={a.name}
                name={a.name}
                venue={a.venue}
                state={a.state}
                lastTickMs={a.last_tick_ms}
                throughput={a.throughput_per_min}
                rejects={a.rejects}
              />
            );
          })}
        </div>
      </div>
    </section>
  );
}
