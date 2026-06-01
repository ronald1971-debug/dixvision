import { useQuery } from "@tanstack/react-query";
import { fetchGoldenSignals, fetchSLOBurnRate, fetchSystemHazards } from "@/api/signals";

function MetricCard({
  title,
  domain,
  children,
}: {
  title: string;
  domain: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-2 rounded border border-border bg-surface p-4">
      <div className="flex items-baseline justify-between">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-300">{title}</h3>
        <span className="text-[10px] uppercase tracking-widest text-slate-500">{domain}</span>
      </div>
      {children}
    </div>
  );
}

function LatencyPanel() {
  const { data } = useQuery({
    queryKey: ["signals"],
    queryFn: ({ signal }) => fetchGoldenSignals(signal),
    refetchInterval: 5000,
  });

  if (!data)
    return <p className="text-xs text-slate-500">Loading latency…</p>;

  const items: { label: string; p50: number; p95: number; p99: number; threshold: number }[] = [
    { label: "fast-execute", p50: data.latency.fast_execute_p50_ms, p95: data.latency.fast_execute_p95_ms, p99: data.latency.fast_execute_p99_ms, threshold: data.latency.threshold_ms },
    { label: "hazard-detect", p50: data.latency.hazard_detect_p50_ms, p95: data.latency.hazard_detect_p95_ms, p99: data.latency.hazard_detect_p99_ms, threshold: data.latency.threshold_ms },
    { label: "ledger-write", p50: data.latency.ledger_write_p50_ms, p95: data.latency.ledger_write_p95_ms, p99: data.latency.ledger_write_p99_ms, threshold: data.latency.threshold_ms },
  ];

  const color = (v: number, th: number) => {
    if (v >= th) return "text-danger";
    if (v >= th * 0.8) return "text-warn";
    return "text-ok";
  };

  return (
    <div className="flex flex-col gap-2">
      {items.map((it) => (
        <div key={it.label} className="flex items-baseline justify-between">
          <span className="text-xs text-slate-400">{it.label}</span>
          <div className="flex gap-3 font-mono text-xs">
            <span className="text-slate-400">p50 {it.p50.toFixed(1)}ms</span>
            <span className={color(it.p95, it.threshold)}>p95 {it.p95.toFixed(1)}ms</span>
            <span className={color(it.p99, it.threshold)}>p99 {it.p99.toFixed(1)}ms</span>
          </div>
        </div>
      ))}
    </div>
  );
}

function TrafficPanel() {
  const { data } = useQuery({
    queryKey: ["signals"],
    queryFn: ({ signal }) => fetchGoldenSignals(signal),
    refetchInterval: 5000,
  });

  if (!data) return <p className="text-xs text-slate-500">Loading…</p>;

  return (
    <div className="flex flex-col gap-1">
      {[
        ["trades/s", data.traffic.trades_per_sec],
        ["ticks/s", data.traffic.ticks_per_sec],
        ["hazards/s", data.traffic.hazards_per_sec],
        ["ledger events/s", data.traffic.ledger_events_per_sec],
      ].map(([label, value]) => (
        <div key={label} className="flex items-baseline justify-between">
          <span className="text-xs text-slate-400">{label}</span>
          <span className="font-mono text-xs text-slate-200">{typeof value === "number" ? value.toFixed(1) : value}</span>
        </div>
      ))}
    </div>
  );
}

function ErrorsPanel() {
  const { data } = useQuery({
    queryKey: ["signals"],
    queryFn: ({ signal }) => fetchGoldenSignals(signal),
    refetchInterval: 5000,
  });

  if (!data) return <p className="text-xs text-slate-500">Loading…</p>;

  return (
    <div className="flex flex-col gap-1">
      {[
        ["rejected-order rate", data.errors.rejected_order_rate_pct + "%"],
        ["adapter error rate", data.errors.adapter_error_rate_pct + "%"],
        ["hazard CRITICAL rate", data.errors.hazard_critical_rate_pct + "%"],
      ].map(([label, value]) => (
        <div key={label} className="flex items-baseline justify-between">
          <span className="text-xs text-slate-400">{label}</span>
          <span className="font-mono text-xs text-slate-200">{value}</span>
        </div>
      ))}
    </div>
  );
}

function SaturationPanel() {
  const { data } = useQuery({
    queryKey: ["signals"],
    queryFn: ({ signal }) => fetchGoldenSignals(signal),
    refetchInterval: 5000,
  });

  if (!data) return <p className="text-xs text-slate-500">Loading…</p>;

  return (
    <div className="flex flex-col gap-1">
      {[
        ["hazard-queue depth", data.saturation.hazard_queue_depth],
        ["ledger-queue depth", data.saturation.ledger_queue_depth],
        ["risk-cache staleness", data.saturation.risk_cache_age_ms + "ms"],
      ].map(([label, value]) => (
        <div key={label} className="flex items-baseline justify-between">
          <span className="text-xs text-slate-400">{label}</span>
          <span className="font-mono text-xs text-slate-200">{value}</span>
        </div>
      ))}
    </div>
  );
}

function SLOBurnRate() {
  const { data } = useQuery({
    queryKey: ["slo-burn-rate"],
    queryFn: ({ signal }) => fetchSLOBurnRate(signal),
    refetchInterval: 10000,
  });

  if (!data) return <p className="text-xs text-slate-500">Loading SLO…</p>;

  return (
    <MetricCard title="SLO Burn Rate" domain="DYON">
      <div className="flex flex-col gap-2">
        {data.windows.map((w) => (
          <div key={w.window} className="flex flex-col gap-1">
            <div className="flex items-baseline justify-between text-xs">
              <span className="text-slate-400">{w.window} budget</span>
              <span className={`font-mono ${w.status === "warning" ? "text-warn" : "text-ok"}`}>{w.burn_pct}%</span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-bg">
              <div className={`h-full rounded-full ${w.status === "warning" ? "bg-warn" : "bg-ok"}`} style={{ width: `${w.burn_pct}%` }} />
            </div>
            <span className="text-[10px] text-slate-500">
              Alert: &gt;10% burn = PAGE
            </span>
          </div>
        ))}
      </div>
    </MetricCard>
  );
}

function HazardEventFeed() {
  const { data } = useQuery({
    queryKey: ["hazards"],
    queryFn: ({ signal }) => fetchSystemHazards(signal),
    refetchInterval: 5000,
  });

  if (!data) return <p className="text-xs text-slate-500">Loading hazards…</p>;

  return (
    <MetricCard title="SYSTEM_HAZARD Events (DYON → GOVERNANCE)" domain="DYON">
      <div className="flex flex-col gap-1">
        {data.hazards.map((h) => (
          <div key={h.id} className="flex items-center gap-2 rounded border border-border bg-bg/60 px-3 py-1.5">
            <span className="text-xs font-medium text-slate-200">
              {h.hazard_type}
            </span>
            <span className="text-[10px] text-slate-500">{h.source}</span>
            <span className="ml-auto text-[10px] uppercase tracking-wider text-slate-400">
              {h.escalation}
            </span>
          </div>
        ))}
        {data.hazards.length === 0 && (
          <p className="text-xs text-slate-500">No hazard events.</p>
        )}
      </div>
    </MetricCard>
  );
}

export function SignalsPage() {
  return (
    <section className="flex h-full flex-col">
      <header className="mb-4">
        <h1 className="text-lg font-semibold tracking-tight">
          DYON System Intelligence
          <span className="ml-2 rounded border border-border bg-bg px-2 py-0.5 font-mono text-[11px] uppercase tracking-widest text-slate-400">LIVE</span>
        </h1>
        <p className="mt-1 text-xs text-slate-400">
          Four Golden Signals + SLO burn rate + SYSTEM_HAZARD escalation.
          Refreshes every 5s.
        </p>
      </header>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <MetricCard title="Latency" domain="DYON">
          <LatencyPanel />
        </MetricCard>
        <MetricCard title="Traffic" domain="DYON">
          <TrafficPanel />
        </MetricCard>
        <MetricCard title="Errors" domain="DYON">
          <ErrorsPanel />
        </MetricCard>
        <MetricCard title="Saturation" domain="DYON">
          <SaturationPanel />
        </MetricCard>
      </div>

      <div className="mt-4">
        <SLOBurnRate />
      </div>

      <div className="mt-4">
        <HazardEventFeed />
      </div>
    </section>
  );
}
