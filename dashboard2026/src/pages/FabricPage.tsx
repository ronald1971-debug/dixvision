import { useEffect, useRef, useState } from "react";

import { Radio } from "lucide-react";

import {
  fetchFabricAuthority,
  fetchFabricBridges,
  fetchFabricEvents,
  fetchFabricLineage,
  fetchFabricPersistence,
  fetchFabricTracing,
  type ActiveTrace,
  type BridgeStatusRecord,
  type CausalLinkRecord,
  type FabricAuthorityResponse,
  type FabricEvent,
  type FabricLineageResponse,
  type FabricPersistenceResponse,
  type FabricTracingResponse,
  type SpanRecord,
} from "@/api/fabric";

// ─── Helpers ──────────────────────────────────────────────────────────────────

function Bar({
  pct,
  color = "bg-sky-500",
  h = "h-1.5",
}: {
  pct: number;
  color?: string;
  h?: string;
}) {
  return (
    <div className={`w-full rounded-full bg-slate-700/60 ${h}`}>
      <div
        className={`${h} rounded-full ${color}`}
        style={{ width: `${Math.max(2, Math.min(100, pct))}%` }}
      />
    </div>
  );
}

function Dot({ active }: { active: boolean }) {
  return (
    <span
      className={`inline-block h-2 w-2 rounded-full ${active ? "bg-emerald-400" : "bg-slate-600"}`}
    />
  );
}

function PanelWrap({
  title,
  sub,
  accent = "sky",
  children,
}: {
  title: string;
  sub: string;
  accent?: "violet" | "teal" | "amber" | "sky";
  children: React.ReactNode;
}) {
  const borderMap = {
    violet: "border-violet-900/50",
    teal: "border-teal-900/50",
    amber: "border-amber-900/50",
    sky: "border-sky-900/50",
  };
  const textMap = {
    violet: "text-violet-400",
    teal: "text-teal-400",
    amber: "text-amber-400",
    sky: "text-sky-400",
  };
  return (
    <div
      className={`flex h-full flex-col overflow-hidden rounded border ${borderMap[accent]} bg-surface`}
    >
      <div className="flex-shrink-0 border-b border-border/50 px-2.5 py-1.5">
        <p
          className={`font-mono text-[10px] uppercase tracking-widest ${textMap[accent]}`}
        >
          {title}
        </p>
        <p className="text-[10px] text-slate-600">{sub}</p>
      </div>
      <div className="min-h-0 flex-1 overflow-auto p-2">{children}</div>
    </div>
  );
}

// ─── Domain colours ───────────────────────────────────────────────────────────

const DOMAIN_COLOR: Record<string, string> = {
  COGNITIVE:   "text-violet-400",
  GOVERNANCE:  "text-amber-400",
  EXECUTION:   "text-emerald-400",
  MARKET:      "text-sky-400",
  SIMULATION:  "text-teal-400",
  LEARNING:    "text-blue-400",
  TELEMETRY:   "text-slate-400",
  SYSTEM:      "text-orange-400",
  MEMORY:      "text-violet-300",
  EVOLUTION:   "text-green-400",
  RESEARCH:    "text-cyan-400",
  UI:          "text-pink-400",
  AUDIT:       "text-rose-400",
  UNKNOWN:     "text-slate-600",
};

const DOMAIN_BAR: Record<string, string> = {
  COGNITIVE:   "bg-violet-700",
  GOVERNANCE:  "bg-amber-700",
  EXECUTION:   "bg-emerald-700",
  MARKET:      "bg-sky-700",
  SIMULATION:  "bg-teal-700",
  LEARNING:    "bg-blue-700",
  TELEMETRY:   "bg-slate-600",
  SYSTEM:      "bg-orange-700",
  MEMORY:      "bg-violet-800",
  EVOLUTION:   "bg-green-700",
  RESEARCH:    "bg-cyan-800",
  UI:          "bg-pink-800",
  AUDIT:       "bg-rose-800",
  UNKNOWN:     "bg-slate-700",
};

function DomainBadge({ domain }: { domain: string }) {
  return (
    <span className={`font-mono text-[9px] uppercase ${DOMAIN_COLOR[domain] ?? "text-slate-500"}`}>
      {domain.slice(0, 4)}
    </span>
  );
}

function nsToTs(ts_ns: number): string {
  if (!ts_ns) return "–";
  return new Date(ts_ns / 1_000_000).toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

// ─── Seed data ────────────────────────────────────────────────────────────────

const SEED_AUTHORITY: FabricAuthorityResponse = {
  published: 1847,
  routed: 1843,
  failed: 4,
  subscriber_count: 14,
  sequence: 1847,
  subscriptions: {
    "COGNITIVE.*":   8,
    "GOVERNANCE.*":  2,
    "EXECUTION.*":   2,
    "MEMORY.*":      1,
    "SYSTEM.*":      1,
  },
};

const SEED_TRACING: FabricTracingResponse = {
  span_count: 412,
  trace_count: 38,
  active_traces: [
    { trace_id: "tr-a1b2c3d4", span_count: 5, domains: ["COGNITIVE", "MEMORY", "GOVERNANCE"] },
    { trace_id: "tr-e5f6a7b8", span_count: 3, domains: ["EXECUTION", "MARKET"] },
    { trace_id: "tr-c9d0e1f2", span_count: 2, domains: ["SIMULATION", "LEARNING"] },
  ],
  recent_spans: [
    { span_id: "sp-0001", trace_id: "tr-a1b2c3d4", parent_span_id: "", event_id: "uf-cog-0001", domain: "COGNITIVE", event_type: "INDIRA_THOUGHT", ts_ns: 0, source: "IndiraRuntime" },
    { span_id: "sp-0002", trace_id: "tr-a1b2c3d4", parent_span_id: "sp-0001", event_id: "uf-mem-0002", domain: "MEMORY", event_type: "MEMORY_WRITE", ts_ns: 0, source: "MemoryCoordinator" },
    { span_id: "sp-0003", trace_id: "tr-e5f6a7b8", parent_span_id: "", event_id: "uf-exe-0003", domain: "EXECUTION", event_type: "SIGNAL_GENERATED", ts_ns: 0, source: "SignalEngine" },
  ],
};

const SEED_LINEAGE: FabricLineageResponse = {
  node_count: 124,
  link_count: 89,
  recent_links: [
    { cause_id: "uf-cog-0001", effect_id: "uf-mem-0002", ts_ns: 0, kind: "produces" },
    { cause_id: "uf-cog-0001", effect_id: "uf-gov-0003", ts_ns: 0, kind: "triggers" },
    { cause_id: "uf-exe-0004", effect_id: "uf-tel-0005", ts_ns: 0, kind: "emits" },
  ],
};

const SEED_PERSISTENCE: FabricPersistenceResponse = {
  active: true,
  appended_session: 412,
  persisted_total: 8247,
  db_path: "data/unified_fabric.db",
  domain_counts: {
    COGNITIVE: 3847,
    GOVERNANCE: 412,
    EXECUTION: 1204,
    MARKET: 892,
    SIMULATION: 643,
    MEMORY: 389,
    TELEMETRY: 287,
    SYSTEM: 573,
  },
};

const SEED_BRIDGES = {
  cognitive: { active: true, forwarded: 1247, failed: 2, channels: ["thought", "insight", "research", "proposal", "risk_breach", "archetype_evolution", "causal_hypothesis", "market_intelligence"] },
  execution: { active: true, forwarded: 600,  failed: 0, channels: ["signal", "fill", "risk_event", "strategy_state", "order_update", "market_data"] },
};

const SEED_EVENTS: FabricEvent[] = [
  { event_id: "uf-cog-abc1", sequence: 1847, domain: "COGNITIVE", event_type: "INDIRA_THOUGHT", ts_ns: 0, source: "IndiraRuntime", priority: 2, trace_id: "tr-a1b2c3d4", parent_id: "", tags: "[]", payload: "{}" },
  { event_id: "uf-mem-def2", sequence: 1848, domain: "MEMORY", event_type: "MEMORY_WRITE", ts_ns: 0, source: "MemoryCoordinator", priority: 2, trace_id: "tr-a1b2c3d4", parent_id: "uf-cog-abc1", tags: "[]", payload: "{}" },
  { event_id: "uf-gov-ghi3", sequence: 1849, domain: "GOVERNANCE", event_type: "MODE_TRANSITION", ts_ns: 0, source: "GovernanceRouter", priority: 1, trace_id: "tr-b2c3d4e5", parent_id: "", tags: "[]", payload: "{}" },
  { event_id: "uf-exe-jkl4", sequence: 1850, domain: "EXECUTION", event_type: "SIGNAL_GENERATED", ts_ns: 0, source: "SignalEngine", priority: 2, trace_id: "tr-e5f6a7b8", parent_id: "", tags: "[]", payload: "{}" },
  { event_id: "uf-sim-mno5", sequence: 1851, domain: "SIMULATION", event_type: "TOURNAMENT_COMPLETE", ts_ns: 0, source: "SimulationEngine", priority: 2, trace_id: "tr-c9d0e1f2", parent_id: "", tags: "[]", payload: "{}" },
];

// ─── Tab type ─────────────────────────────────────────────────────────────────

type Tab = "events" | "traces" | "lineage" | "system";

// ─── Panel components ─────────────────────────────────────────────────────────

function AuthorityPanel({ auth }: { auth: FabricAuthorityResponse }) {
  const successRate =
    auth.published && auth.published > 0
      ? (((auth.routed ?? 0) / auth.published) * 100).toFixed(1)
      : "100.0";

  return (
    <PanelWrap title="FABRIC · BUS AUTHORITY" sub="central router · publish/route stats" accent="sky">
      <div className="mb-2 grid grid-cols-3 gap-1.5">
        {[
          { label: "published", val: auth.published, color: "text-sky-300" },
          { label: "routed",    val: auth.routed,    color: "text-emerald-300" },
          { label: "failed",    val: auth.failed,    color: (auth.failed ?? 0) > 0 ? "text-rose-300" : "text-slate-500" },
        ].map(({ label, val, color }) => (
          <div key={label} className="rounded border border-border/40 bg-bg/30 px-2 py-1 text-center">
            <p className={`font-mono text-[11px] font-semibold ${color}`}>{val?.toLocaleString() ?? "–"}</p>
            <p className="font-mono text-[9px] text-slate-600">{label}</p>
          </div>
        ))}
      </div>
      <div className="mb-1.5">
        <div className="flex justify-between font-mono text-[10px]">
          <span className="text-slate-500">route success</span>
          <span className="text-emerald-300">{successRate}%</span>
        </div>
        <Bar pct={parseFloat(successRate)} color="bg-emerald-600" />
      </div>
      <div className="mt-1.5">
        <p className="mb-1 font-mono text-[9px] text-slate-600">
          {auth.subscriber_count ?? 0} subscribers · seq #{auth.sequence?.toLocaleString() ?? 0}
        </p>
      </div>
    </PanelWrap>
  );
}

function BridgesPanel({
  cognitive,
  execution,
}: {
  cognitive: BridgeStatusRecord | undefined;
  execution: BridgeStatusRecord | undefined;
}) {
  const bridges = [
    { name: "Cognitive Bus Bridge", b: cognitive, accent: "violet" as const },
    { name: "Execution Fabric Bridge", b: execution, accent: "teal" as const },
  ];
  return (
    <PanelWrap title="FABRIC · BRIDGES" sub="non-destructive bus adapters" accent="teal">
      <div className="space-y-2">
        {bridges.map(({ name, b, accent }) => {
          const successRate =
            b?.forwarded && b.forwarded > 0
              ? (((b.forwarded - (b.failed ?? 0)) / b.forwarded) * 100).toFixed(1)
              : "100.0";
          const textMap = { violet: "text-violet-300", teal: "text-teal-300" };
          return (
            <div key={name} className="rounded border border-border/40 bg-bg/30 px-2 py-1.5">
              <div className="mb-1 flex items-center gap-1.5">
                <Dot active={b?.active ?? false} />
                <span className={`font-mono text-[10px] font-semibold ${textMap[accent]}`}>
                  {name}
                </span>
              </div>
              <div className="flex gap-4 font-mono text-[9px]">
                <span className="text-slate-400">{b?.forwarded?.toLocaleString() ?? 0} fwd</span>
                <span className={b?.failed ? "text-rose-400" : "text-slate-600"}>
                  {b?.failed ?? 0} err
                </span>
                <span className="text-emerald-400">{successRate}%</span>
              </div>
              {b?.channels && (
                <p className="mt-0.5 truncate font-mono text-[9px] text-slate-700">
                  {b.channels.length} channels
                </p>
              )}
            </div>
          );
        })}
      </div>
    </PanelWrap>
  );
}

function PersistencePanel({ persistence }: { persistence: FabricPersistenceResponse }) {
  const counts = persistence.domain_counts ?? {};
  const maxVal = Math.max(...Object.values(counts), 1);
  const topDomains = Object.entries(counts)
    .sort(([, a], [, b]) => b - a)
    .slice(0, 8);

  return (
    <PanelWrap title="FABRIC · PERSISTENCE" sub="SQLite WAL · event_id PRIMARY KEY" accent="amber">
      <div className="mb-2 flex gap-3 font-mono text-[10px]">
        <span className="text-slate-300">{persistence.persisted_total?.toLocaleString() ?? "–"} total</span>
        <span className="text-slate-500">+{persistence.appended_session ?? 0} session</span>
      </div>
      <div className="mb-1 space-y-1">
        {topDomains.map(([domain, count]) => (
          <div key={domain} className="flex items-center gap-2">
            <span className={`w-20 flex-shrink-0 font-mono text-[9px] ${DOMAIN_COLOR[domain] ?? "text-slate-500"}`}>
              {domain}
            </span>
            <div className="flex-1">
              <Bar pct={(count / maxVal) * 100} color={DOMAIN_BAR[domain] ?? "bg-slate-600"} h="h-1.5" />
            </div>
            <span className="w-10 flex-shrink-0 text-right font-mono text-[9px] text-slate-600">
              {count.toLocaleString()}
            </span>
          </div>
        ))}
      </div>
      <p className="mt-1 truncate font-mono text-[9px] text-slate-700">
        {persistence.db_path ?? "–"}
      </p>
    </PanelWrap>
  );
}

function EventStreamPanel({ events }: { events: FabricEvent[] }) {
  const PRIORITY_LABEL: Record<number, string> = { 0: "CRIT", 1: "HIGH", 2: "NORM", 3: "LOW" };
  const PRIORITY_COLOR: Record<number, string> = {
    0: "text-rose-400",
    1: "text-amber-400",
    2: "text-slate-500",
    3: "text-slate-600",
  };

  return (
    <PanelWrap title="FABRIC · EVENT STREAM" sub="paginated WAL log · newest first" accent="sky">
      <div className="space-y-1">
        {events.length === 0 && (
          <p className="py-4 text-center text-[11px] text-slate-600">No events</p>
        )}
        {[...events].reverse().map((e) => (
          <div
            key={e.event_id}
            className="flex items-start gap-1.5 rounded border border-border/30 bg-bg/30 px-1.5 py-1"
          >
            <DomainBadge domain={e.domain} />
            <div className="min-w-0 flex-1">
              <div className="flex items-baseline gap-1.5">
                <span className="truncate font-mono text-[10px] text-slate-200">{e.event_type}</span>
                <span className={`flex-shrink-0 font-mono text-[9px] ${PRIORITY_COLOR[e.priority] ?? "text-slate-500"}`}>
                  {PRIORITY_LABEL[e.priority] ?? e.priority}
                </span>
              </div>
              <div className="flex gap-2">
                <span className="font-mono text-[9px] text-slate-600">{e.source}</span>
                {e.trace_id && (
                  <span className="font-mono text-[9px] text-slate-700" title={e.trace_id}>
                    {e.trace_id.slice(0, 12)}…
                  </span>
                )}
              </div>
            </div>
            <span className="flex-shrink-0 font-mono text-[9px] text-slate-700">#{e.sequence}</span>
          </div>
        ))}
      </div>
    </PanelWrap>
  );
}

function TracingPanel({ tracing }: { tracing: FabricTracingResponse }) {
  const actives = tracing.active_traces ?? [];
  const spans = (tracing.recent_spans ?? []).slice(0, 8);

  return (
    <PanelWrap title="FABRIC · TRACE VIEWER" sub="active multi-hop traces · recent spans" accent="violet">
      {actives.length > 0 && (
        <div className="mb-2">
          <p className="mb-1 font-mono text-[9px] uppercase text-slate-600">Active traces</p>
          <div className="space-y-1">
            {actives.map((t: ActiveTrace) => (
              <div key={t.trace_id} className="flex items-center gap-2 rounded border border-violet-900/30 bg-violet-900/10 px-1.5 py-1">
                <span className="font-mono text-[9px] text-violet-300" title={t.trace_id}>
                  {t.trace_id.slice(0, 14)}…
                </span>
                <span className="font-mono text-[9px] text-slate-600">{t.span_count}s</span>
                <div className="flex flex-1 flex-wrap gap-0.5">
                  {(t.domains ?? []).map((d) => (
                    <span key={d} className={`font-mono text-[8px] ${DOMAIN_COLOR[d] ?? "text-slate-600"}`}>
                      {d.slice(0, 3)}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
      <div>
        <p className="mb-1 font-mono text-[9px] uppercase text-slate-600">Recent spans</p>
        <div className="space-y-0.5">
          {spans.map((s: SpanRecord) => (
            <div key={s.span_id} className="flex items-center gap-1.5 py-0.5">
              <span className={`w-14 flex-shrink-0 font-mono text-[9px] ${DOMAIN_COLOR[s.domain] ?? "text-slate-500"}`}>
                {s.domain.slice(0, 4)}
              </span>
              <span className="flex-1 truncate font-mono text-[9px] text-slate-300">
                {s.event_type}
              </span>
              {s.parent_span_id && (
                <span className="flex-shrink-0 font-mono text-[8px] text-slate-700">↳</span>
              )}
            </div>
          ))}
          {spans.length === 0 && (
            <p className="text-center text-[11px] text-slate-600">No spans</p>
          )}
        </div>
      </div>
      <div className="mt-1.5 border-t border-border/40 pt-1 font-mono text-[9px] text-slate-600">
        {tracing.span_count ?? 0} spans · {tracing.trace_count ?? 0} traces total
      </div>
    </PanelWrap>
  );
}

function LineagePanel({ lineage }: { lineage: FabricLineageResponse }) {
  const links = lineage.recent_links ?? [];

  return (
    <PanelWrap title="FABRIC · CAUSALITY GRAPH" sub="directed causal links · root-cause traversal" accent="teal">
      <div className="mb-2 flex gap-4 font-mono text-[10px]">
        <span className="text-slate-400">{lineage.node_count ?? 0} nodes</span>
        <span className="text-slate-500">{lineage.link_count ?? 0} links</span>
      </div>
      <div className="space-y-1">
        {links.length === 0 && (
          <p className="py-4 text-center text-[11px] text-slate-600">No causal links</p>
        )}
        {links.map((l: CausalLinkRecord, i) => (
          <div key={i} className="flex items-center gap-1.5 rounded border border-border/30 bg-bg/30 px-1.5 py-1">
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-1 font-mono text-[9px]">
                <span className="truncate text-slate-500" title={l.cause_id}>
                  {l.cause_id.slice(0, 18)}…
                </span>
                <span className="flex-shrink-0 text-teal-600">→</span>
                <span className="truncate text-slate-400" title={l.effect_id}>
                  {l.effect_id.slice(0, 18)}…
                </span>
              </div>
              <div className="flex gap-2">
                {l.kind && (
                  <span className="font-mono text-[9px] text-teal-500">[{l.kind}]</span>
                )}
                {l.ts_ns > 0 && (
                  <span className="font-mono text-[9px] text-slate-700">{nsToTs(l.ts_ns)}</span>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </PanelWrap>
  );
}

// ─── Page state ───────────────────────────────────────────────────────────────

interface PageState {
  authority: FabricAuthorityResponse;
  tracing: FabricTracingResponse;
  lineage: FabricLineageResponse;
  persistence: FabricPersistenceResponse;
  bridges: { cognitive?: BridgeStatusRecord; execution?: BridgeStatusRecord };
  events: FabricEvent[];
  live: boolean;
  lastUpdate: number;
}

const SEED: PageState = {
  authority:   SEED_AUTHORITY,
  tracing:     SEED_TRACING,
  lineage:     SEED_LINEAGE,
  persistence: SEED_PERSISTENCE,
  bridges:     SEED_BRIDGES,
  events:      SEED_EVENTS,
  live:        false,
  lastUpdate:  Date.now(),
};

// ─── FabricPage ───────────────────────────────────────────────────────────────

export function FabricPage() {
  const [tab, setTab] = useState<Tab>("events");
  const [data, setData] = useState<PageState>(SEED);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function fetchAll() {
      const ctrl = new AbortController();
      abortRef.current = ctrl;
      const sig = ctrl.signal;

      const [authR, traceR, linR, persR, bridgeR, eventsR] =
        await Promise.allSettled([
          fetchFabricAuthority(sig),
          fetchFabricTracing(30, sig),
          fetchFabricLineage(30, sig),
          fetchFabricPersistence(sig),
          fetchFabricBridges(sig),
          fetchFabricEvents(50, 0, "", "", "", sig),
        ]);

      if (cancelled) return;

      const anyOk = [authR, traceR, linR, persR].some(
        (r) => r.status === "fulfilled",
      );

      setData((prev) => ({
        authority:   authR.status  === "fulfilled" ? authR.value          : prev.authority,
        tracing:     traceR.status === "fulfilled" ? traceR.value         : prev.tracing,
        lineage:     linR.status   === "fulfilled" ? linR.value           : prev.lineage,
        persistence: persR.status  === "fulfilled" ? persR.value          : prev.persistence,
        bridges:     bridgeR.status=== "fulfilled" ? bridgeR.value        : prev.bridges,
        events:      eventsR.status=== "fulfilled" ? (eventsR.value.events ?? prev.events) : prev.events,
        live:        anyOk,
        lastUpdate:  Date.now(),
      }));
    }

    fetchAll();
    const id = setInterval(fetchAll, 8_000);
    return () => {
      cancelled = true;
      clearInterval(id);
      abortRef.current?.abort();
    };
  }, []);

  const now = new Date(data.lastUpdate);
  const ts = `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}:${String(now.getSeconds()).padStart(2, "0")}`;

  const TABS: { key: Tab; label: string }[] = [
    { key: "events",  label: "EVENTS" },
    { key: "traces",  label: "TRACES" },
    { key: "lineage", label: "LINEAGE" },
    { key: "system",  label: "SYSTEM" },
  ];

  const PH = "h-[260px]";

  return (
    <div className="flex h-full flex-col overflow-hidden rounded border border-border bg-bg">
      {/* Header */}
      <header className="flex flex-shrink-0 items-center justify-between border-b border-border px-4 py-2">
        <div className="flex items-center gap-2.5">
          <Radio className="h-4 w-4 text-sky-400" />
          <span className="font-mono text-[11px] font-semibold uppercase tracking-widest text-slate-300">
            UNIFIED EVENT FABRIC
          </span>
          <span className="font-mono text-[10px] text-slate-600">
            · {data.authority.published?.toLocaleString() ?? "–"} published · {data.authority.subscriber_count ?? 0} subscribers
          </span>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex gap-0 rounded border border-border/60 bg-bg/40">
            {TABS.map(({ key, label }) => (
              <button
                key={key}
                type="button"
                onClick={() => setTab(key)}
                className={`border-b-2 px-3 py-1 font-mono text-[10px] uppercase tracking-wider transition-colors ${
                  tab === key
                    ? "border-sky-500 text-sky-300"
                    : "border-transparent text-slate-600 hover:text-slate-400"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-1.5">
            <span
              className={`h-1.5 w-1.5 rounded-full ${data.live ? "bg-emerald-400" : "bg-slate-600"}`}
            />
            <span
              className={`font-mono text-[10px] ${data.live ? "text-emerald-400" : "text-slate-600"}`}
            >
              {data.live ? "LIVE" : "SIM"} {ts}
            </span>
          </div>
        </div>
      </header>

      {/* Body */}
      <div className="min-h-0 flex-1 overflow-auto p-3">

        {/* EVENTS tab */}
        {tab === "events" && (
          <div className="h-full">
            <EventStreamPanel events={data.events} />
          </div>
        )}

        {/* TRACES tab */}
        {tab === "traces" && (
          <div className="h-full">
            <TracingPanel tracing={data.tracing} />
          </div>
        )}

        {/* LINEAGE tab */}
        {tab === "lineage" && (
          <div className="h-full">
            <LineagePanel lineage={data.lineage} />
          </div>
        )}

        {/* SYSTEM tab */}
        {tab === "system" && (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
            <div className={PH}>
              <AuthorityPanel auth={data.authority} />
            </div>
            <div className={PH}>
              <BridgesPanel
                cognitive={data.bridges.cognitive}
                execution={data.bridges.execution}
              />
            </div>
            <div className={PH}>
              <PersistencePanel persistence={data.persistence} />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
