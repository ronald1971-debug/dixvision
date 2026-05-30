import { useEffect, useRef, useState } from "react";

import { Activity, Brain, Eye, GitBranch, Radio, Users } from "lucide-react";

import {
  fetchIndiraCausal,
  fetchIndiraClusters,
  fetchIndiraConsciousness,
  fetchIndiraObservations,
  type BehavioralClusterRecord,
  type CausalHypothesisRecord,
  type ConsciousnessEntry,
  type ObservationSessionRecord,
} from "@/api/cognitive";

/**
 * INDIRA Consciousness Panel — Stage 2 cognitive observability.
 *
 * Four tabs:
 *   Stream   — ConsciousnessStream ring buffer (natural language narrative)
 *   Causal   — CausalReasoningGraph active hypotheses
 *   Clusters — BehavioralClusterTracker distribution
 *   Sessions — ObservationSessionManager active sessions
 *
 * Polls /api/cognitive/indira/{consciousness|causal|clusters|observations}
 * every 5 s. Falls back to seed data when backend is unreachable.
 */

type Tab = "stream" | "causal" | "clusters" | "sessions";

// ---------------------------------------------------------------------------
// Seed data
// ---------------------------------------------------------------------------

const SEED_ENTRIES: ConsciousnessEntry[] = [
  {
    entry_id: "e-001",
    ts_ns: 0,
    event_kind: "INDIRA_THOUGHT",
    narrative:
      "BTC regime appears TRENDING — funding rate elevated at 0.012%/8h, open interest expanding +4.2%. Watching for continuation signal.",
    importance: 0.55,
    source: "IndiraRuntime",
    raw_sub_type: "COGNITIVE_TICK",
  },
  {
    entry_id: "e-002",
    ts_ns: 0,
    event_kind: "INDIRA_INSIGHT",
    narrative:
      "Dominant archetype: vwap_reversion_v3 — 12 traders active. Composite score 1.45. Regime alignment STRONG.",
    importance: 0.65,
    source: "BehavioralClusterTracker",
    raw_sub_type: "ARCHETYPE_EVOLUTION",
  },
  {
    entry_id: "e-003",
    ts_ns: 0,
    event_kind: "INDIRA_THOUGHT",
    narrative:
      "Causal chain activating: CPI_surprise → risk-off → BTC_flush. Evidence accumulating (7 signals). Confidence 0.68.",
    importance: 0.68,
    source: "CausalReasoningGraph",
    raw_sub_type: "HYPO_ACTIVATED",
  },
  {
    entry_id: "e-004",
    ts_ns: 0,
    event_kind: "RESEARCH_COMPLETE",
    narrative:
      "Research: @perp_savant updated position model v2.7 — trust 0.72. Integrating into archetype profile.",
    importance: 0.50,
    source: "ResearchRuntime",
    raw_sub_type: "RESEARCH_RESULT",
  },
  {
    entry_id: "e-005",
    ts_ns: 0,
    event_kind: "INDIRA_INSIGHT",
    narrative:
      "Observation session opened: BTC TRENDING regime — 3 hypotheses forming. Session TTL 500 ticks.",
    importance: 0.60,
    source: "ObservationSessionManager",
    raw_sub_type: "SESSION_OPENED",
  },
  {
    entry_id: "e-006",
    ts_ns: 0,
    event_kind: "INDIRA_THOUGHT",
    narrative:
      "MetaLabeler p(trade) = 0.71 — above confidence floor 0.55. Triple-barrier label PASS on H1 horizon.",
    importance: 0.52,
    source: "IndiraRuntime",
    raw_sub_type: "COGNITIVE_TICK",
  },
  {
    entry_id: "e-007",
    ts_ns: 0,
    event_kind: "DYON_VIOLATION",
    narrative:
      "DYON detected cross-layer import violation in execution_engine — severity WARNING. Proposal queued.",
    importance: 0.45,
    source: "DyonRuntime",
    raw_sub_type: "INV_VIOLATION",
  },
];

const SEED_HYPOTHESES: CausalHypothesisRecord[] = [
  { hypo_id: "h-001", label: "cpi_shock_risk_off", state: "ACTIVE", confidence: 0.68, evidence_count: 7, age_ticks: 42 },
  { hypo_id: "h-002", label: "funding_flip_long_squeeze", state: "FORMING", confidence: 0.38, evidence_count: 3, age_ticks: 12 },
  { hypo_id: "h-003", label: "regime_bull_momentum", state: "ACTIVE", confidence: 0.72, evidence_count: 11, age_ticks: 65 },
  { hypo_id: "h-004", label: "whale_accumulation_recovery", state: "FORMING", confidence: 0.34, evidence_count: 2, age_ticks: 8 },
];

const SEED_CLUSTERS: BehavioralClusterRecord[] = [
  { cluster_id: "vwap_reversion_v3", label: "VWAP Reversion", strength: 0.78, composite_score: 1.45, member_count: 12, dominant: true },
  { cluster_id: "momentum_scalper", label: "Momentum Scalper", strength: 0.62, composite_score: 1.02, member_count: 8, dominant: false },
  { cluster_id: "macro_swing_v2", label: "Macro Swing", strength: 0.45, composite_score: 0.68, member_count: 5, dominant: false },
  { cluster_id: "hft_market_make", label: "HFT Market Make", strength: 0.31, composite_score: 0.38, member_count: 3, dominant: false },
];

const SEED_SESSIONS: ObservationSessionRecord[] = [
  { session_id: "s-001", focus_label: "BTC TRENDING", theme: "regime_pattern", state: "ACTIVE", tick_age: 23, hypothesis_count: 3 },
  { session_id: "s-002", focus_label: "vwap_reversion_v3 cluster shift", theme: "archetype_cluster", state: "ACTIVE", tick_age: 11, hypothesis_count: 2 },
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const KIND_COLOR: Record<string, string> = {
  INDIRA_THOUGHT:   "text-sky-400",
  INDIRA_INSIGHT:   "text-violet-400",
  DYON_VIOLATION:   "text-rose-400",
  DYON_PROPOSAL:    "text-amber-400",
  DYON_SCAN_COMPLETE: "text-teal-400",
  RESEARCH_COMPLETE: "text-emerald-400",
  MARKET_TICK:      "text-slate-400",
  RISK_BREACH:      "text-rose-400",
};

function importanceBadge(imp: number): string {
  if (imp >= 0.85) return "border-rose-500/40 bg-rose-500/10 text-rose-300";
  if (imp >= 0.65) return "border-amber-500/40 bg-amber-500/10 text-amber-300";
  if (imp >= 0.45) return "border-teal-500/40 bg-teal-500/10 text-teal-300";
  return "border-slate-600/40 bg-slate-700/20 text-slate-500";
}

function stateColor(state: string): string {
  switch (state) {
    case "ACTIVE":    return "text-emerald-400";
    case "FORMING":   return "text-amber-400";
    case "CONFIRMED": return "text-teal-400";
    case "WEAKENED":  return "text-orange-400";
    case "DISSOLVED": return "text-slate-500";
    default:          return "text-slate-400";
  }
}

// ---------------------------------------------------------------------------
// Sub-renders
// ---------------------------------------------------------------------------

function StreamTab({ entries }: { entries: ConsciousnessEntry[] }) {
  return (
    <div className="flex-1 overflow-auto divide-y divide-border/40">
      {entries.map((e) => (
        <div key={e.entry_id} className="px-3 py-2">
          <div className="flex items-start gap-2">
            <div className="mt-0.5 flex-shrink-0">
              <span
                className={`rounded border px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wider ${importanceBadge(e.importance)}`}
              >
                {(e.importance * 100).toFixed(0)}
              </span>
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-baseline justify-between gap-2">
                <span
                  className={`font-mono text-[10px] uppercase tracking-wide ${KIND_COLOR[e.event_kind] ?? "text-slate-400"}`}
                >
                  {e.event_kind.replace(/_/g, " ")}
                </span>
                <span className="flex-shrink-0 font-mono text-[10px] text-slate-600">
                  {e.source}
                </span>
              </div>
              <p className="mt-0.5 text-[11px] leading-snug text-slate-300">
                {e.narrative}
              </p>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function CausalTab({
  hypotheses,
  topChain,
}: {
  hypotheses: CausalHypothesisRecord[];
  topChain?: { label: string; confidence: number } | null;
}) {
  return (
    <div className="flex-1 overflow-auto">
      {topChain && (
        <div className="border-b border-border/60 bg-violet-500/5 px-3 py-2">
          <span className="font-mono text-[10px] uppercase tracking-wider text-violet-400">
            Top Chain
          </span>
          <p className="mt-0.5 text-[11px] text-slate-200">
            {topChain.label.replace(/_/g, " ")}
          </p>
          <div className="mt-1 h-1 w-full rounded-full bg-slate-700">
            <div
              className="h-1 rounded-full bg-violet-500"
              style={{ width: `${Math.round(topChain.confidence * 100)}%` }}
            />
          </div>
          <span className="font-mono text-[10px] text-slate-500">
            conf {topChain.confidence.toFixed(2)}
          </span>
        </div>
      )}
      <div className="divide-y divide-border/40">
        {hypotheses.map((h) => (
          <div key={h.hypo_id} className="px-3 py-2">
            <div className="flex items-baseline justify-between">
              <span className="text-[11px] text-slate-200">
                {h.label.replace(/_/g, " ")}
              </span>
              <span className={`font-mono text-[10px] ${stateColor(h.state)}`}>
                {h.state}
              </span>
            </div>
            <div className="mt-1 flex items-center gap-3">
              <div className="flex-1">
                <div className="h-1 w-full rounded-full bg-slate-700">
                  <div
                    className={`h-1 rounded-full ${h.confidence >= 0.7 ? "bg-teal-500" : h.confidence >= 0.5 ? "bg-sky-500" : "bg-amber-500"}`}
                    style={{ width: `${Math.round(h.confidence * 100)}%` }}
                  />
                </div>
              </div>
              <span className="font-mono text-[10px] text-slate-500">
                conf {h.confidence.toFixed(2)}
              </span>
              <span className="font-mono text-[10px] text-slate-600">
                ev {h.evidence_count}
              </span>
              <span className="font-mono text-[10px] text-slate-600">
                t+{h.age_ticks}
              </span>
            </div>
          </div>
        ))}
        {hypotheses.length === 0 && (
          <p className="px-3 py-4 text-center text-[11px] text-slate-600">
            No active hypotheses
          </p>
        )}
      </div>
    </div>
  );
}

function ClustersTab({ clusters }: { clusters: BehavioralClusterRecord[] }) {
  const maxScore = Math.max(...clusters.map((c) => c.composite_score), 0.01);
  return (
    <div className="flex-1 overflow-auto divide-y divide-border/40">
      {clusters.map((c) => (
        <div key={c.cluster_id} className="px-3 py-2">
          <div className="flex items-baseline justify-between">
            <div className="flex items-center gap-1.5">
              <span className="text-[11px] text-slate-200">{c.label}</span>
              {c.dominant && (
                <span className="rounded border border-teal-500/40 bg-teal-500/10 px-1 font-mono text-[9px] text-teal-300">
                  DOM
                </span>
              )}
            </div>
            <span className="font-mono text-[10px] text-slate-500">
              {c.member_count} traders
            </span>
          </div>
          <div className="mt-1.5 flex items-center gap-2">
            <div className="flex-1">
              <div className="h-1.5 w-full rounded-full bg-slate-700">
                <div
                  className={`h-1.5 rounded-full ${c.dominant ? "bg-teal-500" : "bg-sky-600"}`}
                  style={{ width: `${Math.round((c.composite_score / maxScore) * 100)}%` }}
                />
              </div>
            </div>
            <span className="font-mono text-[10px] text-slate-500">
              str {c.strength.toFixed(2)}
            </span>
            <span className="font-mono text-[10px] text-slate-600">
              Σ {c.composite_score.toFixed(2)}
            </span>
          </div>
        </div>
      ))}
      {clusters.length === 0 && (
        <p className="px-3 py-4 text-center text-[11px] text-slate-600">
          No behavioral clusters tracked
        </p>
      )}
    </div>
  );
}

function SessionsTab({ sessions }: { sessions: ObservationSessionRecord[] }) {
  return (
    <div className="flex-1 overflow-auto divide-y divide-border/40">
      {sessions.map((s) => (
        <div key={s.session_id} className="px-3 py-2">
          <div className="flex items-baseline justify-between gap-2">
            <span className="text-[11px] font-medium text-slate-200">
              {s.focus_label}
            </span>
            <span className={`flex-shrink-0 font-mono text-[10px] ${stateColor(s.state)}`}>
              {s.state}
            </span>
          </div>
          <div className="mt-0.5 flex items-center gap-3">
            <span className="rounded border border-border px-1.5 font-mono text-[10px] text-slate-500">
              {s.theme}
            </span>
            <span className="font-mono text-[10px] text-slate-600">
              t+{s.tick_age}
            </span>
            <span className="font-mono text-[10px] text-slate-600">
              {s.hypothesis_count} hypo{s.hypothesis_count !== 1 ? "s" : ""}
            </span>
          </div>
        </div>
      ))}
      {sessions.length === 0 && (
        <p className="px-3 py-4 text-center text-[11px] text-slate-600">
          No active observation sessions
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function IndiraConsciousnessPanel() {
  const [tab, setTab] = useState<Tab>("stream");
  const [entries, setEntries] = useState<ConsciousnessEntry[]>(SEED_ENTRIES);
  const [hypotheses, setHypotheses] = useState<CausalHypothesisRecord[]>(SEED_HYPOTHESES);
  const [topChain, setTopChain] = useState<{ label: string; confidence: number } | null | undefined>(
    { label: "regime_bull_momentum", confidence: 0.72 },
  );
  const [clusters, setClusters] = useState<BehavioralClusterRecord[]>(SEED_CLUSTERS);
  const [sessions, setSessions] = useState<ObservationSessionRecord[]>(SEED_SESSIONS);
  const [live, setLive] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function fetchAll() {
      const ctrl = new AbortController();
      abortRef.current = ctrl;
      try {
        const [cResp, causalResp, clustersResp, sessResp] = await Promise.allSettled([
          fetchIndiraConsciousness(60, ctrl.signal),
          fetchIndiraCausal(ctrl.signal),
          fetchIndiraClusters(ctrl.signal),
          fetchIndiraObservations(ctrl.signal),
        ]);
        if (cancelled) return;

        setLive(true);

        if (cResp.status === "fulfilled") {
          setEntries(cResp.value.entries ?? []);
        }
        if (causalResp.status === "fulfilled") {
          setHypotheses(causalResp.value.active_hypotheses ?? []);
          setTopChain(causalResp.value.top_chain ?? null);
        }
        if (clustersResp.status === "fulfilled") {
          setClusters(clustersResp.value.clusters ?? []);
        }
        if (sessResp.status === "fulfilled") {
          setSessions(sessResp.value.sessions ?? []);
        }
      } catch {
        if (!cancelled) setLive(false);
      }
    }

    fetchAll();
    const id = setInterval(fetchAll, 5_000);
    return () => {
      cancelled = true;
      clearInterval(id);
      abortRef.current?.abort();
    };
  }, []);

  const TABS: { key: Tab; label: string; icon: typeof Brain; count?: number }[] = [
    { key: "stream",   label: "Consciousness", icon: Brain,     count: entries.length },
    { key: "causal",   label: "Causal",        icon: GitBranch, count: hypotheses.length },
    { key: "clusters", label: "Clusters",      icon: Users,     count: clusters.length },
    { key: "sessions", label: "Sessions",      icon: Eye,       count: sessions.length },
  ];

  return (
    <section className="flex h-full flex-col rounded border border-border bg-surface">
      {/* Header */}
      <header className="flex items-center justify-between border-b border-border px-3 py-2">
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-300">
            INDIRA · Consciousness
          </h3>
          <p className="mt-0.5 text-[11px] text-slate-500">
            stream · causal chains · behavioral clusters · observation sessions
          </p>
        </div>
        <div className="flex items-center gap-1.5">
          <Activity className={`h-3 w-3 ${live ? "text-violet-400" : "text-slate-600"}`} />
          <span
            className={`rounded border px-1.5 py-0.5 font-mono text-[10px] ${
              live
                ? "border-violet-500/40 bg-violet-500/10 text-violet-300"
                : "border-slate-600/40 bg-slate-700/20 text-slate-500"
            }`}
          >
            {live ? "LIVE" : "SIM"}
          </span>
          <Radio className={`h-3 w-3 ${live ? "text-emerald-400" : "text-slate-600"}`} />
        </div>
      </header>

      {/* Tab bar */}
      <div className="flex gap-0 border-b border-border/60 bg-bg/40">
        {TABS.map(({ key, label, icon: Icon, count }) => (
          <button
            key={key}
            type="button"
            onClick={() => setTab(key)}
            className={`flex items-center gap-1.5 border-b-2 px-3 py-1.5 font-mono text-[10px] uppercase tracking-wider transition-colors ${
              tab === key
                ? "border-violet-500 text-violet-300"
                : "border-transparent text-slate-500 hover:text-slate-300"
            }`}
          >
            <Icon className="h-3 w-3" />
            {label}
            {count !== undefined && count > 0 && (
              <span
                className={`rounded-full px-1 text-[9px] ${
                  tab === key ? "bg-violet-500/20 text-violet-300" : "bg-slate-700 text-slate-500"
                }`}
              >
                {count}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {tab === "stream"   && <StreamTab entries={entries} />}
      {tab === "causal"   && <CausalTab hypotheses={hypotheses} topChain={topChain} />}
      {tab === "clusters" && <ClustersTab clusters={clusters} />}
      {tab === "sessions" && <SessionsTab sessions={sessions} />}
    </section>
  );
}
