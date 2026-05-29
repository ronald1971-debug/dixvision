import { useQuery } from "@tanstack/react-query";

import { fetchAlerts, type Alert, type AlertSeverity } from "@/api/alerts";

const SEV_CLS: Record<AlertSeverity, string> = {
  CRITICAL: "bg-danger/15 text-danger border-danger/40",
  HIGH: "bg-orange-500/15 text-orange-400 border-orange-500/40",
  MEDIUM: "bg-warn/15 text-warn border-warn/40",
  LOW: "bg-blue-500/15 text-blue-400 border-blue-500/40",
  INFO: "bg-surface text-slate-400 border-border",
};

function AlertRow({ alert }: { alert: Alert }) {
  return (
    <li
      className={`flex items-start gap-3 rounded border px-3 py-2.5 text-sm ${SEV_CLS[alert.severity] ?? SEV_CLS.INFO} ${alert.acknowledged ? "opacity-50" : ""}`}
    >
      <span className="mt-0.5 shrink-0 rounded border border-current px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wider">
        {alert.severity}
      </span>
      <div className="flex-1 space-y-0.5">
        <div className="font-medium">{alert.title}</div>
        {alert.detail && <div className="text-xs opacity-80">{alert.detail}</div>}
        <div className="font-mono text-[10px] opacity-50">
          {alert.ts_utc}
          {alert.source ? ` · ${alert.source}` : ""}
        </div>
      </div>
      {alert.acknowledged && (
        <span className="shrink-0 text-[10px] uppercase tracking-wider text-slate-500">ack</span>
      )}
    </li>
  );
}

export function AlertsPage() {
  const { data, isPending, isError, error, refetch, isFetching } = useQuery({
    queryKey: ["alerts"],
    queryFn: ({ signal }) => fetchAlerts(50, signal),
    refetchInterval: 5_000,
  });

  return (
    <section className="flex h-full flex-col">
      <header className="mb-3 flex items-baseline justify-between">
        <div>
          <h1 className="text-lg font-semibold tracking-tight">
            Alerts
            {data && data.unacknowledged > 0 && (
              <span className="ml-2 inline-flex items-center rounded border border-danger/40 bg-danger/15 px-1.5 py-0.5 font-mono text-xs text-danger">
                {data.unacknowledged} unack
              </span>
            )}
          </h1>
          <p className="mt-1 text-xs text-slate-400">
            System alerts sorted by severity. Refreshes every 5 s.
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
        <ul className="flex-1 space-y-1.5 overflow-auto pb-6">
          {data.alerts.length === 0 ? (
            <li className="rounded border border-border bg-surface px-3 py-6 text-center text-sm text-slate-500">
              No alerts
            </li>
          ) : (
            data.alerts.map((a) => <AlertRow key={a.id} alert={a} />)
          )}
        </ul>
      )}
    </section>
  );
}
