import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, TrendingUp, Zap, Activity } from "lucide-react";

import {
  fetchGoldenSignals,
  fetchSLOBurnRate,
  fetchSystemHazards,
  type GoldenSignals,
  type SLOBurnRate,
  type SystemHazard,
  type HazardSeverity,
} from "@/api/signals";

// ============================================================
// LATENCY PANEL
// ============================================================

function LatencyPanel({ latency }: { latency: GoldenSignals["latency"] }) {
  const isBreaching = latency.fast_execute_p99_ms > latency.threshold_ms;

  return (
    <div className="flex flex-col rounded border border-border bg-surface p-4">
      <div className="mb-3 flex items-center gap-2">
        <Zap className="h-4 w-4 text-accent" />
        <h3 className="text-sm font-semibold">Latency</h3>
        {isBreaching && (
          <span className="ml-auto rounded bg-danger/20 px-1.5 py-0.5 text-[10px] font-medium text-danger">
            BREACH
          </span>
        )}
      </div>

      <div className="space-y-2">
        <div>
          <div className="text-[10px] uppercase tracking-wider text-text-secondary">
            fast_execute
          </div>
          <div className="mt-0.5 flex items-baseline gap-2 font-mono text-sm">
            <span className="text-text-secondary">p50</span>
            <span className="text-ok">{latency.fast_execute_p50_ms.toFixed(1)}ms</span>
            <span className="text-text-secondary">p95</span>
            <span className="text-warn">{latency.fast_execute_p95_ms.toFixed(1)}ms</span>
            <span className="text-text-secondary">p99</span>
            <span className={isBreaching ? "text-danger" : "text-ok"}>
              {latency.fast_execute_p99_ms.toFixed(1)}ms
            </span>
          </div>
        </div>

        <div>
          <div className="text-[10px] uppercase tracking-wider text-text-secondary">
            hazard_detect
          </div>
          <div className="mt-0.5 flex items-baseline gap-2 font-mono text-sm">
            <span className="text-text-secondary">p50</span>
            <span className="text-ok">{latency.hazard_detect_p50_ms.toFixed(1)}ms</span>
            <span className="text-text-secondary">p95</span>
            <span className="text-warn">{latency.hazard_detect_p95_ms.toFixed(1)}ms</span>
          </div>
        </div>

        <div>
          <div className="text-[10px] uppercase tracking-wider text-text-secondary">
            ledger_write
          </div>
          <div className="mt-0.5 flex items-baseline gap-2 font-mono text-sm">
            <span className="text-text-secondary">p50</span>
            <span className="text-ok">{latency.ledger_write_p50_ms.toFixed(1)}ms</span>
            <span className="text-text-secondary">p95</span>
            <span className="text-warn">{latency.ledger_write_p95_ms.toFixed(1)}ms</span>
          </div>
        </div>

        <div className="mt-2 border-t border-border pt-2 text-[10px] text-text-secondary">
          threshold: <span className="font-mono text-text-primary">{latency.threshold_ms}ms</span>
        </div>
      </div>
    </div>
  );
}

// ============================================================
// TRAFFIC PANEL
// ============================================================

function TrafficPanel({ traffic }: { traffic: GoldenSignals["traffic"] }) {
  return (
    <div className="flex flex-col rounded border border-border bg-surface p-4">
      <div className="mb-3 flex items-center gap-2">
        <TrendingUp className="h-4 w-4 text-accent" />
        <h3 className="text-sm font-semibold">Traffic</h3>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-wider text-text-secondary">
            trades/sec
          </div>
          <div className="font-mono text-lg text-text-primary">
            {traffic.trades_per_sec.toFixed(1)}
          </div>
          <div className="text-[10px] text-text-secondary">INDIRA</div>
        </div>

        <div>
          <div className="text-[10px] uppercase tracking-wider text-text-secondary">
            ticks/sec
          </div>
          <div className="font-mono text-lg text-text-primary">
            {traffic.ticks_per_sec.toFixed(1)}
          </div>
          <div className="text-[10px] text-text-secondary">DYON</div>
        </div>

        <div>
          <div className="text-[10px] uppercase tracking-wider text-text-secondary">
            hazards/sec
          </div>
          <div className="font-mono text-lg text-text-primary">
            {traffic.hazards_per_sec.toFixed(2)}
          </div>
          <div className="text-[10px] text-text-secondary">DYON</div>
        </div>

        <div>
          <div className="text-[10px] uppercase tracking-wider text-text-secondary">
            ledger/sec
          </div>
          <div className="font-mono text-lg text-text-primary">
            {traffic.ledger_events_per_sec.toFixed(1)}
          </div>
          <div className="text-[10px] text-text-secondary">EVENT FABRIC</div>
        </div>
      </div>
    </div>
  );
}

// ============================================================
// ERRORS PANEL
// ============================================================

function ErrorsPanel({ errors }: { errors: GoldenSignals["errors"] }) {
  const hasHighErrors =
    errors.rejected_order_rate > 0.05 ||
    errors.adapter_error_rate > 0.01 ||
    errors.hazard_critical_rate > 0;

  return (
    <div className="flex flex-col rounded border border-border bg-surface p-4">
      <div className="mb-3 flex items-center gap-2">
        <AlertTriangle className="h-4 w-4 text-accent" />
        <h3 className="text-sm font-semibold">Errors</h3>
        {hasHighErrors && (
          <span className="ml-auto rounded bg-warn/20 px-1.5 py-0.5 text-[10px] font-medium text-warn">
            ELEVATED
          </span>
        )}
      </div>

      <div className="space-y-3">
        <div>
          <div className="flex items-baseline justify-between">
            <span className="text-[10px] uppercase tracking-wider text-text-secondary">
              rejected-order rate
            </span>
            <span
              className={`font-mono text-sm ${
                errors.rejected_order_rate > 0.05 ? "text-danger" : "text-ok"
              }`}
            >
              {(errors.rejected_order_rate * 100).toFixed(2)}%
            </span>
          </div>
          <div className="mt-1 h-1.5 w-full overflow-hidden rounded bg-bg">
            <div
              className={`h-full ${
                errors.rejected_order_rate > 0.05 ? "bg-danger" : "bg-ok"
              }`}
              style={{ width: `${Math.min(errors.rejected_order_rate * 100 * 10, 100)}%` }}
            />
          </div>
        </div>

        <div>
          <div className="flex items-baseline justify-between">
            <span className="text-[10px] uppercase tracking-wider text-text-secondary">
              adapter error rate
            </span>
            <span
              className={`font-mono text-sm ${
                errors.adapter_error_rate > 0.01 ? "text-warn" : "text-ok"
              }`}
            >
              {(errors.adapter_error_rate * 100).toFixed(3)}%
            </span>
          </div>
          <div className="mt-1 h-1.5 w-full overflow-hidden rounded bg-bg">
            <div
              className={`h-full ${
                errors.adapter_error_rate > 0.01 ? "bg-warn" : "bg-ok"
              }`}
              style={{ width: `${Math.min(errors.adapter_error_rate * 100 * 100, 100)}%` }}
            />
          </div>
        </div>

        <div>
          <div className="flex items-baseline justify-between">
            <span className="text-[10px] uppercase tracking-wider text-text-secondary">
              hazard CRITICAL rate
            </span>
            <span
              className={`font-mono text-sm ${
                errors.hazard_critical_rate > 0 ? "text-danger" : "text-ok"
              }`}
            >
              {(errors.hazard_critical_rate * 100).toFixed(3)}%
            </span>
          </div>
          <div className="mt-1 h-1.5 w-full overflow-hidden rounded bg-bg">
            <div
              className={`h-full ${
                errors.hazard_critical_rate > 0 ? "bg-danger" : "bg-ok"
              }`}
              style={{ width: `${Math.min(errors.hazard_critical_rate * 100 * 100, 100)}%` }}
            />
          </div>
        </div>
      </div>
    </div>
  );
}

// ============================================================
// SATURATION PANEL
// ============================================================

function SaturationPanel({ saturation }: { saturation: GoldenSignals["saturation"] }) {
  const hazardQueuePct =
    saturation.hazard_queue_max > 0
      ? (saturation.hazard_queue_depth / saturation.hazard_queue_max) * 100
      : 0;
  const ledgerQueuePct =
    saturation.ledger_queue_max > 0
      ? (saturation.ledger_queue_depth / saturation.ledger_queue_max) * 100
      : 0;

  return (
    <div className="flex flex-col rounded border border-border bg-surface p-4">
      <div className="mb-3 flex items-center gap-2">
        <Activity className="h-4 w-4 text-accent" />
        <h3 className="text-sm font-semibold">Saturation</h3>
      </div>

      <div className="space-y-3">
        <div>
          <div className="flex items-baseline justify-between">
            <span className="text-[10px] uppercase tracking-wider text-text-secondary">
              hazard queue
            </span>
            <span className="font-mono text-sm text-text-primary">
              {saturation.hazard_queue_depth} / {saturation.hazard_queue_max}
            </span>
          </div>
          <div className="mt-1 h-1.5 w-full overflow-hidden rounded bg-bg">
            <div
              className={`h-full ${hazardQueuePct > 80 ? "bg-danger" : hazardQueuePct > 50 ? "bg-warn" : "bg-ok"}`}
              style={{ width: `${hazardQueuePct}%` }}
            />
          </div>
        </div>

        <div>
          <div className="flex items-baseline justify-between">
            <span className="text-[10px] uppercase tracking-wider text-text-secondary">
              ledger queue
            </span>
            <span className="font-mono text-sm text-text-primary">
              {saturation.ledger_queue_depth} / {saturation.ledger_queue_max}
            </span>
          </div>
          <div className="mt-1 h-1.5 w-full overflow-hidden rounded bg-bg">
            <div
              className={`h-full ${ledgerQueuePct > 80 ? "bg-danger" : ledgerQueuePct > 50 ? "bg-warn" : "bg-ok"}`}
              style={{ width: `${ledgerQueuePct}%` }}
            />
          </div>
        </div>

        <div>
          <div className="flex items-baseline justify-between">
            <span className="text-[10px] uppercase tracking-wider text-text-secondary">
              fast-risk-cache staleness
            </span>
            <span
              className={`font-mono text-sm ${
                saturation.fast_risk_cache_staleness_ms > 1000 ? "text-warn" : "text-ok"
              }`}
            >
              {saturation.fast_risk_cache_staleness_ms}ms
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

// ============================================================
// GOLDEN SIGNALS GRID
// ============================================================

export function GoldenSignalsGrid({ signals }: { signals: GoldenSignals }) {
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
      <LatencyPanel latency={signals.latency} />
      <TrafficPanel traffic={signals.traffic} />
      <ErrorsPanel errors={signals.errors} />
      <SaturationPanel saturation={signals.saturation} />
    </div>
  );
}

// ============================================================
// SLO BURN RATE PANEL
// ============================================================

export function SLOBurnRatePanel({ burnRate }: { burnRate: SLOBurnRate }) {
  const windows = [
    { label: "1h budget", value: burnRate.budget_1h_percent },
    { label: "6h budget", value: burnRate.budget_6h_percent },
    { label: "24h budget", value: burnRate.budget_24h_percent },
  ];

  return (
    <div className="rounded border border-border bg-surface p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold">SLO Burn Rate (Multi-Window Error Budget)</h3>
        <span className="text-[10px] text-text-secondary">
          Alert threshold: {burnRate.alert_threshold_percent}%
        </span>
      </div>

      <div className="space-y-3">
        {windows.map(({ label, value }) => {
          const isAlerting = 100 - value < burnRate.alert_threshold_percent;
          return (
            <div key={label}>
              <div className="flex items-baseline justify-between">
                <span className="text-[10px] uppercase tracking-wider text-text-secondary">
                  {label}
                </span>
                <div className="flex items-center gap-2">
                  <span
                    className={`font-mono text-sm ${
                      isAlerting ? "text-danger" : "text-ok"
                    }`}
                  >
                    {value.toFixed(1)}%
                  </span>
                  {isAlerting && (
                    <span className="text-[10px] font-medium text-danger">PAGE</span>
                  )}
                </div>
              </div>
              <div className="mt-1 h-2 w-full overflow-hidden rounded bg-bg">
                <div
                  className={`h-full transition-all ${
                    isAlerting ? "bg-danger" : value > 70 ? "bg-warn" : "bg-ok"
                  }`}
                  style={{ width: `${value}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>

      <div className="mt-2 text-[10px] text-text-secondary">
        Alert: {">"}{burnRate.alert_threshold_percent}% burn = PAGE
      </div>
    </div>
  );
}

// ============================================================
// HAZARD EVENT FEED
// ============================================================

function severityCls(severity: HazardSeverity) {
  switch (severity) {
    case "CRITICAL":
      return "text-danger bg-danger/10 border-danger/30";
    case "WARNING":
      return "text-warn bg-warn/10 border-warn/30";
    case "INFO":
    default:
      return "text-info bg-info/10 border-info/30";
  }
}

function statusBadge(status: SystemHazard["status"]) {
  switch (status) {
    case "escalated":
      return "text-danger";
    case "pending":
      return "text-warn";
    case "resolved":
      return "text-ok";
    default:
      return "text-text-secondary";
  }
}

export function HazardEventFeed({ hazards }: { hazards: SystemHazard[] }) {
  if (hazards.length === 0) {
    return (
      <div className="rounded border border-border bg-surface p-4">
        <h3 className="mb-2 text-sm font-semibold">
          SYSTEM_HAZARD Events (DYON to GOVERNANCE escalation)
        </h3>
        <p className="text-sm text-text-secondary">No active hazards</p>
      </div>
    );
  }

  return (
    <div className="rounded border border-border bg-surface p-4">
      <h3 className="mb-3 text-sm font-semibold">
        SYSTEM_HAZARD Events (DYON to GOVERNANCE escalation)
      </h3>
      <ul className="space-y-2">
        {hazards.map((hazard) => (
          <li
            key={hazard.id}
            className={`flex items-start gap-3 rounded border px-3 py-2 ${severityCls(hazard.severity)}`}
          >
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <span className="font-mono text-[10px] uppercase">{hazard.severity}</span>
                <span className={`text-[10px] ${statusBadge(hazard.status)}`}>
                  ({hazard.status})
                </span>
              </div>
              <p className="mt-0.5 text-sm">{hazard.message}</p>
              <span className="mt-1 block font-mono text-[10px] opacity-70">
                {hazard.timestamp_utc}
                {hazard.ledger_seq && ` · seq ${hazard.ledger_seq}`}
              </span>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

// ============================================================
// SIGNALS PAGE
// ============================================================

export function SignalsPage() {
  const {
    data: signals,
    isPending: signalsPending,
    isError: signalsError,
    error: signalsErr,
    refetch: refetchSignals,
    isFetching: signalsFetching,
  } = useQuery({
    queryKey: ["golden-signals"],
    queryFn: ({ signal }) => fetchGoldenSignals(signal),
    refetchInterval: 2_000,
  });

  const { data: slo } = useQuery({
    queryKey: ["slo-burn-rate"],
    queryFn: ({ signal }) => fetchSLOBurnRate(signal),
    refetchInterval: 5_000,
  });

  const { data: hazards } = useQuery({
    queryKey: ["system-hazards"],
    queryFn: ({ signal }) => fetchSystemHazards(signal),
    refetchInterval: 3_000,
  });

  return (
    <section className="flex h-full flex-col">
      <header className="mb-4 flex items-baseline justify-between">
        <div>
          <h1 className="text-lg font-semibold tracking-tight">
            DYON System Intelligence{" "}
            <span className="ml-2 rounded border border-border bg-bg px-2 py-0.5 font-mono text-[11px] uppercase tracking-widest text-text-secondary">
              LIVE
            </span>
          </h1>
          <p className="mt-1 text-xs text-text-secondary">
            Four Golden Signals, SLO burn rate, and SYSTEM_HAZARD event feed.
            Observes infrastructure health per Google SRE methodology.
          </p>
        </div>
        <button
          type="button"
          onClick={() => refetchSignals()}
          disabled={signalsFetching}
          className="rounded border border-border bg-surface px-3 py-1.5 text-xs hover:border-accent disabled:opacity-50"
        >
          {signalsFetching ? "refreshing..." : "refresh"}
        </button>
      </header>

      {signalsPending && <p className="text-sm text-text-secondary">Loading...</p>}

      {signalsError && (
        <div className="rounded border border-danger/40 bg-danger/10 p-3 text-sm text-danger">
          {(signalsErr as Error).message}
        </div>
      )}

      {signals && (
        <div className="space-y-6 overflow-auto pb-6">
          <div>
            <h2 className="mb-3 text-sm font-medium text-text-secondary">Four Golden Signals</h2>
            <GoldenSignalsGrid signals={signals} />
          </div>

          {slo && (
            <div>
              <SLOBurnRatePanel burnRate={slo} />
            </div>
          )}

          {hazards && (
            <div>
              <HazardEventFeed hazards={hazards} />
            </div>
          )}
        </div>
      )}
    </section>
  );
}
