import { useEffect, useRef, useState } from "react";

import { Archive, Search } from "lucide-react";

import {
  fetchMemoryLayerSnapshot,
  fetchMemoryTimeline,
  fetchMemorySearch,
  fetchMemoryIdentity,
  fetchMemoryCompression,
  fetchMemoryStrategyStore,
  fetchMemoryTraderStore,
  fetchMemoryGovernanceStore,
  fetchMemoryRuntimeStore,
  type MemorySnapshotResponse,
  type MemoryRecordEntry,
  type MemoryIdentityResponse,
  type MemoryCompressionResponse,
  type MemoryStrategyStoreResponse,
  type MemoryTraderStoreResponse,
  type MemoryGovernanceStoreResponse,
  type MemoryRuntimeStoreResponse,
  type StoreMiniRecord,
} from "@/api/memory";

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
  accent = "violet",
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

// ─── Kind colours ─────────────────────────────────────────────────────────────

const KIND_COLOR: Record<string, string> = {
  EPISODIC: "border-sky-500/40 bg-sky-500/10 text-sky-300",
  SEMANTIC: "border-violet-500/40 bg-violet-500/10 text-violet-300",
  PROCEDURAL: "border-teal-500/40 bg-teal-500/10 text-teal-300",
  STRATEGY: "border-emerald-500/40 bg-emerald-500/10 text-emerald-300",
  TRADER: "border-amber-500/40 bg-amber-500/10 text-amber-300",
  GOVERNANCE: "border-orange-500/40 bg-orange-500/10 text-orange-300",
  RUNTIME: "border-slate-500/40 bg-slate-600/20 text-slate-400",
  REGRET: "border-rose-500/40 bg-rose-500/10 text-rose-300",
};

const KIND_BAR: Record<string, string> = {
  EPISODIC: "bg-sky-700",
  SEMANTIC: "bg-violet-700",
  PROCEDURAL: "bg-teal-700",
  STRATEGY: "bg-emerald-700",
  TRADER: "bg-amber-700",
  GOVERNANCE: "bg-orange-700",
  RUNTIME: "bg-slate-600",
  REGRET: "bg-rose-800",
};

const KIND_ORDER = [
  "EPISODIC",
  "SEMANTIC",
  "PROCEDURAL",
  "STRATEGY",
  "TRADER",
  "GOVERNANCE",
  "RUNTIME",
  "REGRET",
] as const;

function KindBadge({ kind }: { kind: string }) {
  return (
    <span
      className={`flex-shrink-0 rounded border px-1 font-mono text-[8px] uppercase ${KIND_COLOR[kind] ?? "border-slate-600/40 text-slate-500"}`}
    >
      {kind.slice(0, 3)}
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

// ─── Seed ─────────────────────────────────────────────────────────────────────

const SEED_RECORDS: MemoryRecordEntry[] = [
  { record_id: "m1", kind: "EPISODIC", ts_ns: 0, source: "IndiraRuntime", summary: "BTC regime detected as TRENDING — funding 0.012%, OI +4.2%", confidence: 0.72 },
  { record_id: "m2", kind: "SEMANTIC", ts_ns: 0, source: "MemoryCompressor", summary: "Compressed 5 episodic regime-detection events → regime_bull_consensus", confidence: 0.68 },
  { record_id: "m3", kind: "STRATEGY", ts_ns: 0, source: "StrategyMemoryStore", summary: "vwap_reversion_v3 fitness update: 0.71 → 0.74 after 3-win streak", confidence: 0.74 },
  { record_id: "m4", kind: "PROCEDURAL", ts_ns: 0, source: "DyonRuntime", summary: "Dead module removal procedure approved for execution_engine.legacy_v1", confidence: 0.82 },
  { record_id: "m5", kind: "GOVERNANCE", ts_ns: 0, source: "GovernanceMemoryStore", summary: "Mode transition PAPER → LEARNING authorised by operator", confidence: 1.0 },
  { record_id: "m6", kind: "TRADER", ts_ns: 0, source: "TraderMemoryStore", summary: "vwap_reversion_v3 archetype: win_rate 0.64, avg_pnl +0.8% over 24h", confidence: 0.64 },
  { record_id: "m7", kind: "RUNTIME", ts_ns: 0, source: "RuntimeEventMemoryStore", summary: "INDIRA tick latency spike: p99 jumped from 45ms → 180ms (1 tick)", confidence: 0.55 },
  { record_id: "m8", kind: "REGRET", ts_ns: 0, source: "ReflectionEngine", summary: "Missed BTC breakout — causal hypothesis whale_accumulation_recovery was FORMING, not ACTIVE", confidence: 0.38 },
];

const SEED_SNAP: MemorySnapshotResponse = {
  active: true,
  timeline_count: 847,
  index_size: 312,
  dedup_cache_size: 128,
  stores: { EPISODIC: 125, SEMANTIC: 234, PROCEDURAL: 89, STRATEGY: 45, TRADER: 23, GOVERNANCE: 12, RUNTIME: 67, REGRET: 8 },
};

const SEED_IDENTITY: MemoryIdentityResponse = {
  cache_size: 128, cache_capacity: 4096, total_assigned: 1204, total_new: 847, total_dedup: 357,
};

const SEED_COMPRESSION: MemoryCompressionResponse = {
  total_compressed: 38, dedup_skips: 12, buffer_size: 0, min_group_size: 3,
};

const SEED_STRATEGY: MemoryStrategyStoreResponse = {
  proposal_count: 14, fitness_history_size: 6,
  recent: [
    { record_id: "s1", summary: "vwap_reversion_v3 fitness → 0.74", ts_ns: 0 },
    { record_id: "s2", summary: "momentum_scalper mutation approved", ts_ns: 0 },
  ],
};

const SEED_TRADER: MemoryTraderStoreResponse = {
  trader_count: 4, leaderboard: [],
  recent: [
    { record_id: "t1", summary: "archetype=vwap_reversion_v3 regime=TRENDING win=true pnl=+0.8%", ts_ns: 0 },
    { record_id: "t2", summary: "archetype=momentum_scalper regime=VOLATILE win=false pnl=-0.3%", ts_ns: 0 },
  ],
};

const SEED_GOVERNANCE: MemoryGovernanceStoreResponse = {
  mode_transition_count: 2, violation_count: 0, operator_action_count: 1,
  mode_history: ["PAPER → LEARNING (operator_auth)", "LEARNING → PAPER (session_end)"],
  recent: [{ record_id: "g1", summary: "Mode PAPER → LEARNING authorised", ts_ns: 0 }],
};

const SEED_RUNTIME: MemoryRuntimeStoreResponse = {
  health_event_count: 14, failure_count: 1, recovery_count: 1,
  recent: [
    { record_id: "r1", summary: "Health event: INDIRA latency spike p99=180ms", ts_ns: 0 },
    { record_id: "r2", summary: "Recovery: latency normalised to p99=45ms after 1 tick", ts_ns: 0 },
  ],
};

// ─── Tab type ─────────────────────────────────────────────────────────────────

type Tab = "overview" | "timeline" | "search" | "stores";

// ─── Panels ───────────────────────────────────────────────────────────────────

function SnapshotPanel({
  snap,
  identity,
  compression,
}: {
  snap: MemorySnapshotResponse;
  identity: MemoryIdentityResponse;
  compression: MemoryCompressionResponse;
}) {
  const stores = snap.stores ?? {};
  const maxVal = Math.max(...Object.values(stores).filter(Boolean).map(Number), 1);

  return (
    <PanelWrap title="MEMORY · SNAPSHOT" sub="unified layer stats · 8 kind stores" accent="violet">
      <div className="mb-2 flex items-center gap-2">
        <Dot active={snap.active ?? false} />
        <span className="font-mono text-[10px] text-slate-400">
          {snap.timeline_count?.toLocaleString() ?? "–"} records · idx {snap.index_size ?? "–"}
        </span>
      </div>
      <div className="mb-2 space-y-1">
        {KIND_ORDER.map((kind) => {
          const n = stores[kind] ?? 0;
          return (
            <div key={kind} className="flex items-center gap-2">
              <span className="w-20 flex-shrink-0 font-mono text-[9px] text-slate-500">{kind}</span>
              <div className="flex-1">
                <Bar pct={(n / maxVal) * 100} color={KIND_BAR[kind] ?? "bg-slate-600"} h="h-1.5" />
              </div>
              <span className="w-7 flex-shrink-0 text-right font-mono text-[9px] text-slate-500">{n}</span>
            </div>
          );
        })}
      </div>
      <div className="grid grid-cols-3 gap-1.5 border-t border-border/40 pt-2">
        <div className="text-center">
          <p className="font-mono text-[10px] font-semibold text-violet-300">{identity.total_new ?? "–"}</p>
          <p className="font-mono text-[9px] text-slate-600">new</p>
        </div>
        <div className="text-center">
          <p className="font-mono text-[10px] font-semibold text-amber-300">{identity.total_dedup ?? "–"}</p>
          <p className="font-mono text-[9px] text-slate-600">dedup</p>
        </div>
        <div className="text-center">
          <p className="font-mono text-[10px] font-semibold text-teal-300">{compression.total_compressed ?? "–"}</p>
          <p className="font-mono text-[9px] text-slate-600">compressed</p>
        </div>
      </div>
    </PanelWrap>
  );
}

function IdentityPanel({ identity }: { identity: MemoryIdentityResponse }) {
  const hitRate =
    identity.total_dedup && identity.total_assigned
      ? ((identity.total_dedup / identity.total_assigned) * 100).toFixed(1)
      : "0.0";
  const cachePct =
    identity.cache_size && identity.cache_capacity
      ? (identity.cache_size / identity.cache_capacity) * 100
      : 0;

  return (
    <PanelWrap title="MEMORY · IDENTITY" sub="SHA-256 dedup · 60s fingerprint window" accent="sky">
      <div className="space-y-2">
        <div>
          <div className="flex justify-between font-mono text-[10px]">
            <span className="text-slate-500">LRU cache</span>
            <span className="text-slate-300">
              {identity.cache_size ?? 0}/{identity.cache_capacity ?? 4096}
            </span>
          </div>
          <Bar pct={cachePct} color="bg-sky-600" />
        </div>
        <div className="grid grid-cols-2 gap-1.5">
          {[
            { label: "assigned", val: identity.total_assigned },
            { label: "new",      val: identity.total_new },
            { label: "dedup",    val: identity.total_dedup },
            { label: "hit rate", val: `${hitRate}%` },
          ].map(({ label, val }) => (
            <div key={label} className="rounded border border-border/40 bg-bg/30 px-2 py-1">
              <p className="font-mono text-[11px] font-semibold text-slate-200">{val ?? "–"}</p>
              <p className="font-mono text-[9px] text-slate-600">{label}</p>
            </div>
          ))}
        </div>
      </div>
    </PanelWrap>
  );
}

function CompressionPanel({ compression }: { compression: MemoryCompressionResponse }) {
  return (
    <PanelWrap title="MEMORY · COMPRESSION" sub="episodic→semantic · 5-min windows" accent="teal">
      <div className="space-y-2">
        <div className="grid grid-cols-2 gap-1.5">
          {[
            { label: "compressed",  val: compression.total_compressed,  color: "text-teal-300" },
            { label: "dedup skip",  val: compression.dedup_skips,       color: "text-amber-300" },
            { label: "buffer now",  val: compression.buffer_size,       color: "text-slate-300" },
            { label: "min group",   val: compression.min_group_size,    color: "text-slate-400" },
          ].map(({ label, val, color }) => (
            <div key={label} className="rounded border border-border/40 bg-bg/30 px-2 py-1">
              <p className={`font-mono text-[11px] font-semibold ${color}`}>{val ?? "–"}</p>
              <p className="font-mono text-[9px] text-slate-600">{label}</p>
            </div>
          ))}
        </div>
        <p className="text-[10px] text-slate-600">
          Groups of ≥{compression.min_group_size ?? 3} episodic events from the same source
          within a 5-minute bucket are compressed into a single semantic record.
        </p>
      </div>
    </PanelWrap>
  );
}

function TimelinePanel({ records }: { records: MemoryRecordEntry[] }) {
  return (
    <PanelWrap title="MEMORY · TIMELINE" sub="cognition timeline · newest first" accent="violet">
      <div className="space-y-1">
        {records.length === 0 && (
          <p className="py-4 text-center text-[11px] text-slate-600">No records</p>
        )}
        {records.map((r) => (
          <div
            key={r.record_id}
            className="flex items-start gap-1.5 rounded border border-border/30 bg-bg/30 px-1.5 py-1"
          >
            <KindBadge kind={r.kind} />
            <div className="min-w-0 flex-1">
              <p className="truncate text-[10px] leading-tight text-slate-300">{r.summary}</p>
              <div className="mt-0.5 flex items-center gap-2">
                <span className="font-mono text-[9px] text-slate-600">{r.source}</span>
                {r.confidence !== undefined && r.confidence >= 0 && (
                  <span className="font-mono text-[9px] text-slate-700">
                    {(r.confidence * 100).toFixed(0)}%
                  </span>
                )}
                {r.ts_ns > 0 && (
                  <span className="font-mono text-[9px] text-slate-700">{nsToTs(r.ts_ns)}</span>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </PanelWrap>
  );
}

function StorePanel({
  title,
  accent,
  stats,
  recent,
}: {
  title: string;
  accent: "violet" | "teal" | "amber" | "sky";
  stats: { label: string; val: string | number | undefined }[];
  recent: StoreMiniRecord[] | undefined;
}) {
  return (
    <PanelWrap title={title} sub="domain memory store · recent writes" accent={accent}>
      <div className="mb-2 flex flex-wrap gap-1.5">
        {stats.map(({ label, val }) => (
          <div
            key={label}
            className="rounded border border-border/40 bg-bg/30 px-1.5 py-0.5"
          >
            <span className="font-mono text-[10px] font-semibold text-slate-200">{val ?? "–"} </span>
            <span className="font-mono text-[9px] text-slate-600">{label}</span>
          </div>
        ))}
      </div>
      <div className="space-y-1">
        {(recent ?? []).slice(0, 5).map((r) => (
          <div key={r.record_id} className="flex items-start gap-1.5">
            <span className="mt-0.5 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-slate-600" />
            <p className="flex-1 truncate text-[10px] text-slate-400">{r.summary}</p>
          </div>
        ))}
        {!recent?.length && (
          <p className="text-center text-[11px] text-slate-600">No recent writes</p>
        )}
      </div>
    </PanelWrap>
  );
}

// ─── MemoryPage ───────────────────────────────────────────────────────────────

interface PageState {
  snap: MemorySnapshotResponse;
  identity: MemoryIdentityResponse;
  compression: MemoryCompressionResponse;
  timeline: MemoryRecordEntry[];
  strategy: MemoryStrategyStoreResponse;
  trader: MemoryTraderStoreResponse;
  governance: MemoryGovernanceStoreResponse;
  runtime: MemoryRuntimeStoreResponse;
  live: boolean;
  lastUpdate: number;
}

const SEED: PageState = {
  snap: SEED_SNAP,
  identity: SEED_IDENTITY,
  compression: SEED_COMPRESSION,
  timeline: SEED_RECORDS,
  strategy: SEED_STRATEGY,
  trader: SEED_TRADER,
  governance: SEED_GOVERNANCE,
  runtime: SEED_RUNTIME,
  live: false,
  lastUpdate: Date.now(),
};

export function MemoryPage() {
  const [tab, setTab] = useState<Tab>("overview");
  const [data, setData] = useState<PageState>(SEED);
  const [searchQ, setSearchQ] = useState("");
  const [searchResults, setSearchResults] = useState<MemoryRecordEntry[]>([]);
  const [searching, setSearching] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function fetchAll() {
      const ctrl = new AbortController();
      abortRef.current = ctrl;
      const sig = ctrl.signal;

      const [snapR, identR, compR, tlR, stratR, traderR, govR, rtR] =
        await Promise.allSettled([
          fetchMemoryLayerSnapshot(sig),
          fetchMemoryIdentity(sig),
          fetchMemoryCompression(sig),
          fetchMemoryTimeline(50, 0, "", sig),
          fetchMemoryStrategyStore(10, sig),
          fetchMemoryTraderStore(10, sig),
          fetchMemoryGovernanceStore(10, sig),
          fetchMemoryRuntimeStore(10, sig),
        ]);

      if (cancelled) return;

      const anyOk = [snapR, identR, compR, tlR].some(
        (r) => r.status === "fulfilled",
      );

      setData((prev) => ({
        snap:       snapR.status  === "fulfilled" ? snapR.value       : prev.snap,
        identity:   identR.status === "fulfilled" ? identR.value      : prev.identity,
        compression:compR.status  === "fulfilled" ? compR.value       : prev.compression,
        timeline:   tlR.status    === "fulfilled" ? (tlR.value.records ?? prev.timeline) : prev.timeline,
        strategy:   stratR.status === "fulfilled" ? stratR.value      : prev.strategy,
        trader:     traderR.status=== "fulfilled" ? traderR.value     : prev.trader,
        governance: govR.status   === "fulfilled" ? govR.value        : prev.governance,
        runtime:    rtR.status    === "fulfilled" ? rtR.value         : prev.runtime,
        live:       anyOk,
        lastUpdate: Date.now(),
      }));
    }

    fetchAll();
    const id = setInterval(fetchAll, 10_000);
    return () => {
      cancelled = true;
      clearInterval(id);
      abortRef.current?.abort();
    };
  }, []);

  async function runSearch() {
    if (!searchQ.trim()) return;
    setSearching(true);
    try {
      const res = await fetchMemorySearch(searchQ.trim(), 20, "all");
      setSearchResults(res.records ?? []);
    } catch {
      setSearchResults([]);
    } finally {
      setSearching(false);
    }
  }

  const now = new Date(data.lastUpdate);
  const ts = `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}:${String(now.getSeconds()).padStart(2, "0")}`;

  const TABS: { key: Tab; label: string }[] = [
    { key: "overview", label: "OVERVIEW" },
    { key: "timeline", label: "TIMELINE" },
    { key: "search",   label: "SEARCH" },
    { key: "stores",   label: "STORES" },
  ];

  const PH = "h-[240px]";

  return (
    <div className="flex h-full flex-col overflow-hidden rounded border border-border bg-bg">
      {/* Header */}
      <header className="flex flex-shrink-0 items-center justify-between border-b border-border px-4 py-2">
        <div className="flex items-center gap-2.5">
          <Archive className="h-4 w-4 text-violet-400" />
          <span className="font-mono text-[11px] font-semibold uppercase tracking-widest text-slate-300">
            UNIFIED MEMORY LAYER
          </span>
          <span className="font-mono text-[10px] text-slate-600">
            · {data.snap.timeline_count?.toLocaleString() ?? "–"} records · 8 stores
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
                    ? "border-violet-500 text-violet-300"
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

        {/* OVERVIEW tab */}
        {tab === "overview" && (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
            <div className={PH}><SnapshotPanel snap={data.snap} identity={data.identity} compression={data.compression} /></div>
            <div className={PH}><IdentityPanel identity={data.identity} /></div>
            <div className={PH}><CompressionPanel compression={data.compression} /></div>
          </div>
        )}

        {/* TIMELINE tab */}
        {tab === "timeline" && (
          <div className="h-full">
            <TimelinePanel records={data.timeline} />
          </div>
        )}

        {/* SEARCH tab */}
        {tab === "search" && (
          <div className="flex h-full flex-col gap-3">
            <div className="flex gap-2">
              <div className="relative flex-1">
                <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-600" />
                <input
                  type="text"
                  value={searchQ}
                  onChange={(e) => setSearchQ(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && runSearch()}
                  placeholder="Space-separated keywords (AND search)…"
                  className="w-full rounded border border-border bg-bg py-1.5 pl-8 pr-3 font-mono text-[11px] text-slate-200 placeholder:text-slate-600 focus:outline-none focus:ring-1 focus:ring-violet-500"
                />
              </div>
              <button
                type="button"
                onClick={runSearch}
                disabled={searching}
                className="rounded border border-violet-800/60 bg-violet-900/20 px-3 font-mono text-[10px] text-violet-300 hover:bg-violet-800/30 disabled:opacity-40"
              >
                {searching ? "…" : "SEARCH"}
              </button>
            </div>
            <div className="min-h-0 flex-1 overflow-auto rounded border border-border/50 bg-bg/40 p-2">
              {searchResults.length === 0 ? (
                <p className="py-8 text-center text-[11px] text-slate-600">
                  {searchQ ? "No results" : "Enter keywords and press Search or ↩"}
                </p>
              ) : (
                <div className="space-y-1.5">
                  <p className="font-mono text-[9px] text-slate-600">
                    {searchResults.length} result{searchResults.length !== 1 ? "s" : ""}
                  </p>
                  {searchResults.map((r) => (
                    <div
                      key={r.record_id}
                      className="flex items-start gap-1.5 rounded border border-border/30 bg-bg/30 px-1.5 py-1"
                    >
                      <KindBadge kind={r.kind} />
                      <div className="min-w-0 flex-1">
                        <p className="text-[10px] leading-snug text-slate-300">{r.summary}</p>
                        <div className="mt-0.5 flex gap-2">
                          <span className="font-mono text-[9px] text-slate-600">{r.source}</span>
                          {r.tags && r.tags.length > 0 && (
                            <span className="font-mono text-[9px] text-slate-700">
                              [{r.tags.slice(0, 3).join(", ")}]
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* STORES tab */}
        {tab === "stores" && (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            <div className={PH}>
              <StorePanel
                title="MEMORY · STRATEGY STORE"
                accent="teal"
                stats={[
                  { label: "proposals", val: data.strategy.proposal_count },
                  { label: "tracked",   val: data.strategy.fitness_history_size },
                ]}
                recent={data.strategy.recent}
              />
            </div>
            <div className={PH}>
              <StorePanel
                title="MEMORY · TRADER STORE"
                accent="amber"
                stats={[
                  { label: "archetypes", val: data.trader.trader_count },
                ]}
                recent={data.trader.recent}
              />
            </div>
            <div className={PH}>
              <StorePanel
                title="MEMORY · GOVERNANCE STORE"
                accent="violet"
                stats={[
                  { label: "transitions", val: data.governance.mode_transition_count },
                  { label: "violations",  val: data.governance.violation_count },
                  { label: "ops",         val: data.governance.operator_action_count },
                ]}
                recent={data.governance.recent}
              />
            </div>
            <div className={PH}>
              <StorePanel
                title="MEMORY · RUNTIME STORE"
                accent="sky"
                stats={[
                  { label: "health",    val: data.runtime.health_event_count },
                  { label: "failures",  val: data.runtime.failure_count },
                  { label: "recoveries",val: data.runtime.recovery_count },
                ]}
                recent={data.runtime.recent}
              />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
