import { useEffect, useState } from "react";

import { Activity, Brain, GitBranch, Layers, Lightbulb, Radio, Telescope } from "lucide-react";

import { useCognitiveStream } from "@/state/cognitive_realtime";

/**
 * INDIRA Cognitive Observability Stream (BUILD-DIRECTIVE §P0-COG).
 *
 * Real-time feed of INDIRA's internal cognitive events:
 *   THOUGHT_STREAM      — reasoning steps and conclusions
 *   BELIEF_EVOLUTION    — belief delta with driver
 *   MEMORY_FORMATION    — episodic/semantic/procedural memory writes
 *   CONFIDENCE_SHIFT    — confidence delta exceeding threshold (±0.04)
 *   CAUSAL_CHAIN        — hypothesis → causes → effects graph
 *   RESEARCH_DISCOVERY  — browser-research findings
 *
 * Backend: GET /api/cognitive/indira/stream (SSE / WS fan-out of
 * state.ledger INTELLIGENCE event stream filtered by source=INDIRA).
 *
 * Seeded deterministically so the panel is informative before the
 * live stream is wired.
 */
type EventKind =
  | "THOUGHT_STREAM"
  | "BELIEF_EVOLUTION"
  | "MEMORY_FORMATION"
  | "CONFIDENCE_SHIFT"
  | "CAUSAL_CHAIN"
  | "RESEARCH_DISCOVERY";

interface CogEvent {
  id: string;
  kind: EventKind;
  ts_iso: string;
  summary: string;
  confidence?: number;
  delta?: number;
  detail?: string;
}

const SEED: CogEvent[] = [
  {
    id: "t-001",
    kind: "THOUGHT_STREAM",
    ts_iso: "20:14:02",
    summary: "Regime: TRENDING detected — BTC funding > 0.01% / 8h, OI expanding",
    confidence: 0.82,
    detail: "inputs: funding_rate=0.012, oi_delta=+4.2%, vol_rank=8th",
  },
  {
    id: "b-001",
    kind: "BELIEF_EVOLUTION",
    ts_iso: "20:13:55",
    summary: "BTC short-term trend belief updated",
    delta: +0.14,
    confidence: 0.79,
    detail: "driver: VWAP reclaim + order-flow imbalance +0.31",
  },
  {
    id: "m-001",
    kind: "MEMORY_FORMATION",
    ts_iso: "20:13:40",
    summary: "Episodic: funding-flip setup stored — SOL-PERP / 2026-04-21",
    confidence: 0.71,
    detail: "memory_kind: EPISODIC · replaces: none",
  },
  {
    id: "cs-001",
    kind: "CONFIDENCE_SHIFT",
    ts_iso: "20:13:22",
    summary: "ETH reversal confidence: 0.41 → 0.61 (+0.20)",
    delta: +0.20,
    detail: "driver: CoinDesk shock + CVD divergence",
  },
  {
    id: "cc-001",
    kind: "CAUSAL_CHAIN",
    ts_iso: "20:13:10",
    summary: "Hypo: CPI > est → risk-off → BTC flush → ALT recovery",
    confidence: 0.68,
    detail: "causes: CPI_surprise, USD_strength · effects: BTC_flush, ALT_recovery · evidence: 12",
  },
  {
    id: "rd-001",
    kind: "RESEARCH_DISCOVERY",
    ts_iso: "20:12:58",
    summary: "Research: @perp_savant updated position model v2.7 (trust 0.72)",
    confidence: 0.72,
    detail: "topic: trader_profile:@perp_savant · source: tradingview.com",
  },
  {
    id: "t-002",
    kind: "THOUGHT_STREAM",
    ts_iso: "20:12:44",
    summary: "MetaLabeler p(trade) = 0.71 — above confidence floor 0.55",
    confidence: 0.71,
    detail: "triple-barrier label PASS · horizon: H1 · archetype: vwap_reversion_v3",
  },
  {
    id: "b-002",
    kind: "BELIEF_EVOLUTION",
    ts_iso: "20:12:30",
    summary: "SOL macro regime belief: NEUTRAL → RISK-ON",
    delta: +0.18,
    confidence: 0.65,
    detail: "driver: FRED real-yields compression + BTC correlation 0.88",
  },
];

const KIND_META: Record<EventKind, { icon: typeof Brain; label: string; color: string }> = {
  THOUGHT_STREAM:     { icon: Lightbulb, label: "Thought",   color: "text-sky-400" },
  BELIEF_EVOLUTION:   { icon: Activity,  label: "Belief",    color: "text-violet-400" },
  MEMORY_FORMATION:   { icon: Layers,    label: "Memory",    color: "text-teal-400" },
  CONFIDENCE_SHIFT:   { icon: GitBranch, label: "Confidence",color: "text-amber-400" },
  CAUSAL_CHAIN:       { icon: Brain,     label: "Causal",    color: "text-rose-300" },
  RESEARCH_DISCOVERY: { icon: Telescope, label: "Research",  color: "text-emerald-400" },
};

type Filter = EventKind | "ALL";

export function IndiraCognitiveStream() {
  const [events, setEvents] = useState<CogEvent[]>(SEED);
  const [filter, setFilter] = useState<Filter>("ALL");
  const [expanded, setExpanded] = useState<string | null>(null);

  // Live SSE from /api/cognitive/stream channel "indira"
  const { events: liveEvents, live } = useCognitiveStream<Record<string, unknown>>("indira", 200);
  useEffect(() => {
    if (liveEvents.length === 0) return;
    const row = liveEvents[liveEvents.length - 1];
    // SSE frame: {channel, ts_iso, payload: <db-row>}
    // db-row: {sub_type, source, payload: <cognitive-event-fields>, ...}
    // Cognitive event fields live one level deeper inside row.payload.
    const kind = (row.sub_type ?? row.kind ?? "THOUGHT_STREAM") as EventKind;
    if (!(kind in KIND_META)) return;
    const p = (row.payload ?? {}) as Record<string, unknown>;
    const now = new Date();
    const ts = `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}:${String(now.getSeconds()).padStart(2, "0")}`;
    setEvents((prev) => [
      {
        id: String(p.thought_id ?? p.memory_id ?? p.chain_id ?? p.discovery_id ?? Date.now()),
        kind,
        ts_iso: ts,
        summary: String(p.reasoning_step ?? p.subject ?? p.content_summary ?? p.hypothesis ?? p.topic ?? kind),
        confidence: typeof p.confidence === "number" ? p.confidence : undefined,
        delta: typeof p.delta === "number" ? p.delta : undefined,
        detail: typeof p.conclusion === "number"
          ? String(p.conclusion)
          : p.conclusion
            ? `conclusion: ${p.conclusion}`
            : p.driver
              ? `driver: ${p.driver}`
              : undefined,
      },
      ...prev.slice(0, 49),
    ]);
  }, [liveEvents]);

  // Simulation fallback when SSE not connected
  useEffect(() => {
    if (live) return; // backend is live — no simulation needed
    let seq = SEED.length;
    const KINDS: EventKind[] = ["THOUGHT_STREAM", "BELIEF_EVOLUTION", "CONFIDENCE_SHIFT", "MEMORY_FORMATION"];
    const ROTATING = [
      "Regime confirmation: vol contraction → breakout watch",
      "Archetype fitness updated: vwap_reversion_v3 → 0.83",
      "Memory consolidated: swing pattern #112",
      "Confidence shift: regime-trend 0.79 → 0.85",
    ];
    const id = setInterval(() => {
      const kind = KINDS[seq % KINDS.length];
      const now = new Date();
      const ts = `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}:${String(now.getSeconds()).padStart(2, "0")}`;
      setEvents((prev) => [
        {
          id: `sim-${seq}`,
          kind,
          ts_iso: ts,
          summary: ROTATING[seq % ROTATING.length],
          confidence: 0.5 + (seq % 5) * 0.08,
          delta: kind === "BELIEF_EVOLUTION" || kind === "CONFIDENCE_SHIFT"
            ? (seq % 3 === 0 ? 0.06 : -0.05)
            : undefined,
        },
        ...prev.slice(0, 49),
      ]);
      seq += 1;
    }, 6_000);
    return () => clearInterval(id);
  }, [live]);

  const visible =
    filter === "ALL" ? events : events.filter((e) => e.kind === filter);

  return (
    <section className="flex h-full flex-col rounded border border-border bg-surface">
      <header className="flex items-baseline justify-between border-b border-border px-3 py-2">
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-300">
            INDIRA · Cognitive Stream
          </h3>
          <p className="mt-0.5 text-[11px] text-slate-500">
            thought · belief · memory · confidence · causal · research
          </p>
        </div>
        <div className="flex items-center gap-1.5">
          <Radio className={`h-3 w-3 ${live ? "text-emerald-400" : "text-slate-600"}`} />
          <span className="rounded border border-violet-500/40 bg-violet-500/10 px-1.5 py-0.5 font-mono text-[10px] text-violet-300">
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
                    <span className={`font-mono text-[10px] uppercase ${meta.color}`}>
                      {meta.label}
                    </span>
                    <span className="font-mono text-[10px] text-slate-600">{ev.ts_iso}</span>
                  </div>
                  <p className="mt-0.5 text-[11px] text-slate-300 leading-snug">{ev.summary}</p>
                  {(ev.confidence !== undefined || ev.delta !== undefined) && (
                    <div className="mt-1 flex gap-3">
                      {ev.confidence !== undefined && (
                        <span className="font-mono text-[10px] text-slate-500">
                          conf {ev.confidence.toFixed(2)}
                        </span>
                      )}
                      {ev.delta !== undefined && (
                        <span
                          className={`font-mono text-[10px] ${
                            ev.delta >= 0 ? "text-emerald-400" : "text-rose-400"
                          }`}
                        >
                          Δ {ev.delta >= 0 ? "+" : ""}
                          {ev.delta.toFixed(2)}
                        </span>
                      )}
                    </div>
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
