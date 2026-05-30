import { useEffect, useState } from "react";

interface FabricEvent {
  event_id: string;
  ts_ns: number;
  priority: number; // 1=CRITICAL 2=HIGH 3=NORMAL 4=LOW
  domain: string;
  event_type: string;
  source: string;
  payload: string; // JSON string
}

interface Alert {
  id: string;
  ts_iso: string;
  severity: "info" | "warn" | "danger";
  text: string;
}

function priorityToSeverity(priority: number): "info" | "warn" | "danger" {
  if (priority <= 1) return "danger";
  if (priority === 2) return "warn";
  return "info";
}

function fabricEventToAlert(ev: FabricEvent): Alert {
  let payloadText = "";
  try {
    const p = JSON.parse(ev.payload ?? "{}");
    const first = Object.entries(p)
      .filter(([, v]) => v !== "" && v !== null)
      .slice(0, 2)
      .map(([k, v]) => `${k}=${v}`)
      .join(" ");
    if (first) payloadText = ` — ${first}`;
  } catch {
    // non-parseable payload: skip
  }
  const text = `[${ev.domain}] ${ev.event_type} (${ev.source})${payloadText}`;
  const ts_ms = Math.floor(ev.ts_ns / 1_000_000);
  return {
    id: ev.event_id,
    ts_iso: new Date(ts_ms).toISOString(),
    severity: priorityToSeverity(ev.priority),
    text,
  };
}

const POLL_MS = 5_000;

export function AlertsHub() {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function fetchAlerts() {
      try {
        // Fetch the 50 most recent events across all domains, highest-priority first.
        // Priority sort: the persistence layer returns ASC by ts_ns; we reverse client-side.
        const res = await fetch("/api/fabric/events?limit=50");
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data: { count: number; events: FabricEvent[] } = await res.json();
        if (!cancelled) {
          const mapped = data.events
            .map(fabricEventToAlert)
            .sort((a, b) => {
              // danger first, then warn, then info; within tier: newest first
              const sOrder = { danger: 0, warn: 1, info: 2 };
              const sdiff = sOrder[a.severity] - sOrder[b.severity];
              if (sdiff !== 0) return sdiff;
              return b.ts_iso < a.ts_iso ? -1 : 1;
            });
          setAlerts(mapped);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : String(err));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    fetchAlerts();
    const timer = setInterval(fetchAlerts, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  const dangerCount = alerts.filter((a) => a.severity === "danger").length;
  const warnCount   = alerts.filter((a) => a.severity === "warn").length;
  const badgeColor  =
    dangerCount > 0
      ? "border-red-500/40 bg-red-500/10 text-red-300"
      : warnCount > 0
        ? "border-amber-500/40 bg-amber-500/10 text-amber-300"
        : "border-slate-500/40 bg-slate-500/10 text-slate-400";

  return (
    <div className="flex h-full flex-col rounded border border-border bg-surface">
      <header className="flex items-baseline justify-between border-b border-border px-3 py-2">
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-300">
            Alerts Hub
          </h3>
          <p className="mt-0.5 text-[11px] text-slate-500">
            {error ? `fetch error: ${error}` : "fabric-events · live · 5s poll"}
          </p>
        </div>
        <span
          className={`rounded border px-1.5 py-0.5 font-mono text-[10px] ${badgeColor}`}
        >
          {loading ? "…" : `${alerts.length} events`}
        </span>
      </header>
      <ul className="flex-1 divide-y divide-border overflow-auto">
        {loading && (
          <li className="px-3 py-2 text-[12px] text-slate-500">Loading…</li>
        )}
        {!loading && alerts.length === 0 && (
          <li className="px-3 py-2 text-[12px] text-slate-500">
            No events in fabric log.
          </li>
        )}
        {alerts.map((a) => (
          <li
            key={a.id}
            className="flex items-baseline gap-2 px-3 py-1.5 text-[12px]"
          >
            <span
              className={`mt-1 h-2 w-2 shrink-0 rounded-full ${
                a.severity === "danger"
                  ? "bg-red-400"
                  : a.severity === "warn"
                    ? "bg-amber-300"
                    : "bg-accent"
              }`}
            />
            <span className="font-mono text-[10px] uppercase tracking-wider text-slate-500">
              {new Date(a.ts_iso).toLocaleTimeString()}
            </span>
            <span className="flex-1 text-slate-200">{a.text}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
