import { useEffect, useState } from "react";

import { AlertOctagon, Cpu, GitMerge, Map, Radio, Wrench, Zap } from "lucide-react";

import { useCognitiveStream } from "@/state/cognitive_realtime";

/**
 * DYON Architecture Observability Stream (BUILD-DIRECTIVE §P0-COG).
 *
 * Real-time feed of DYON's engineering cognition events:
 *   TOPOLOGY_DRIFT        — declared vs actual topology divergence
 *   ARCHITECTURAL_DRIFT   — invariant violation (INV-15, B1, INV-08…)
 *   DEPENDENCY_ANOMALY    — forbidden import, circular dep, B1 violation
 *   RUNTIME_ANOMALY       — subsystem health deviation
 *   PATCH_PROPOSAL        — proposed structural mutations awaiting governance
 *   REPAIR_PIPELINE       — stage-by-stage repair pipeline progress
 *
 * Backend: GET /api/cognitive/dyon/stream (SSE / WS fan-out of
 * state.ledger SYSTEM event stream filtered by source=DYON).
 *
 * Seeded deterministically so the panel is informative before
 * the live stream is wired.
 */
type EventKind =
  | "TOPOLOGY_DRIFT"
  | "ARCHITECTURAL_DRIFT"
  | "DEPENDENCY_ANOMALY"
  | "RUNTIME_ANOMALY"
  | "PATCH_PROPOSAL"
  | "REPAIR_PIPELINE";

type Severity = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "INFO";

interface DyonEvent {
  id: string;
  kind: EventKind;
  ts_iso: string;
  summary: string;
  severity: Severity;
  module?: string;
  status?: string;
  detail?: string;
}

const SEED: DyonEvent[] = [
  {
    id: "pp-120",
    kind: "PATCH_PROPOSAL",
    ts_iso: "20:14:08",
    summary: "patch-120: raise ledger hot-ring compaction trigger 70% → 85%",
    severity: "LOW",
    module: "core/ledger/hot_ring",
    status: "AWAITING_APPROVAL",
    detail: "patch_kind: REFACTOR · risk_level: LOW · governance: PROPOSED",
  },
  {
    id: "ra-001",
    kind: "RUNTIME_ANOMALY",
    ts_iso: "20:13:52",
    summary: "execution_engine.hot_path: p99 ack latency 142ms (target ≤ 100ms)",
    severity: "MEDIUM",
    module: "execution_engine.hot_path",
    detail: "auto_repair_triggered: true · repair: patch-118 queued",
  },
  {
    id: "ad-001",
    kind: "ARCHITECTURAL_DRIFT",
    ts_iso: "20:13:40",
    summary: "INV-15 drift: wall-clock leak detected in learning_engine.lanes.ewc",
    severity: "HIGH",
    module: "learning_engine.lanes.ewc",
    detail: "invariant: INV-15 · affected: learning_engine.lanes.ewc, learning_engine.meta · recommended: extract clock to injection seam",
  },
  {
    id: "rp-001",
    kind: "REPAIR_PIPELINE",
    ts_iso: "20:13:28",
    summary: "Repair pipeline patch-119: SANDBOX stage → STATIC_ANALYSIS",
    severity: "INFO",
    module: "intelligence_engine/regime_router",
    status: "IN_PROGRESS",
    detail: "pipeline_id: repair-019 · stage: STATIC_ANALYSIS · outcome: IN_PROGRESS",
  },
  {
    id: "da-001",
    kind: "DEPENDENCY_ANOMALY",
    ts_iso: "20:13:15",
    summary: "B1 violation: system_monitor.hazard_bus importing execution.adapters",
    severity: "CRITICAL",
    module: "system_monitor.hazard_bus",
    detail: "anomaly_kind: FORBIDDEN · source: system_monitor.hazard_bus · target: execution.adapters.kraken",
  },
  {
    id: "td-001",
    kind: "TOPOLOGY_DRIFT",
    ts_iso: "20:13:02",
    summary: "runtime/fabric/fill_reconciler declared HEALTHY but not reachable via active loop",
    severity: "MEDIUM",
    module: "runtime.fabric.fill_reconciler",
    detail: "expected: HEALTHY · actual: DORMANT · recommended: wire into execution tick or mark DECLARED_BUT_DORMANT",
  },
  {
    id: "rp-002",
    kind: "REPAIR_PIPELINE",
    ts_iso: "20:12:50",
    summary: "Repair pipeline patch-118: SANDBOX complete → AWAITING_APPROVAL",
    severity: "INFO",
    module: "execution_engine/hot_path",
    status: "COMPLETED",
    detail: "pipeline_id: repair-018 · stage: AWAITING_APPROVAL · outcome: SUCCESS",
  },
  {
    id: "pp-119",
    kind: "PATCH_PROPOSAL",
    ts_iso: "20:12:38",
    summary: "patch-119: tighten regime hysteresis band 0.6 → 0.45 for vol regime",
    severity: "MEDIUM",
    module: "intelligence_engine/regime_router",
    status: "SANDBOX",
    detail: "patch_kind: PARAMETER · risk_level: MEDIUM · governance: SIMULATED",
  },
];

const KIND_META: Record<EventKind, { icon: typeof Cpu; label: string; color: string }> = {
  TOPOLOGY_DRIFT:     { icon: Map,         label: "Topology",     color: "text-sky-400" },
  ARCHITECTURAL_DRIFT:{ icon: AlertOctagon, label: "Arch Drift",  color: "text-rose-400" },
  DEPENDENCY_ANOMALY: { icon: Zap,          label: "Dep Anomaly", color: "text-amber-400" },
  RUNTIME_ANOMALY:    { icon: Cpu,          label: "Runtime",     color: "text-orange-400" },
  PATCH_PROPOSAL:     { icon: Wrench,       label: "Patch",       color: "text-violet-400" },
  REPAIR_PIPELINE:    { icon: GitMerge,     label: "Repair",      color: "text-teal-400" },
};

const SEV_COLOR: Record<Severity, string> = {
  CRITICAL: "text-rose-500",
  HIGH:     "text-rose-400",
  MEDIUM:   "text-amber-400",
  LOW:      "text-slate-400",
  INFO:     "text-slate-500",
};

type Filter = EventKind | "ALL";

export function DyonArchitectureStream() {
  const [events, setEvents] = useState<DyonEvent[]>(SEED);
  const [filter, setFilter] = useState<Filter>("ALL");
  const [expanded, setExpanded] = useState<string | null>(null);

  // Live SSE from /api/cognitive/stream channel "dyon"
  const { events: liveEvents, live } = useCognitiveStream<Record<string, unknown>>("dyon", 200);
  useEffect(() => {
    if (liveEvents.length === 0) return;
    const row = liveEvents[liveEvents.length - 1];
    // SSE frame: {channel, ts_iso, payload: <db-row>}
    // db-row: {sub_type, source, payload: <dyon-event-fields>, ...}
    // DYON event fields live one level deeper inside row.payload.
    const kind = (row.sub_type ?? row.kind ?? "RUNTIME_ANOMALY") as EventKind;
    if (!(kind in KIND_META)) return;
    const p = (row.payload ?? {}) as Record<string, unknown>;
    const now = new Date();
    const ts = `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}:${String(now.getSeconds()).padStart(2, "0")}`;
    setEvents((prev) => [
      {
        id: String(p.drift_id ?? p.anomaly_id ?? p.proposal_id ?? p.pipeline_id ?? Date.now()),
        kind,
        ts_iso: ts,
        summary: String(p.description ?? p.violation_description ?? p.summary ?? kind),
        severity: (p.severity ?? p.drift_severity ?? "INFO") as Severity,
        module: p.module ? String(p.module) : p.target_module ? String(p.target_module) : p.subsystem ? String(p.subsystem) : undefined,
        status: p.governance_status ? String(p.governance_status) : p.outcome ? String(p.outcome) : undefined,
        detail: p.recommended_action ? `recommended: ${p.recommended_action}` : p.rationale ? `rationale: ${p.rationale}` : undefined,
      },
      ...prev.slice(0, 49),
    ]);
  }, [liveEvents]);

  // Simulation fallback when SSE not connected
  useEffect(() => {
    if (live) return;
    let seq = SEED.length;
    const ROTATING: Array<Pick<DyonEvent, "kind" | "severity" | "summary" | "module">> = [
      { kind: "RUNTIME_ANOMALY",     severity: "LOW",    summary: "state.ledger.event_store: write latency p50 18ms → 12ms (improved)", module: "state.ledger.event_store" },
      { kind: "TOPOLOGY_DRIFT",      severity: "MEDIUM", summary: "evolution_engine.structural_loop: DECLARED but not invoked in boot", module: "evolution_engine.structural_loop" },
      { kind: "REPAIR_PIPELINE",     severity: "INFO",   summary: "Repair pipeline patch-121: DIAGNOSIS → PROPOSAL", module: "core.ledger.hot_ring" },
      { kind: "ARCHITECTURAL_DRIFT", severity: "HIGH",   summary: "INV-08 drift: MutationTrace missing frozen=True in learning_engine.meta", module: "learning_engine.meta" },
    ];
    const id = setInterval(() => {
      const rot = ROTATING[seq % ROTATING.length];
      const now = new Date();
      const ts = `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}:${String(now.getSeconds()).padStart(2, "0")}`;
      setEvents((prev) => [
        { id: `sim-${seq}`, ts_iso: ts, ...rot },
        ...prev.slice(0, 49),
      ]);
      seq += 1;
    }, 8_000);
    return () => clearInterval(id);
  }, [live]);

  const visible =
    filter === "ALL" ? events : events.filter((e) => e.kind === filter);

  return (
    <section className="flex h-full flex-col rounded border border-border bg-surface">
      <header className="flex items-baseline justify-between border-b border-border px-3 py-2">
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-300">
            DYON · Architecture Stream
          </h3>
          <p className="mt-0.5 text-[11px] text-slate-500">
            topology · drift · anomalies · patches · repair pipelines
          </p>
        </div>
        <div className="flex items-center gap-1.5">
          <Radio className={`h-3 w-3 ${live ? "text-emerald-400" : "text-slate-600"}`} />
          <span className="rounded border border-teal-500/40 bg-teal-500/10 px-1.5 py-0.5 font-mono text-[10px] text-teal-300">
            {live ? "LIVE" : "SIM"}
          </span>
        </div>
      </header>

      {/* Filter bar */}
      <div className="flex flex-wrap gap-1 border-b border-border/60 bg-bg/50 px-2 py-1.5">
        {(["ALL", ...Object.keys(KIND_META)] as Filter[]).map((k) => {
          const meta = k !== "ALL" ? KIND_META[k as EventKind] : null;
          return (
            <button
              key={k}
              type="button"
              onClick={() => setFilter(k)}
              className={`rounded border px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider ${
                filter === k
                  ? "border-accent/40 bg-accent/10 text-accent"
                  : "border-border bg-bg/40 text-slate-500 hover:text-slate-300"
              }`}
            >
              {meta ? meta.label : "All"}
            </button>
          );
        })}
      </div>

      {/* Event list */}
      <div className="flex-1 overflow-auto divide-y divide-border/40">
        {visible.map((ev) => {
          const meta = KIND_META[ev.kind];
          const Icon = meta.icon;
          const open = expanded === ev.id;
          return (
            <button
              key={ev.id}
              type="button"
              onClick={() => setExpanded(open ? null : ev.id)}
              className="w-full px-3 py-2 text-left hover:bg-bg/60"
            >
              <div className="flex items-start gap-2">
                <Icon className={`mt-0.5 h-3 w-3 flex-shrink-0 ${meta.color}`} />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-1.5">
                      <span className={`font-mono text-[10px] uppercase ${meta.color}`}>
                        {meta.label}
                      </span>
                      <span className={`font-mono text-[10px] uppercase ${SEV_COLOR[ev.severity]}`}>
                        {ev.severity}
                      </span>
                    </div>
                    <span className="font-mono text-[10px] text-slate-600">{ev.ts_iso}</span>
                  </div>
                  <p className="mt-0.5 text-[11px] text-slate-300 leading-snug">{ev.summary}</p>
                  {ev.module && (
                    <span className="mt-0.5 font-mono text-[10px] text-slate-600">
                      {ev.module}
                    </span>
                  )}
                  {ev.status && (
                    <span
                      className={`ml-2 font-mono text-[10px] ${
                        ev.status === "AWAITING_APPROVAL"
                          ? "text-amber-400"
                          : ev.status === "COMPLETED" || ev.status === "MERGED"
                            ? "text-emerald-400"
                            : ev.status === "FAILED" || ev.status === "REVERTED"
                              ? "text-rose-400"
                              : "text-slate-500"
                      }`}
                    >
                      {ev.status}
                    </span>
                  )}
                  {open && ev.detail && (
                    <p className="mt-1.5 rounded bg-bg/60 px-2 py-1 font-mono text-[10px] text-slate-400 leading-relaxed">
                      {ev.detail}
                    </p>
                  )}
                </div>
              </div>
            </button>
          );
        })}
      </div>
    </section>
  );
}
