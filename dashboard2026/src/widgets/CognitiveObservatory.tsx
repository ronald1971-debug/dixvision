import { useEffect, useRef, useState } from "react";

import { Activity, Brain, Cpu, GitBranch, Network, Shield, Telescope, Zap } from "lucide-react";

import {
  fetchCognitiveSpine,
  fetchDyonDeadCode,
  fetchDyonDrift,
  fetchDyonEngineering,
  fetchDyonRepo,
  fetchEvolutionPipeline,
  fetchGovernanceStore,
  fetchIndiraCausal,
  fetchIndiraClusters,
  fetchIndiraConsciousness,
  fetchKernelStatus,
  fetchMemorySnapshot,
  fetchSimulationDominance,
  fetchTelemetrySummary,
  type BehavioralClusterRecord,
  type CausalHypothesisRecord,
  type ConsciousnessEntry,
  type DeadCodeResponse,
  type DriftResponse,
  type DyonEngineeringResponse,
  type GovernanceStoreResponse,
  type KernelStatusResponse,
  type MemoryLayerSnapshot,
  type PipelineResponse,
  type RepoInspectorResponse,
  type SimDominanceResponse,
  type SpineSnapshotResponse,
  type TelemetrySummaryResponse,
} from "@/api/cognitive";

// ─── Types ───────────────────────────────────────────────────────────────────

type Section = "all" | "indira" | "dyon" | "system";

interface ObsState {
  // INDIRA
  consciousness: ConsciousnessEntry[];
  clusters: BehavioralClusterRecord[];
  hypotheses: CausalHypothesisRecord[];
  topChain: { label: string; confidence: number } | null;
  // DYON
  spine: SpineSnapshotResponse;
  drift: DriftResponse;
  repo: RepoInspectorResponse;
  deadCode: DeadCodeResponse;
  pipeline: PipelineResponse;
  engineering: DyonEngineeringResponse;
  // SYSTEM
  telemetry: TelemetrySummaryResponse;
  simulation: SimDominanceResponse;
  memory: MemoryLayerSnapshot;
  governance: GovernanceStoreResponse;
  kernel: KernelStatusResponse;
  live: boolean;
  lastUpdate: number;
}

// ─── Seed data ───────────────────────────────────────────────────────────────

const SEED: ObsState = {
  consciousness: [
    { entry_id: "c1", ts_ns: 0, event_kind: "INDIRA_THOUGHT", narrative: "Regime: TRENDING — BTC funding 0.012%/8h, OI expanding +4.2%. Watching for continuation.", importance: 0.55, source: "IndiraRuntime", raw_sub_type: "COGNITIVE_TICK" },
    { entry_id: "c2", ts_ns: 0, event_kind: "INDIRA_INSIGHT", narrative: "Dominant archetype: vwap_reversion_v3 — 12 active traders. Composite score 1.45.", importance: 0.65, source: "BehavioralCluster", raw_sub_type: "ARCHETYPE_EVOLUTION" },
    { entry_id: "c3", ts_ns: 0, event_kind: "INDIRA_THOUGHT", narrative: "Causal chain activating: CPI_surprise → risk-off → BTC_flush. Evidence: 7 signals.", importance: 0.68, source: "CausalGraph", raw_sub_type: "HYPO_ACTIVATED" },
    { entry_id: "c4", ts_ns: 0, event_kind: "DYON_PROPOSAL", narrative: "DYON proposal: dead module execution_engine.legacy_v1 — ORPHANED, confidence 0.80.", importance: 0.42, source: "DeadCodeDetector", raw_sub_type: "DEAD_CODE" },
    { entry_id: "c5", ts_ns: 0, event_kind: "RESEARCH_COMPLETE", narrative: "@perp_savant updated position model v2.7 — trust 0.72. Integrating.", importance: 0.50, source: "ResearchRuntime", raw_sub_type: "RESEARCH_RESULT" },
  ],
  clusters: [
    { cluster_id: "vwap_reversion_v3", label: "VWAP Reversion", strength: 0.78, composite_score: 1.45, member_count: 12, dominant: true },
    { cluster_id: "momentum_scalper", label: "Momentum Scalper", strength: 0.62, composite_score: 1.02, member_count: 8, dominant: false },
    { cluster_id: "macro_swing_v2", label: "Macro Swing", strength: 0.45, composite_score: 0.68, member_count: 5, dominant: false },
    { cluster_id: "hft_market_make", label: "HFT Market Make", strength: 0.31, composite_score: 0.38, member_count: 3, dominant: false },
  ],
  hypotheses: [
    { hypo_id: "h1", label: "cpi_shock_risk_off", state: "ACTIVE", confidence: 0.68, evidence_count: 7, age_ticks: 42 },
    { hypo_id: "h2", label: "regime_bull_momentum", state: "ACTIVE", confidence: 0.72, evidence_count: 11, age_ticks: 65 },
    { hypo_id: "h3", label: "funding_flip_long_squeeze", state: "FORMING", confidence: 0.38, evidence_count: 3, age_ticks: 12 },
    { hypo_id: "h4", label: "whale_accumulation_recovery", state: "FORMING", confidence: 0.29, evidence_count: 2, age_ticks: 7 },
  ],
  topChain: { label: "regime_bull_momentum", confidence: 0.72 },
  spine: { active: true, tick_seq: 1247, phase_errors: { cogov: 0, memory: 0, trader: 0, indira: 2, dyon: 1 }, cadence: { cogov_every: 1, memory_every: 5, trader_every: 2, indira_every: 1, dyon_every: 3 } },
  drift: { health_score: 78, trend: "STABLE", grade: "B", spike_detected: false, scan_count: 14, history_series: [72, 74, 76, 75, 77, 76, 78, 79, 78, 78] },
  repo: { file_count: 1247, python_file_count: 892, scan_count: 3, edge_count: 2847, isolated_modules: 12, layer_distribution: { L0: 45, L1: 123, L2: 67, L3: 89, L4: 112, L5: 78, L6: 45, L7: 234, L8: 99 } },
  deadCode: { scan_count: 3, dead_module_count: 17, by_classification: { ORPHANED: 8, ISOLATED: 4, STUB: 3, EMPTY: 2 }, dead_modules: [] },
  pipeline: { active_count: 5, completed_count: 23, stage_counts: { PROPOSED: 2, SANDBOX: 1, BENCHMARK: 1, GOV_REVIEW: 1, PROMOTED: 8, MONITORING: 3, AUDITED: 12, REJECTED: 2 } },
  engineering: { active: true, tick_seq: 412 },
  telemetry: { indira: { count: 1247, throughput_per_min: 4.8, p50_ms: 12, p99_ms: 45 }, dyon: { count: 412, throughput_per_min: 1.6, p50_ms: 8, p99_ms: 22 }, research: { count: 34, throughput_per_min: 0.3, p50_ms: 2100, p99_ms: 8000 }, long_horizon: { count: 89, throughput_per_min: 0.7, p50_ms: 95, p99_ms: 450 } },
  simulation: { dominance_achieved: false, dominant_strategy: "vwap_reversion_v3", tournament_runs: 12, scoreboard: { "vwap_reversion_v3": { fitness: 0.72, wins: 8, losses: 2, current_streak: 3 }, "momentum_scalper": { fitness: 0.61, wins: 6, losses: 4, current_streak: 1 }, "macro_swing_v2": { fitness: 0.49, wins: 4, losses: 6, current_streak: 0 } }, dominance_threshold: 60, promoted_count: 2 },
  memory: { timeline_count: 847, index_size: 312, stores: { EPISODIC: 125, SEMANTIC: 234, PROCEDURAL: 89, STRATEGY: 45, TRADER: 23, GOVERNANCE: 12, RUNTIME: 67, REGRET: 8 } },
  governance: { mode_transitions: [{ from_mode: "PAPER", to_mode: "LEARNING", reason: "operator_auth", ts_ns: 0 }, { from_mode: "LEARNING", to_mode: "PAPER", reason: "session_end", ts_ns: 0 }], operator_actions: [], violations: [] },
  kernel: { active: true, tick_seq: 1247, components: { cross_bus_router: { active: true, type: "CrossBusRouter" }, governance_router: { active: true, type: "GovernanceRouter" }, cognition_scheduler: { active: true, type: "CognitionScheduler" }, memory_coordinator: { active: true, type: "MemoryCoordinator" }, telemetry_aggregator: { active: true, type: "TelemetryAggregator" }, state_sync: { active: true, type: "UnifiedStateSync" }, cognitive_spine: { active: true, type: "CognitiveSpine" } } },
  live: false,
  lastUpdate: Date.now(),
};

// ─── Helpers ──────────────────────────────────────────────────────────────────

function Bar({ pct, color = "bg-sky-500", h = "h-1.5" }: { pct: number; color?: string; h?: string }) {
  return (
    <div className={`w-full rounded-full bg-slate-700/60 ${h}`}>
      <div className={`${h} rounded-full ${color}`} style={{ width: `${Math.max(2, Math.min(100, pct))}%` }} />
    </div>
  );
}

function Dot({ active }: { active: boolean }) {
  return <span className={`inline-block h-2 w-2 rounded-full ${active ? "bg-emerald-400" : "bg-slate-600"}`} />;
}

function StateBadge({ state }: { state: string }) {
  const colors: Record<string, string> = {
    ACTIVE: "border-emerald-500/40 bg-emerald-500/10 text-emerald-300",
    FORMING: "border-amber-500/40 bg-amber-500/10 text-amber-300",
    CONFIRMED: "border-teal-500/40 bg-teal-500/10 text-teal-300",
    WEAKENED: "border-orange-500/40 bg-orange-500/10 text-orange-300",
    DISSOLVED: "border-slate-600/40 bg-slate-700/20 text-slate-500",
  };
  return (
    <span className={`rounded border px-1 font-mono text-[9px] uppercase ${colors[state] ?? "border-slate-600/40 text-slate-500"}`}>
      {state}
    </span>
  );
}

function PanelWrap({ color, title, sub, children }: { color: string; title: string; sub: string; children: React.ReactNode }) {
  return (
    <div className={`flex h-full flex-col overflow-hidden rounded border ${color} bg-surface`}>
      <div className="flex-shrink-0 border-b border-border/50 px-2.5 py-1.5">
        <p className={`font-mono text-[10px] uppercase tracking-widest ${color.includes("violet") ? "text-violet-400" : color.includes("teal") ? "text-teal-400" : "text-amber-400"}`}>{title}</p>
        <p className="text-[10px] text-slate-600">{sub}</p>
      </div>
      <div className="min-h-0 flex-1 overflow-auto p-2">{children}</div>
    </div>
  );
}

const SECTION_BORDER: Record<"indira" | "dyon" | "system", string> = {
  indira: "border-violet-900/50",
  dyon: "border-teal-900/50",
  system: "border-amber-900/50",
};

// ─── INDIRA panels ────────────────────────────────────────────────────────────

const KIND_COLOR: Record<string, string> = {
  INDIRA_THOUGHT: "text-sky-400",
  INDIRA_INSIGHT: "text-violet-400",
  DYON_VIOLATION: "text-rose-400",
  DYON_PROPOSAL: "text-amber-400",
  DYON_SCAN_COMPLETE: "text-teal-400",
  RESEARCH_COMPLETE: "text-emerald-400",
  MARKET_TICK: "text-slate-500",
  RISK_BREACH: "text-rose-400",
};

function ReasoningStreamPanel({ entries }: { entries: ConsciousnessEntry[] }) {
  return (
    <PanelWrap color={SECTION_BORDER.indira} title="INDIRA · REASONING STREAM" sub="consciousness ring buffer — newest first">
      <div className="space-y-1.5">
        {entries.slice(0, 6).map((e) => (
          <div key={e.entry_id} className="flex items-start gap-1.5">
            <div
              className="mt-0.5 h-2 w-2 flex-shrink-0 rounded-full"
              style={{ opacity: 0.3 + e.importance * 0.7, background: e.importance > 0.7 ? "#f87171" : e.importance > 0.5 ? "#a78bfa" : "#38bdf8" }}
            />
            <div className="min-w-0 flex-1">
              <span className={`mr-1 font-mono text-[9px] uppercase ${KIND_COLOR[e.event_kind] ?? "text-slate-500"}`}>
                {e.event_kind.replace(/_/g, " ")}
              </span>
              <p className="truncate text-[10px] leading-tight text-slate-300">{e.narrative}</p>
            </div>
          </div>
        ))}
        {entries.length === 0 && <p className="text-center text-[11px] text-slate-600">No entries</p>}
      </div>
    </PanelWrap>
  );
}

function TraderClustersPanel({ clusters }: { clusters: BehavioralClusterRecord[] }) {
  const max = Math.max(...clusters.map((c) => c.composite_score), 0.01);
  return (
    <PanelWrap color={SECTION_BORDER.indira} title="INDIRA · TRADER CLUSTERS" sub="behavioral archetype distribution">
      <div className="space-y-2">
        {clusters.map((c) => (
          <div key={c.cluster_id}>
            <div className="flex items-baseline justify-between">
              <div className="flex items-center gap-1">
                <span className="text-[11px] text-slate-200">{c.label}</span>
                {c.dominant && (
                  <span className="rounded border border-teal-500/40 bg-teal-500/10 px-1 font-mono text-[8px] text-teal-300">DOM</span>
                )}
              </div>
              <span className="font-mono text-[9px] text-slate-600">{c.member_count}t · Σ{c.composite_score.toFixed(2)}</span>
            </div>
            <Bar pct={(c.composite_score / max) * 100} color={c.dominant ? "bg-violet-500" : "bg-violet-800"} h="h-1" />
          </div>
        ))}
      </div>
    </PanelWrap>
  );
}

function CausalGraphPanel({ hypotheses, topChain }: { hypotheses: CausalHypothesisRecord[]; topChain: { label: string; confidence: number } | null }) {
  return (
    <PanelWrap color={SECTION_BORDER.indira} title="INDIRA · CAUSAL GRAPH" sub="hypothesis lifecycle · evidence chains">
      {topChain && (
        <div className="mb-2 rounded border border-violet-900/60 bg-violet-900/20 p-1.5">
          <p className="font-mono text-[9px] uppercase text-violet-400">Top Chain</p>
          <p className="mt-0.5 text-[11px] text-slate-200">{topChain.label.replace(/_/g, " ")}</p>
          <div className="mt-1 flex items-center gap-2">
            <Bar pct={topChain.confidence * 100} color="bg-violet-500" h="h-1" />
            <span className="flex-shrink-0 font-mono text-[9px] text-slate-500">{topChain.confidence.toFixed(2)}</span>
          </div>
        </div>
      )}
      <div className="space-y-1.5">
        {hypotheses.slice(0, 4).map((h) => (
          <div key={h.hypo_id} className="flex items-center gap-2">
            <StateBadge state={h.state} />
            <span className="flex-1 truncate text-[10px] text-slate-300">{h.label.replace(/_/g, " ")}</span>
            <span className="flex-shrink-0 font-mono text-[9px] text-slate-600">{h.confidence.toFixed(2)}</span>
          </div>
        ))}
      </div>
    </PanelWrap>
  );
}

const REGIME_SEED: { asset: string; regime: string; meta: string }[] = [
  { asset: "BTC", regime: "TRENDING", meta: "fund +0.012" },
  { asset: "ETH", regime: "RANGING", meta: "vol −12%" },
  { asset: "SOL", regime: "TRENDING", meta: "oi +4.2%" },
  { asset: "SPX", regime: "MIXED", meta: "vix 18.4" },
  { asset: "EUR", regime: "RANGING", meta: "dx −0.3%" },
  { asset: "GLOBAL", regime: "RISK-ON", meta: "regime bull" },
];

const REGIME_COLOR: Record<string, string> = {
  TRENDING: "border-emerald-500/40 bg-emerald-500/10 text-emerald-300",
  RANGING: "border-amber-500/40 bg-amber-500/10 text-amber-300",
  VOLATILE: "border-rose-500/40 bg-rose-500/10 text-rose-300",
  MIXED: "border-slate-500/40 bg-slate-600/20 text-slate-400",
  "RISK-ON": "border-teal-500/40 bg-teal-500/10 text-teal-300",
  "RISK-OFF": "border-rose-500/40 bg-rose-500/10 text-rose-300",
};

function RegimeMapPanel() {
  return (
    <PanelWrap color={SECTION_BORDER.indira} title="INDIRA · REGIME MAP" sub="asset regime detection · market context">
      <div className="grid grid-cols-2 gap-1.5">
        {REGIME_SEED.map(({ asset, regime, meta }) => (
          <div key={asset} className="rounded border border-border/40 bg-bg/40 p-1.5">
            <div className="flex items-baseline justify-between">
              <span className="font-mono text-[10px] font-semibold text-slate-200">{asset}</span>
              <span className="font-mono text-[9px] text-slate-600">{meta}</span>
            </div>
            <span className={`mt-1 inline-block rounded border px-1 font-mono text-[9px] uppercase ${REGIME_COLOR[regime] ?? "text-slate-500"}`}>
              {regime}
            </span>
          </div>
        ))}
      </div>
    </PanelWrap>
  );
}

function UncertaintyPanel({ hypotheses }: { hypotheses: CausalHypothesisRecord[] }) {
  const deltas = [+0.14, -0.05, +0.20, +0.06, -0.08, +0.11, +0.03, -0.04];
  const net = deltas.reduce((a, b) => a + b, 0);
  return (
    <PanelWrap color={SECTION_BORDER.indira} title="INDIRA · UNCERTAINTY" sub="belief delta stream · confidence swings">
      <div className="mb-2">
        <div className="flex items-baseline justify-between">
          <span className="font-mono text-[10px] text-slate-500">Net confidence drift</span>
          <span className={`font-mono text-[11px] font-semibold ${net >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
            {net >= 0 ? "+" : ""}{net.toFixed(2)}
          </span>
        </div>
        <div className="mt-1 h-2 w-full overflow-hidden rounded-full bg-slate-700">
          <div
            className={`h-2 rounded-full ${net >= 0 ? "bg-emerald-500" : "bg-rose-500"}`}
            style={{ width: `${Math.min(100, Math.abs(net) * 200)}%`, marginLeft: net >= 0 ? "50%" : undefined, marginRight: net < 0 ? "50%" : undefined }}
          />
        </div>
      </div>
      <div className="space-y-1">
        {deltas.map((d, i) => (
          <div key={i} className="flex items-center gap-2">
            <span className="w-4 flex-shrink-0 font-mono text-[9px] text-slate-600">{i + 1}</span>
            <div className="flex flex-1 items-center gap-1">
              {d >= 0 ? (
                <div className="flex flex-1 justify-end">
                  <div className="h-1.5 rounded-full bg-emerald-600" style={{ width: `${Math.abs(d) * 300}%`, maxWidth: "50%" }} />
                </div>
              ) : (
                <div className="flex-1" />
              )}
              <div className="w-px h-3 bg-slate-700 flex-shrink-0" />
              {d < 0 ? (
                <div className="h-1.5 rounded-full bg-rose-600" style={{ width: `${Math.abs(d) * 300}%`, maxWidth: "50%" }} />
              ) : (
                <div className="flex-1" />
              )}
            </div>
            <span className={`w-10 flex-shrink-0 text-right font-mono text-[9px] ${d >= 0 ? "text-emerald-500" : "text-rose-500"}`}>
              {d >= 0 ? "+" : ""}{d.toFixed(2)}
            </span>
          </div>
        ))}
      </div>
    </PanelWrap>
  );
}

function ConfidenceEvolutionPanel({ entries }: { entries: ConsciousnessEntry[] }) {
  const series = entries.slice(0, 20).map((e) => e.importance).reverse();
  const padded = series.length > 0 ? series : [0.5, 0.52, 0.55, 0.58, 0.56, 0.60, 0.62, 0.61, 0.64, 0.67, 0.65, 0.68, 0.70, 0.68, 0.72];
  const max = Math.max(...padded);
  const min = Math.min(...padded);
  const range = max - min || 0.1;
  const current = padded[padded.length - 1];
  const prev = padded[padded.length - 2] ?? current;
  const trend = current > prev ? "▲" : current < prev ? "▼" : "━";
  const trendColor = current > prev ? "text-emerald-400" : current < prev ? "text-rose-400" : "text-slate-400";

  return (
    <PanelWrap color={SECTION_BORDER.indira} title="INDIRA · CONFIDENCE" sub="rolling cognitive confidence · importance proxy">
      <div className="mb-2 flex items-baseline justify-between">
        <span className="font-mono text-[10px] text-slate-500">Current</span>
        <span className={`font-mono text-sm font-semibold ${trendColor}`}>
          {trend} {(current * 100).toFixed(0)}%
        </span>
      </div>
      <div className="flex h-16 items-end gap-px">
        {padded.map((v, i) => {
          const h = ((v - min) / range) * 100;
          const isLast = i === padded.length - 1;
          return (
            <div
              key={i}
              className={`flex-1 rounded-t-sm ${isLast ? "bg-violet-400" : "bg-violet-700/60"}`}
              style={{ height: `${Math.max(4, h)}%` }}
            />
          );
        })}
      </div>
      <div className="mt-1 flex justify-between font-mono text-[9px] text-slate-600">
        <span>min {(min * 100).toFixed(0)}%</span>
        <span>max {(max * 100).toFixed(0)}%</span>
      </div>
    </PanelWrap>
  );
}

// ─── DYON panels ──────────────────────────────────────────────────────────────

const LAYER_COLORS: Record<string, string> = {
  L0: "bg-slate-500", L1: "bg-blue-700", L2: "bg-sky-600",
  L3: "bg-teal-600", L4: "bg-emerald-600", L5: "bg-green-700",
  L6: "bg-yellow-700", L7: "bg-orange-700", L8: "bg-rose-700",
};

function RepoEvolutionPanel({ repo }: { repo: RepoInspectorResponse }) {
  const dist = repo.layer_distribution ?? {};
  const max = Math.max(...Object.values(dist), 1);
  const layers = Object.entries(dist).sort(([a], [b]) => a.localeCompare(b));

  return (
    <PanelWrap color={SECTION_BORDER.dyon} title="DYON · REPOSITORY EVOLUTION" sub="layer distribution · module topology">
      <div className="mb-2 flex gap-4 font-mono text-[10px]">
        <span className="text-slate-400">{repo.file_count ?? "–"} files</span>
        <span className="text-slate-500">{repo.edge_count ?? "–"} edges</span>
        <span className="text-rose-400">{repo.isolated_modules ?? 0} isolated</span>
      </div>
      <div className="space-y-1">
        {layers.map(([layer, count]) => (
          <div key={layer} className="flex items-center gap-2">
            <span className="w-6 flex-shrink-0 font-mono text-[9px] text-slate-500">{layer}</span>
            <div className="flex flex-1 items-center gap-1">
              <div className="flex-1 rounded-full bg-slate-700/60 h-1.5">
                <div className={`h-1.5 rounded-full ${LAYER_COLORS[layer] ?? "bg-slate-500"}`} style={{ width: `${(count / max) * 100}%` }} />
              </div>
              <span className="flex-shrink-0 w-6 text-right font-mono text-[9px] text-slate-600">{count}</span>
            </div>
          </div>
        ))}
      </div>
    </PanelWrap>
  );
}

function RuntimeHealthPanel({ spine }: { spine: SpineSnapshotResponse }) {
  const phases = ["cogov", "memory", "trader", "indira", "dyon"];
  const errors = spine.phase_errors ?? {};
  const cadence = spine.cadence ?? {};

  return (
    <PanelWrap color={SECTION_BORDER.dyon} title="DYON · RUNTIME HEALTH" sub="phase errors · tick cadence · spine status">
      <div className="mb-1.5 flex items-center gap-2">
        <Dot active={spine.active ?? false} />
        <span className="font-mono text-[10px] text-slate-400">
          {spine.active ? "SPINE ACTIVE" : "SPINE INACTIVE"} · tick #{spine.tick_seq ?? 0}
        </span>
      </div>
      <div className="space-y-1">
        {phases.map((p) => {
          const errs = errors[p] ?? 0;
          const every = cadence[`${p}_every`] ?? 1;
          return (
            <div key={p} className="flex items-center gap-2">
              <Dot active={errs === 0} />
              <span className="w-14 font-mono text-[10px] text-slate-300 capitalize">{p}</span>
              <div className="flex-1">
                <Bar pct={Math.max(2, 100 - Math.min(100, errs * 20))} color={errs === 0 ? "bg-emerald-600" : errs < 3 ? "bg-amber-500" : "bg-rose-600"} h="h-1" />
              </div>
              <span className="w-8 flex-shrink-0 text-right font-mono text-[9px] text-slate-600">
                {errs > 0 ? <span className="text-rose-400">{errs}e</span> : "ok"}
              </span>
              <span className="flex-shrink-0 font-mono text-[9px] text-slate-700">/{every}</span>
            </div>
          );
        })}
      </div>
    </PanelWrap>
  );
}

const GRADE_COLOR: Record<string, string> = {
  A: "border-emerald-500/60 bg-emerald-500/10 text-emerald-300",
  B: "border-teal-500/60 bg-teal-500/10 text-teal-300",
  C: "border-amber-500/60 bg-amber-500/10 text-amber-300",
  D: "border-orange-500/60 bg-orange-500/10 text-orange-300",
  F: "border-rose-500/60 bg-rose-500/10 text-rose-300",
};

function ArchDriftPanel({ drift }: { drift: DriftResponse }) {
  const series = drift.history_series ?? [];
  const max = Math.max(...series, 100);
  const grade = drift.grade ?? "C";
  const health = drift.health_score ?? 50;
  const trend = drift.trend ?? "STABLE";
  const trendColor = trend === "IMPROVING" ? "text-emerald-400" : trend === "DEGRADING" ? "text-rose-400" : "text-slate-400";

  return (
    <PanelWrap color={SECTION_BORDER.dyon} title="DYON · ARCHITECTURE DRIFT" sub="health trend · invariant scan history">
      <div className="mb-2 flex items-start justify-between gap-3">
        <div>
          <span className={`rounded border px-2 py-0.5 font-mono text-xl font-bold ${GRADE_COLOR[grade] ?? GRADE_COLOR.C}`}>
            {grade}
          </span>
          <p className="mt-1 font-mono text-[10px] text-slate-400">{health}/100</p>
        </div>
        <div className="text-right">
          <span className={`font-mono text-[10px] font-semibold ${trendColor}`}>{trend}</span>
          <p className="font-mono text-[9px] text-slate-600">{drift.scan_count ?? 0} scans</p>
          {drift.spike_detected && <span className="font-mono text-[9px] text-rose-400">SPIKE</span>}
        </div>
      </div>
      {series.length > 0 && (
        <>
          <div className="flex h-10 items-end gap-px">
            {series.map((v, i) => (
              <div
                key={i}
                className={`flex-1 rounded-t-sm ${v >= 75 ? "bg-teal-600" : v >= 55 ? "bg-amber-600" : "bg-rose-600"}`}
                style={{ height: `${(v / max) * 100}%` }}
              />
            ))}
          </div>
          <p className="mt-0.5 font-mono text-[9px] text-slate-700">last {series.length} scans</p>
        </>
      )}
    </PanelWrap>
  );
}

const STAGE_ORDER = ["PROPOSED", "SANDBOX", "BENCHMARK", "GOV_REVIEW", "PROMOTED", "MONITORING", "AUDITED", "REJECTED"] as const;

function MutationTrackingPanel({ pipeline }: { pipeline: PipelineResponse }) {
  const counts = pipeline.stage_counts ?? {};
  const maxCount = Math.max(...Object.values(counts), 1);

  return (
    <PanelWrap color={SECTION_BORDER.dyon} title="DYON · MUTATION TRACKING" sub="governed evolution pipeline · stage funnel">
      <div className="mb-1.5 flex gap-3 font-mono text-[10px]">
        <span className="text-slate-400">active {pipeline.active_count ?? 0}</span>
        <span className="text-slate-500">done {pipeline.completed_count ?? 0}</span>
      </div>
      <div className="space-y-1">
        {STAGE_ORDER.map((stage) => {
          const n = counts[stage] ?? 0;
          const isGov = stage === "GOV_REVIEW";
          return (
            <div key={stage} className="flex items-center gap-2">
              <span className="w-24 flex-shrink-0 font-mono text-[9px] text-slate-500">{stage.replace(/_/g, " ")}</span>
              <div className="flex-1">
                <Bar pct={(n / maxCount) * 100} color={isGov && n > 0 ? "bg-amber-500" : "bg-teal-700"} h="h-1.5" />
              </div>
              <span className={`w-4 flex-shrink-0 text-right font-mono text-[10px] ${isGov && n > 0 ? "text-amber-300" : "text-slate-500"}`}>{n}</span>
            </div>
          );
        })}
      </div>
    </PanelWrap>
  );
}

const CLASS_COLORS: Record<string, string> = {
  ORPHANED: "text-amber-400 border-amber-900/40",
  ISOLATED: "text-rose-400 border-rose-900/40",
  STUB: "text-slate-400 border-slate-700/40",
  EMPTY: "text-slate-500 border-slate-700/40",
};

function OptimizationPanel({ deadCode }: { deadCode: DeadCodeResponse }) {
  const byClass = deadCode.by_classification ?? {};
  const modules = deadCode.dead_modules?.slice(0, 5) ?? [];

  return (
    <PanelWrap color={SECTION_BORDER.dyon} title="DYON · OPTIMIZATION CANDIDATES" sub="dead code · orphaned modules · cleanup queue">
      <div className="mb-2 flex flex-wrap gap-1.5">
        {Object.entries(byClass).map(([cls, n]) => (
          <span key={cls} className={`rounded border px-1.5 font-mono text-[9px] ${CLASS_COLORS[cls] ?? "text-slate-500 border-slate-700/40"}`}>
            {n} {cls}
          </span>
        ))}
      </div>
      {modules.length > 0 ? (
        <div className="space-y-1">
          {modules.map((m) => (
            <div key={m.module_path} className="flex items-center gap-2">
              <span className={`flex-shrink-0 font-mono text-[9px] ${CLASS_COLORS[m.classification]?.split(" ")[0] ?? "text-slate-500"}`}>
                {m.classification[0]}
              </span>
              <span className="flex-1 truncate font-mono text-[10px] text-slate-400">{m.module_path}</span>
              <span className="flex-shrink-0 font-mono text-[9px] text-slate-600">{(m.confidence * 100).toFixed(0)}%</span>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-center text-[11px] text-slate-600">No candidates yet</p>
      )}
    </PanelWrap>
  );
}

// ─── SYSTEM panels ────────────────────────────────────────────────────────────

const COMPONENT_LABELS: Record<string, string> = {
  indira: "INDIRA thoughts",
  dyon: "DYON scans",
  research: "Research",
  long_horizon: "Long-horizon",
};

function EventThroughputPanel({ telemetry }: { telemetry: TelemetrySummaryResponse }) {
  const components = ["indira", "dyon", "research", "long_horizon"] as const;
  const maxTpm = Math.max(...components.map((k) => telemetry[k]?.throughput_per_min ?? 0), 0.1);

  return (
    <PanelWrap color={SECTION_BORDER.system} title="SYSTEM · EVENT THROUGHPUT" sub="per-component event rates · telemetry">
      <div className="space-y-2">
        {components.map((k) => {
          const s = telemetry[k];
          if (!s) return null;
          return (
            <div key={k}>
              <div className="flex items-baseline justify-between">
                <span className="text-[10px] text-slate-400">{COMPONENT_LABELS[k]}</span>
                <span className="font-mono text-[10px] text-slate-400">{s.throughput_per_min?.toFixed(1)}/min</span>
              </div>
              <Bar pct={(s.throughput_per_min ?? 0) / maxTpm * 100} color="bg-amber-600" h="h-1.5" />
              <div className="mt-0.5 flex gap-3 font-mono text-[9px] text-slate-600">
                <span>n={s.count?.toLocaleString()}</span>
                {s.p50_ms && <span>p50={s.p50_ms}ms</span>}
                {s.p99_ms && <span>p99={s.p99_ms}ms</span>}
              </div>
            </div>
          );
        })}
      </div>
    </PanelWrap>
  );
}

function CognitionLatencyPanel({ spine }: { spine: SpineSnapshotResponse }) {
  const tickSeq = spine.tick_seq ?? 0;
  const cadence = spine.cadence ?? {};
  const phases: { name: string; key: string }[] = [
    { name: "cogov", key: "cogov_every" },
    { name: "memory", key: "memory_every" },
    { name: "trader", key: "trader_every" },
    { name: "indira", key: "indira_every" },
    { name: "dyon", key: "dyon_every" },
  ];
  const minEvery = Math.min(...phases.map((p) => cadence[p.key] ?? 1), 1);

  return (
    <PanelWrap color={SECTION_BORDER.system} title="SYSTEM · COGNITION LATENCY" sub="phase cadence · tick rates">
      <div className="mb-2">
        <span className="font-mono text-[10px] text-slate-500">tick #{tickSeq.toLocaleString()}</span>
      </div>
      <div className="space-y-1.5">
        {phases.map(({ name, key }) => {
          const every = cadence[key] ?? 1;
          const relRate = minEvery / every;
          return (
            <div key={name} className="flex items-center gap-2">
              <span className="w-12 font-mono text-[10px] capitalize text-slate-300">{name}</span>
              <div className="flex-1">
                <Bar pct={relRate * 100} color="bg-amber-700" h="h-1.5" />
              </div>
              <span className="w-14 flex-shrink-0 text-right font-mono text-[9px] text-slate-500">
                every {every} tick{every !== 1 ? "s" : ""}
              </span>
            </div>
          );
        })}
      </div>
      <div className="mt-2 border-t border-border/40 pt-1.5">
        <p className="font-mono text-[9px] text-slate-600">
          INDIRA runs every tick · DYON every {cadence.dyon_every ?? 3} · memory every {cadence.memory_every ?? 5}
        </p>
      </div>
    </PanelWrap>
  );
}

function GovernanceActionsPanel({ governance }: { governance: GovernanceStoreResponse }) {
  const transitions = governance.mode_transitions ?? [];

  return (
    <PanelWrap color={SECTION_BORDER.system} title="SYSTEM · GOVERNANCE ACTIONS" sub="mode transitions · operator decisions">
      {transitions.length > 0 ? (
        <div className="space-y-1.5">
          {transitions.slice(0, 5).map((t, i) => (
            <div key={i} className="rounded border border-border/40 bg-bg/40 px-2 py-1">
              <div className="flex items-center gap-1.5 font-mono text-[10px]">
                <span className="text-slate-500">{t.from_mode ?? "–"}</span>
                <span className="text-slate-700">→</span>
                <span className="text-amber-300">{t.to_mode ?? "–"}</span>
              </div>
              {t.reason && (
                <p className="mt-0.5 text-[10px] text-slate-600">{t.reason}</p>
              )}
            </div>
          ))}
        </div>
      ) : (
        <div className="space-y-1.5">
          {[{ from: "PAPER", to: "LEARNING", reason: "operator_auth" }, { from: "LEARNING", to: "PAPER", reason: "session_end" }].map((t, i) => (
            <div key={i} className="rounded border border-border/40 bg-bg/40 px-2 py-1">
              <div className="flex items-center gap-1.5 font-mono text-[10px]">
                <span className="text-slate-500">{t.from}</span>
                <span className="text-slate-700">→</span>
                <span className="text-amber-300">{t.to}</span>
              </div>
              <p className="mt-0.5 text-[10px] text-slate-600">{t.reason}</p>
            </div>
          ))}
          <p className="text-center font-mono text-[9px] text-slate-700">seed data</p>
        </div>
      )}
    </PanelWrap>
  );
}

const MEMORY_KIND_COLORS: Record<string, string> = {
  EPISODIC: "bg-sky-700",
  SEMANTIC: "bg-violet-700",
  PROCEDURAL: "bg-teal-700",
  STRATEGY: "bg-emerald-700",
  TRADER: "bg-amber-700",
  GOVERNANCE: "bg-orange-700",
  RUNTIME: "bg-slate-600",
  REGRET: "bg-rose-800",
};

function MemoryGrowthPanel({ memory }: { memory: MemoryLayerSnapshot }) {
  const stores = memory.stores ?? {};
  const maxVal = Math.max(...Object.values(stores), 1);

  return (
    <PanelWrap color={SECTION_BORDER.system} title="SYSTEM · MEMORY GROWTH" sub="unified memory layer · 8 kind stores">
      <div className="mb-1.5 flex gap-3 font-mono text-[10px]">
        <span className="text-slate-400">total {memory.timeline_count?.toLocaleString() ?? "–"}</span>
        <span className="text-slate-600">index {memory.index_size ?? "–"}</span>
      </div>
      <div className="space-y-1">
        {Object.entries(stores).map(([kind, count]) => (
          <div key={kind} className="flex items-center gap-2">
            <span className="w-20 flex-shrink-0 font-mono text-[9px] text-slate-500">{kind}</span>
            <div className="flex-1">
              <Bar pct={(count / maxVal) * 100} color={MEMORY_KIND_COLORS[kind] ?? "bg-slate-600"} h="h-1.5" />
            </div>
            <span className="w-8 flex-shrink-0 text-right font-mono text-[9px] text-slate-500">{count}</span>
          </div>
        ))}
      </div>
    </PanelWrap>
  );
}

function SimulationStatePanel({ simulation }: { simulation: SimDominanceResponse }) {
  const scoreboard = simulation.scoreboard ?? {};
  const entries = Object.entries(scoreboard).sort(([, a], [, b]) => (b.fitness ?? 0) - (a.fitness ?? 0));
  const champion = simulation.dominant_strategy;
  const achieved = simulation.dominance_achieved ?? false;

  return (
    <PanelWrap color={SECTION_BORDER.system} title="SYSTEM · SIMULATION STATE" sub="mutation tournament · strategy dominance">
      <div className="mb-2">
        <div className="flex items-center justify-between">
          <span className={`rounded border px-2 py-0.5 font-mono text-[10px] ${achieved ? "border-teal-500/40 bg-teal-500/10 text-teal-300" : "border-amber-500/40 bg-amber-500/10 text-amber-300"}`}>
            {achieved ? "DOMINANCE ACHIEVED" : "PENDING"}
          </span>
          <span className="font-mono text-[9px] text-slate-600">{simulation.tournament_runs ?? 0} tournaments</span>
        </div>
        {champion && (
          <p className="mt-1 truncate font-mono text-[10px] text-slate-300">
            champion: {champion}
          </p>
        )}
      </div>
      <div className="space-y-1.5">
        {entries.slice(0, 4).map(([id, s]) => (
          <div key={id}>
            <div className="flex items-baseline justify-between">
              <span className={`truncate text-[10px] ${id === champion ? "text-amber-300" : "text-slate-400"}`}>{id}</span>
              <span className="flex-shrink-0 font-mono text-[9px] text-slate-600">
                {s.wins ?? 0}W/{s.losses ?? 0}L streak={s.current_streak ?? 0}
              </span>
            </div>
            <Bar pct={(s.fitness ?? 0) * 100} color={id === champion ? "bg-amber-500" : "bg-slate-600"} h="h-1" />
          </div>
        ))}
      </div>
    </PanelWrap>
  );
}

const COMPONENT_LABEL: Record<string, string> = {
  cross_bus_router: "CrossBus Router",
  governance_router: "Gov Router",
  cognition_scheduler: "Cog Scheduler",
  memory_coordinator: "Memory Coord",
  telemetry_aggregator: "Telemetry Agg",
  state_sync: "State Sync",
  cognitive_spine: "Cog Spine",
};

function OrchestrationPanel({ kernel }: { kernel: KernelStatusResponse }) {
  const components = kernel.components ?? {};
  const entries = Object.entries(components);

  return (
    <PanelWrap color={SECTION_BORDER.system} title="SYSTEM · ORCHESTRATION" sub="unified cognitive kernel · 7 subsystems">
      <div className="mb-1.5 flex items-center gap-2">
        <Dot active={kernel.active ?? false} />
        <span className="font-mono text-[10px] text-slate-400">
          {kernel.active ? "KERNEL ACTIVE" : "KERNEL OFFLINE"} · tick #{(kernel.tick_seq ?? 0).toLocaleString()}
        </span>
      </div>
      <div className="space-y-1">
        {entries.map(([key, c]) => (
          <div key={key} className="flex items-center gap-2">
            <Dot active={c.active ?? false} />
            <span className="flex-1 text-[10px] text-slate-300">
              {COMPONENT_LABEL[key] ?? key}
            </span>
            <span className="font-mono text-[9px] text-slate-600">{c.type ?? "?"}</span>
          </div>
        ))}
        {entries.length === 0 && (
          <p className="text-center text-[11px] text-slate-600">No kernel data</p>
        )}
      </div>
    </PanelWrap>
  );
}

// ─── Section wrapper ──────────────────────────────────────────────────────────

const SECTION_META = {
  indira: { label: "INDIRA", color: "text-violet-400", border: "border-violet-800/40", bg: "bg-violet-900/10", icon: Brain },
  dyon:   { label: "DYON",   color: "text-teal-400",   border: "border-teal-800/40",   bg: "bg-teal-900/10",   icon: Cpu },
  system: { label: "SYSTEM", color: "text-amber-400",  border: "border-amber-800/40",  bg: "bg-amber-900/10",  icon: Network },
};

function SectionDivider({ section, count }: { section: keyof typeof SECTION_META; count: number }) {
  const meta = SECTION_META[section];
  const Icon = meta.icon;
  return (
    <div className={`flex items-center gap-2 rounded border ${meta.border} ${meta.bg} px-3 py-1.5`}>
      <Icon className={`h-3.5 w-3.5 ${meta.color}`} />
      <span className={`font-mono text-[10px] font-semibold uppercase tracking-widest ${meta.color}`}>{meta.label}</span>
      <span className="font-mono text-[10px] text-slate-600">{count} panels</span>
    </div>
  );
}

// ─── CognitiveObservatory ─────────────────────────────────────────────────────

const PANEL_H = "h-[220px]";
const PANEL_H_FULL = "h-[280px]";

export function CognitiveObservatory() {
  const [section, setSection] = useState<Section>("all");
  const [data, setData] = useState<ObsState>(SEED);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function fetchAll() {
      const ctrl = new AbortController();
      abortRef.current = ctrl;
      const sig = ctrl.signal;

      const [
        cResp, causalResp, clustersResp,
        spineResp, driftResp, repoResp, deadResp, pipelineResp, engResp,
        telResp, simResp, memResp, govResp, kernelResp,
      ] = await Promise.allSettled([
        fetchIndiraConsciousness(60, sig),
        fetchIndiraCausal(sig),
        fetchIndiraClusters(sig),
        fetchCognitiveSpine(sig),
        fetchDyonDrift(sig),
        fetchDyonRepo(sig),
        fetchDyonDeadCode(sig),
        fetchEvolutionPipeline(sig),
        fetchDyonEngineering(sig),
        fetchTelemetrySummary(sig),
        fetchSimulationDominance(sig),
        fetchMemorySnapshot(sig),
        fetchGovernanceStore(sig),
        fetchKernelStatus(sig),
      ]);

      if (cancelled) return;

      const ok = [cResp, causalResp, clustersResp, spineResp, driftResp, repoResp,
                  deadResp, pipelineResp, engResp, telResp, simResp, memResp, govResp, kernelResp
                 ].some((r) => r.status === "fulfilled");

      setData((prev) => ({
        consciousness: cResp.status === "fulfilled" ? (cResp.value.entries ?? prev.consciousness) : prev.consciousness,
        clusters:      clustersResp.status === "fulfilled" ? (clustersResp.value.clusters ?? prev.clusters) : prev.clusters,
        hypotheses:    causalResp.status === "fulfilled" ? (causalResp.value.active_hypotheses ?? prev.hypotheses) : prev.hypotheses,
        topChain:      causalResp.status === "fulfilled" ? (causalResp.value.top_chain ?? prev.topChain) : prev.topChain,
        spine:         spineResp.status === "fulfilled" ? spineResp.value : prev.spine,
        drift:         driftResp.status === "fulfilled" ? driftResp.value : prev.drift,
        repo:          repoResp.status === "fulfilled" ? repoResp.value : prev.repo,
        deadCode:      deadResp.status === "fulfilled" ? deadResp.value : prev.deadCode,
        pipeline:      pipelineResp.status === "fulfilled" ? pipelineResp.value : prev.pipeline,
        engineering:   engResp.status === "fulfilled" ? engResp.value : prev.engineering,
        telemetry:     telResp.status === "fulfilled" ? telResp.value : prev.telemetry,
        simulation:    simResp.status === "fulfilled" ? simResp.value : prev.simulation,
        memory:        memResp.status === "fulfilled" ? memResp.value : prev.memory,
        governance:    govResp.status === "fulfilled" ? govResp.value : prev.governance,
        kernel:        kernelResp.status === "fulfilled" ? kernelResp.value : prev.kernel,
        live:          ok,
        lastUpdate:    Date.now(),
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

  const ph = section === "all" ? PANEL_H : PANEL_H_FULL;

  const TABS: { key: Section; label: string }[] = [
    { key: "all",    label: "ALL" },
    { key: "indira", label: "INDIRA" },
    { key: "dyon",   label: "DYON" },
    { key: "system", label: "SYSTEM" },
  ];

  const tabColor = (key: Section) => {
    if (key === "indira") return "border-violet-500 text-violet-300";
    if (key === "dyon")   return "border-teal-500 text-teal-300";
    if (key === "system") return "border-amber-500 text-amber-300";
    return "border-accent text-accent";
  };

  const showIndira = section === "all" || section === "indira";
  const showDyon   = section === "all" || section === "dyon";
  const showSystem = section === "all" || section === "system";

  const now = new Date(data.lastUpdate);
  const ts = `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}:${String(now.getSeconds()).padStart(2, "0")}`;

  return (
    <div className="flex h-full flex-col overflow-hidden rounded border border-border bg-bg">
      {/* Observatory header */}
      <header className="flex flex-shrink-0 items-center justify-between border-b border-border px-4 py-2">
        <div className="flex items-center gap-2.5">
          <Telescope className="h-4 w-4 text-slate-400" />
          <span className="font-mono text-[11px] font-semibold uppercase tracking-widest text-slate-300">
            COGNITIVE OBSERVATORY
          </span>
          <span className="font-mono text-[10px] text-slate-600">· 17 panels</span>
        </div>
        <div className="flex items-center gap-3">
          {/* Tab switcher */}
          <div className="flex gap-0 rounded border border-border/60 bg-bg/40">
            {TABS.map(({ key, label }) => (
              <button
                key={key}
                type="button"
                onClick={() => setSection(key)}
                className={`border-b-2 px-3 py-1 font-mono text-[10px] uppercase tracking-wider transition-colors ${
                  section === key ? tabColor(key) : "border-transparent text-slate-600 hover:text-slate-400"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-1.5">
            <span className={`h-1.5 w-1.5 rounded-full ${data.live ? "bg-emerald-400" : "bg-slate-600"}`} />
            <span className={`font-mono text-[10px] ${data.live ? "text-emerald-400" : "text-slate-600"}`}>
              {data.live ? "LIVE" : "SIM"} {ts}
            </span>
          </div>
        </div>
      </header>

      {/* Panel grid */}
      <div className="min-h-0 flex-1 overflow-auto p-3 space-y-4">
        {/* INDIRA section */}
        {showIndira && (
          <div>
            <SectionDivider section="indira" count={6} />
            <div className="mt-2 grid grid-cols-1 gap-2 md:grid-cols-2 lg:grid-cols-3">
              <div className={ph}><ReasoningStreamPanel entries={data.consciousness} /></div>
              <div className={ph}><TraderClustersPanel clusters={data.clusters} /></div>
              <div className={ph}><CausalGraphPanel hypotheses={data.hypotheses} topChain={data.topChain} /></div>
              <div className={ph}><RegimeMapPanel /></div>
              <div className={ph}><UncertaintyPanel hypotheses={data.hypotheses} /></div>
              <div className={ph}><ConfidenceEvolutionPanel entries={data.consciousness} /></div>
            </div>
          </div>
        )}

        {/* DYON section */}
        {showDyon && (
          <div>
            <SectionDivider section="dyon" count={5} />
            <div className="mt-2 grid grid-cols-1 gap-2 md:grid-cols-2 lg:grid-cols-3">
              <div className={ph}><RepoEvolutionPanel repo={data.repo} /></div>
              <div className={ph}><RuntimeHealthPanel spine={data.spine} /></div>
              <div className={ph}><ArchDriftPanel drift={data.drift} /></div>
              <div className={ph}><MutationTrackingPanel pipeline={data.pipeline} /></div>
              <div className={ph}><OptimizationPanel deadCode={data.deadCode} /></div>
            </div>
          </div>
        )}

        {/* SYSTEM section */}
        {showSystem && (
          <div>
            <SectionDivider section="system" count={6} />
            <div className="mt-2 grid grid-cols-1 gap-2 md:grid-cols-2 lg:grid-cols-3">
              <div className={ph}><EventThroughputPanel telemetry={data.telemetry} /></div>
              <div className={ph}><CognitionLatencyPanel spine={data.spine} /></div>
              <div className={ph}><GovernanceActionsPanel governance={data.governance} /></div>
              <div className={ph}><MemoryGrowthPanel memory={data.memory} /></div>
              <div className={ph}><SimulationStatePanel simulation={data.simulation} /></div>
              <div className={ph}><OrchestrationPanel kernel={data.kernel} /></div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
