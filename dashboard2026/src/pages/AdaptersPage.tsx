import { useQuery } from "@tanstack/react-query";
import { Network, Check, X, Clock, Activity } from "lucide-react";

import { fetchAdapterHealth, type AdapterHealth, type TradingForm } from "@/api/signals";

// ============================================================
// ADAPTER CARD
// ============================================================

function FormBadge({ form, supported }: { form: TradingForm; supported: boolean }) {
  return (
    <span
      className={`inline-flex items-center gap-0.5 rounded px-1.5 py-0.5 text-[10px] font-medium ${
        supported
          ? "bg-ok/20 text-ok"
          : "bg-text-disabled/20 text-text-disabled"
      }`}
    >
      {form}
      {supported ? (
        <Check className="h-2.5 w-2.5" />
      ) : (
        <X className="h-2.5 w-2.5" />
      )}
    </span>
  );
}

function AdapterCard({ adapter }: { adapter: AdapterHealth }) {
  const ALL_FORMS: TradingForm[] = [
    "SPOT",
    "MARGIN",
    "PERP",
    "FUTURES",
    "OPTIONS",
    "DEX_SWAP",
    "DEX_LP",
  ];

  const relevantForms =
    adapter.adapter_type === "CEX"
      ? (["SPOT", "MARGIN", "PERP", "FUTURES", "OPTIONS"] as TradingForm[])
      : (["DEX_SWAP", "DEX_LP"] as TradingForm[]);

  const isStale = adapter.last_tick_age_ms > 5000;
  const hasHighErrors = adapter.error_rate > 0.01;

  return (
    <div
      className={`rounded border bg-surface p-4 ${
        adapter.connected
          ? isStale
            ? "border-warn/40"
            : "border-ok/40"
          : "border-danger/40"
      }`}
    >
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-semibold">{adapter.name}</h3>
          <span className="rounded bg-surface-raised px-1.5 py-0.5 text-[10px] font-medium text-text-secondary">
            {adapter.adapter_type}
          </span>
        </div>
        {adapter.connected ? (
          <span
            className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${
              isStale ? "bg-warn/20 text-warn" : "bg-ok/20 text-ok"
            }`}
          >
            {isStale ? "STALE" : "CONNECTED"}
          </span>
        ) : (
          <span className="rounded bg-danger/20 px-1.5 py-0.5 text-[10px] font-medium text-danger">
            DISCONNECTED
          </span>
        )}
      </div>

      <div className="mb-3 flex flex-wrap gap-1">
        {relevantForms.map((form) => (
          <FormBadge
            key={form}
            form={form}
            supported={adapter.supported_forms.includes(form)}
          />
        ))}
      </div>

      <div className="grid grid-cols-3 gap-3 border-t border-border pt-3">
        <div>
          <div className="flex items-center gap-1 text-[10px] uppercase tracking-wider text-text-secondary">
            <Clock className="h-3 w-3" />
            last tick
          </div>
          <div
            className={`mt-0.5 font-mono text-sm ${
              isStale ? "text-warn" : "text-ok"
            }`}
          >
            {adapter.last_tick_age_ms < 1000
              ? `${adapter.last_tick_age_ms}ms`
              : `${(adapter.last_tick_age_ms / 1000).toFixed(1)}s`}
          </div>
        </div>

        <div>
          <div className="flex items-center gap-1 text-[10px] uppercase tracking-wider text-text-secondary">
            <Activity className="h-3 w-3" />
            throughput
          </div>
          <div className="mt-0.5 font-mono text-sm text-text-primary">
            {adapter.throughput_per_min.toLocaleString()}/min
          </div>
        </div>

        <div>
          <div className="text-[10px] uppercase tracking-wider text-text-secondary">
            rejects (24h)
          </div>
          <div
            className={`mt-0.5 font-mono text-sm ${
              hasHighErrors ? "text-danger" : "text-text-primary"
            }`}
          >
            {adapter.reject_count_24h}
          </div>
        </div>
      </div>
    </div>
  );
}

// ============================================================
// ADAPTERS GRID (grouped by CEX/DEX)
// ============================================================

function AdaptersGrid({ adapters }: { adapters: AdapterHealth[] }) {
  const cexAdapters = adapters.filter((a) => a.adapter_type === "CEX");
  const dexAdapters = adapters.filter((a) => a.adapter_type === "DEX");

  return (
    <div className="space-y-6">
      {cexAdapters.length > 0 && (
        <div>
          <h2 className="mb-3 text-sm font-medium text-text-secondary">
            CEX Adapters ({cexAdapters.length})
          </h2>
          <div className="space-y-3">
            {cexAdapters.map((adapter) => (
              <AdapterCard key={adapter.adapter_id} adapter={adapter} />
            ))}
          </div>
        </div>
      )}

      {dexAdapters.length > 0 && (
        <div>
          <h2 className="mb-3 text-sm font-medium text-text-secondary">
            DEX Adapters ({dexAdapters.length})
          </h2>
          <div className="space-y-3">
            {dexAdapters.map((adapter) => (
              <AdapterCard key={adapter.adapter_id} adapter={adapter} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ============================================================
// ADAPTERS SUMMARY
// ============================================================

function AdaptersSummary({ adapters }: { adapters: AdapterHealth[] }) {
  const connected = adapters.filter((a) => a.connected).length;
  const stale = adapters.filter((a) => a.connected && a.last_tick_age_ms > 5000).length;
  const disconnected = adapters.filter((a) => !a.connected).length;
  const totalThroughput = adapters.reduce((sum, a) => sum + a.throughput_per_min, 0);
  const totalRejects = adapters.reduce((sum, a) => sum + a.reject_count_24h, 0);

  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-5">
      <div className="rounded border border-border bg-surface p-3">
        <div className="text-[10px] uppercase tracking-wider text-text-secondary">
          Connected
        </div>
        <div className="mt-1 font-mono text-xl text-ok">{connected}</div>
      </div>

      <div className="rounded border border-border bg-surface p-3">
        <div className="text-[10px] uppercase tracking-wider text-text-secondary">
          Stale
        </div>
        <div className={`mt-1 font-mono text-xl ${stale > 0 ? "text-warn" : "text-text-primary"}`}>
          {stale}
        </div>
      </div>

      <div className="rounded border border-border bg-surface p-3">
        <div className="text-[10px] uppercase tracking-wider text-text-secondary">
          Disconnected
        </div>
        <div className={`mt-1 font-mono text-xl ${disconnected > 0 ? "text-danger" : "text-text-primary"}`}>
          {disconnected}
        </div>
      </div>

      <div className="rounded border border-border bg-surface p-3">
        <div className="text-[10px] uppercase tracking-wider text-text-secondary">
          Total Throughput
        </div>
        <div className="mt-1 font-mono text-xl text-text-primary">
          {totalThroughput.toLocaleString()}/min
        </div>
      </div>

      <div className="rounded border border-border bg-surface p-3">
        <div className="text-[10px] uppercase tracking-wider text-text-secondary">
          Rejects (24h)
        </div>
        <div className={`mt-1 font-mono text-xl ${totalRejects > 50 ? "text-warn" : "text-text-primary"}`}>
          {totalRejects}
        </div>
      </div>
    </div>
  );
}

// ============================================================
// ADAPTERS PAGE
// ============================================================

export function AdaptersPage() {
  const {
    data: adapters,
    isPending,
    isError,
    error,
    refetch,
    isFetching,
  } = useQuery({
    queryKey: ["adapter-health"],
    queryFn: ({ signal }) => fetchAdapterHealth(signal),
    refetchInterval: 3_000,
  });

  return (
    <section className="flex h-full flex-col">
      <header className="mb-4 flex items-baseline justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-lg font-semibold tracking-tight">
            <Network className="h-5 w-5 text-accent" />
            DYON Adapter Health{" "}
            <span className="ml-2 rounded border border-border bg-bg px-2 py-0.5 font-mono text-[11px] uppercase tracking-widest text-text-secondary">
              LIVE
            </span>
          </h1>
          <p className="mt-1 text-xs text-text-secondary">
            Per-adapter connection state, last-tick age, throughput, and reject counts.
            DYON domain infrastructure monitoring.
          </p>
        </div>
        <button
          type="button"
          onClick={() => refetch()}
          disabled={isFetching}
          className="rounded border border-border bg-surface px-3 py-1.5 text-xs hover:border-accent disabled:opacity-50"
        >
          {isFetching ? "refreshing..." : "refresh"}
        </button>
      </header>

      {isPending && <p className="text-sm text-text-secondary">Loading...</p>}

      {isError && (
        <div className="rounded border border-danger/40 bg-danger/10 p-3 text-sm text-danger">
          {(error as Error).message}
        </div>
      )}

      {adapters && (
        <div className="space-y-6 overflow-auto pb-6">
          <AdaptersSummary adapters={adapters} />
          <AdaptersGrid adapters={adapters} />
        </div>
      )}
    </section>
  );
}
