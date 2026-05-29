import { useQuery } from "@tanstack/react-query";

import { fetchSysHealth, type ComponentStatus } from "@/api/syshealth";
import { fetchVoiceAlerts } from "@/api/voicealerts";

function statusCls(status: ComponentStatus["status"]) {
  switch (status) {
    case "ok":
      return "text-ok";
    case "degraded":
      return "text-warn";
    case "error":
      return "text-danger";
    default:
      return "text-slate-400";
  }
}

function ComponentCard({ c }: { c: ComponentStatus }) {
  return (
    <div className="flex flex-col gap-1 rounded border border-border bg-surface px-3 py-2.5">
      <div className="flex items-center justify-between gap-2">
        <span className="truncate text-sm font-medium">{c.name}</span>
        <span
          className={`shrink-0 rounded border border-current px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wider ${statusCls(c.status)}`}
        >
          {c.status}
        </span>
      </div>
      {c.detail && (
        <span className="text-xs text-slate-400">{c.detail}</span>
      )}
      {c.latency_ms !== undefined && (
        <span className="font-mono text-[10px] text-slate-500">
          {c.latency_ms.toFixed(1)} ms
        </span>
      )}
    </div>
  );
}

function VoiceAlertsCard() {
  const { data } = useQuery({
    queryKey: ["voice-alerts"],
    queryFn: ({ signal }) => fetchVoiceAlerts(signal),
    refetchInterval: 15_000,
  });

  return (
    <div className="flex flex-col gap-1 rounded border border-border bg-surface px-3 py-2.5">
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm font-medium">Voice Alerts</span>
        <span className="shrink-0 rounded border border-border px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wider text-slate-400">
          TTS
        </span>
      </div>
      {data ? (
        <>
          <span className="text-xs text-slate-400">
            threshold: <span className="text-slate-200">{data.min_severity}</span>
            {" · "}dispatched: <span className="text-slate-200">{data.dispatched_count}</span>
          </span>
          {data.history.length > 0 && (
            <span className="font-mono text-[10px] text-slate-500 truncate">
              last: {data.history[data.history.length - 1].output_path}
            </span>
          )}
        </>
      ) : (
        <span className="text-xs text-slate-500">loading…</span>
      )}
    </div>
  );
}

export function SystemHealthPage() {
  const { data, isPending, isError, error, refetch, isFetching } = useQuery({
    queryKey: ["syshealth"],
    queryFn: ({ signal }) => fetchSysHealth(signal),
    refetchInterval: 5_000,
  });

  return (
    <section className="flex h-full flex-col">
      <header className="mb-3 flex items-baseline justify-between">
        <div>
          <h1 className="text-lg font-semibold tracking-tight">
            System Health{" "}
            <span className="ml-2 rounded border border-border bg-bg px-2 py-0.5 font-mono text-[11px] uppercase tracking-widest text-slate-400">
              LIVE
            </span>
          </h1>
          <p className="mt-1 text-xs text-slate-400">
            Component status grid, dead man switch, and latency guard
            indicator. Refreshes every 5 s.
          </p>
        </div>
        <button
          type="button"
          onClick={() => refetch()}
          disabled={isFetching}
          className="rounded border border-border bg-surface px-3 py-1.5 text-xs hover:border-accent disabled:opacity-50"
        >
          {isFetching ? "refreshing…" : "refresh"}
        </button>
      </header>

      {isPending && <p className="text-sm text-slate-400">Loading…</p>}

      {isError && (
        <div className="rounded border border-danger/40 bg-danger/10 p-3 text-sm text-danger">
          {(error as Error).message}
        </div>
      )}

      {data && (
        <div className="space-y-4 overflow-auto pb-6">
          {data.dead_man && (
            <div
              className={`flex items-center gap-3 rounded border px-4 py-2 text-sm ${
                data.dead_man.active
                  ? "border-ok/40 bg-ok/10 text-ok"
                  : "border-danger/40 bg-danger/10 text-danger"
              }`}
            >
              <span className="font-semibold">Dead Man</span>
              <span>{data.dead_man.active ? "active" : "INACTIVE"}</span>
              <span className="text-xs opacity-70">
                last heartbeat {data.dead_man.last_heartbeat_utc}
              </span>
            </div>
          )}

          {data.latency_guard && (
            <div
              className={`flex items-center gap-3 rounded border px-4 py-2 text-sm ${
                data.latency_guard.breached
                  ? "border-danger/40 bg-danger/10 text-danger"
                  : "border-ok/40 bg-ok/10 text-ok"
              }`}
            >
              <span className="font-semibold">Latency Guard</span>
              <span>{data.latency_guard.breached ? "BREACHED" : "ok"}</span>
              <span className="font-mono text-xs opacity-70">
                p99 {data.latency_guard.p99_ms.toFixed(1)} ms / threshold{" "}
                {data.latency_guard.threshold_ms} ms
              </span>
            </div>
          )}

          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {(data.components ?? []).map((c) => (
              <ComponentCard key={c.name} c={c} />
            ))}
            <VoiceAlertsCard />
          </div>
        </div>
      )}
    </section>
  );
}
