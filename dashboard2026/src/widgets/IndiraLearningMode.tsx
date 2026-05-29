import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import React, { useMemo, useState } from "react";

import { Activity, BookOpen, Inbox, Lightbulb, Microscope, Search } from "lucide-react";

import {
  fetchIndiraBeliefs,
  fetchIndiraThoughts,
  fetchResearchResults,
  fetchResearchStatus,
  postResearchEnqueue,
} from "@/api/cognitive";

/**
 * Indira Learning Mode panel — surfaces what Indira is *currently
 * learning from*. Live tabs (Research, Thoughts) pull from the
 * COGNITIVE ACTIVATION PHASE backend endpoints. Static tabs
 * (Philosophies, Trader feed, Proposals, Shadow eval) retain
 * representative seed data until the corresponding backends are wired.
 */
type Tab =
  | "research"
  | "thoughts"
  | "philosophies"
  | "feed"
  | "beliefs"
  | "shadow";

// ---------------------------------------------------------------------------
// Static seed data (pre-wired tabs)
// ---------------------------------------------------------------------------

interface PhilosophyRow {
  id: string;
  name: string;
  style: string;
  followers: number;
  philosophy_version: string;
  last_updated: string;
}

interface FeedRow {
  id: string;
  trader: string;
  symbol: string;
  side: "BUY" | "SELL" | "CLOSE";
  size_pct: number;
  ts_iso: string;
}

interface ShadowEval {
  id: string;
  strategy: string;
  sharpe: number;
  max_drawdown_pct: number;
  fill_rate: number;
  news_attribution: number;
  samples: number;
  gate_pass: boolean;
}

const PHILOSOPHIES: PhilosophyRow[] = [
  {
    id: "trader-001",
    name: "@orderflow_jane",
    style: "Microstructure / VWAP reversion",
    followers: 12_400,
    philosophy_version: "v3.2",
    last_updated: "2026-04-19T11:21Z",
  },
  {
    id: "trader-002",
    name: "@perp_savant",
    style: "Funding-flip + liquidation cascade",
    followers: 5_840,
    philosophy_version: "v2.7",
    last_updated: "2026-04-21T08:02Z",
  },
  {
    id: "trader-003",
    name: "@rune_macro",
    style: "FRED / BLS regime overlay",
    followers: 2_010,
    philosophy_version: "v1.4",
    last_updated: "2026-04-18T15:40Z",
  },
];

const FEED: FeedRow[] = [
  { id: "f-001", trader: "@orderflow_jane", symbol: "BTC/USDC", side: "BUY", size_pct: 1.5, ts_iso: "2026-04-21T20:14Z" },
  { id: "f-002", trader: "@perp_savant", symbol: "SOL-PERP", side: "SELL", size_pct: 0.8, ts_iso: "2026-04-21T20:11Z" },
  { id: "f-003", trader: "@rune_macro", symbol: "EUR/USD", side: "CLOSE", size_pct: 0.0, ts_iso: "2026-04-21T20:02Z" },
];

const SHADOW: ShadowEval[] = [
  { id: "s-001", strategy: "vwap_reversion_v3", sharpe: 1.34, max_drawdown_pct: 3.1, fill_rate: 0.97, news_attribution: 0.62, samples: 612, gate_pass: true },
  { id: "s-002", strategy: "funding_flip_v2", sharpe: 0.82, max_drawdown_pct: 4.7, fill_rate: 0.94, news_attribution: 0.41, samples: 380, gate_pass: false },
];

// ---------------------------------------------------------------------------
// Tab metadata
// ---------------------------------------------------------------------------

const TABS: { id: Tab; label: string; icon: React.ComponentType<{ className?: string }>; hint: string; live?: boolean }[] = [
  { id: "research",     label: "Research",     icon: Search,    hint: "P4",      live: true },
  { id: "thoughts",    label: "Thoughts",     icon: Lightbulb, hint: "P1",      live: true },
  { id: "beliefs",     label: "Beliefs",      icon: Activity,  hint: "LIVE",    live: true },
  { id: "philosophies", label: "Philosophies", icon: BookOpen,  hint: "PR #95" },
  { id: "feed",        label: "Trader feed",  icon: Inbox,     hint: "PR #96" },
  { id: "shadow",      label: "Shadow eval",  icon: Microscope, hint: "PR #114" },
];

// ---------------------------------------------------------------------------
// Root widget
// ---------------------------------------------------------------------------

export function IndiraLearningMode() {
  const [tab, setTab] = useState<Tab>("research");

  const body = useMemo(() => {
    switch (tab) {
      case "research":    return <ResearchPanel />;
      case "thoughts":    return <ThoughtsPanel />;
      case "beliefs":     return <BeliefsPanel />;
      case "philosophies": return <PhilosophiesTable rows={PHILOSOPHIES} />;
      case "feed":        return <FeedTable rows={FEED} />;
      case "shadow":      return <ShadowTable rows={SHADOW} />;
    }
  }, [tab]);

  return (
    <div className="flex h-full flex-col rounded border border-border bg-surface text-sm">
      <header className="flex items-baseline justify-between border-b border-border px-3 py-2">
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-300">
            Indira · Learning Mode
          </h3>
          <p className="mt-0.5 text-[11px] text-slate-500">
            research · thoughts · philosophies · proposals · shadow eval
          </p>
        </div>
        <span className="rounded border border-accent/40 bg-accent/10 px-1.5 py-0.5 font-mono text-[10px] text-accent">
          INDIRA-L
        </span>
      </header>

      <nav
        className="flex flex-wrap items-center gap-1 border-b border-border bg-bg/50 px-2 py-1.5"
        role="tablist"
        aria-label="Indira learning sections"
      >
        {TABS.map((t) => {
          const Icon = t.icon;
          const active = tab === t.id;
          return (
            <button
              key={t.id}
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => setTab(t.id)}
              className={`flex items-center gap-1.5 rounded border px-2 py-1 font-mono text-[10px] uppercase tracking-wider ${
                active
                  ? "border-accent bg-accent/10 text-accent"
                  : "border-border bg-bg text-slate-400 hover:text-slate-200"
              }`}
            >
              <Icon className="h-3 w-3" />
              {t.label}
              {t.live && (
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" title="live" />
              )}
              <span className="text-[9px] text-slate-600">{t.hint}</span>
            </button>
          );
        })}
      </nav>

      <div className="flex-1 overflow-auto">{body}</div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Research tab — live from AutonomousResearchRuntime
// ---------------------------------------------------------------------------

const TASK_TYPES = [
  "MARKET_ANALYSIS",
  "TRADER_PROFILE",
  "STRATEGY_REPORT",
  "NEWS_DEEP_DIVE",
  "ACADEMIC_PAPER",
];

function ResearchPanel() {
  const qc = useQueryClient();
  const [topic, setTopic] = useState("");
  const [taskType, setTaskType] = useState("MARKET_ANALYSIS");
  const [priority, setPriority] = useState(5);
  const [feedback, setFeedback] = useState<{ ok: boolean; text: string } | null>(null);

  const statusQ = useQuery({
    queryKey: ["cognitive", "research", "status"],
    queryFn: ({ signal }) => fetchResearchStatus(signal),
    refetchInterval: 5_000,
  });

  const resultsQ = useQuery({
    queryKey: ["cognitive", "research", "results"],
    queryFn: ({ signal }) => fetchResearchResults(20, signal),
    refetchInterval: 10_000,
  });

  const enqueue = useMutation({
    mutationFn: (body: Parameters<typeof postResearchEnqueue>[0]) =>
      postResearchEnqueue(body),
    onSuccess: (resp) => {
      setFeedback({ ok: true, text: `Queued — depth now ${resp.queue_depth}` });
      setTopic("");
      void qc.invalidateQueries({ queryKey: ["cognitive", "research"] });
    },
    onError: (err: unknown) => {
      setFeedback({
        ok: false,
        text: err instanceof Error ? err.message : "enqueue failed",
      });
    },
  });

  const status = statusQ.data;
  const results = resultsQ.data?.results ?? [];

  return (
    <div className="flex h-full flex-col divide-y divide-border/50">
      {/* Status bar */}
      <div className="flex items-center gap-4 px-3 py-2 text-[11px]">
        <span className={`font-mono uppercase ${status?.running ? "text-emerald-400" : "text-rose-400"}`}>
          {status?.running ? "● RUNNING" : "● STOPPED"}
        </span>
        <span className="text-slate-500">
          queue <span className="text-slate-200 font-mono">{status?.queue_depth ?? "—"}</span>
        </span>
        <span className="text-slate-500">
          total <span className="text-slate-200 font-mono">{status?.total_runs ?? "—"}</span>
          {" "}/ ok <span className="text-emerald-400 font-mono">{status?.total_ok ?? "—"}</span>
        </span>
        <span className="text-slate-500">
          interval <span className="font-mono text-slate-400">{status?.fetch_interval_s ?? "—"}s</span>
        </span>
      </div>

      {/* Enqueue form */}
      <form
        className="flex flex-col gap-2 px-3 py-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (!topic.trim()) return;
          setFeedback(null);
          enqueue.mutate({ topic: topic.trim(), task_type: taskType, priority, max_pages: 3 });
        }}
      >
        <div className="flex gap-2">
          <input
            type="text"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            placeholder="Research topic (e.g. BTC funding rate regime 2026)"
            maxLength={256}
            className="flex-1 rounded border border-border bg-bg px-2 py-1 text-[11px] text-slate-200 placeholder:text-slate-600 focus:border-accent focus:outline-none"
          />
          <select
            value={taskType}
            onChange={(e) => setTaskType(e.target.value)}
            className="rounded border border-border bg-bg px-2 py-1 font-mono text-[10px] text-slate-400 focus:border-accent focus:outline-none"
          >
            {TASK_TYPES.map((t) => (
              <option key={t} value={t}>{t.replace(/_/g, " ")}</option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-3">
          <label className="font-mono text-[10px] text-slate-500 uppercase">
            Priority
          </label>
          <input
            type="range"
            min={1}
            max={10}
            value={priority}
            onChange={(e) => setPriority(Number(e.target.value))}
            className="w-24"
          />
          <span className="font-mono text-[10px] text-slate-400">{priority}</span>
          <span className="text-[10px] text-slate-600">(1=highest)</span>
          <button
            type="submit"
            disabled={!topic.trim() || enqueue.isPending}
            className="ml-auto rounded border border-accent/40 bg-accent/10 px-3 py-1 font-mono text-[10px] uppercase text-accent hover:bg-accent/20 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {enqueue.isPending ? "QUEUING…" : "ENQUEUE"}
          </button>
        </div>
        {feedback && (
          <p className={`text-[10px] font-mono ${feedback.ok ? "text-emerald-400" : "text-rose-400"}`}>
            {feedback.text}
          </p>
        )}
      </form>

      {/* Queue preview */}
      {(status?.queue_preview?.length ?? 0) > 0 && (
        <div className="px-3 py-1.5">
          <p className="mb-1 font-mono text-[10px] uppercase text-slate-500">Next in queue</p>
          <div className="flex flex-col gap-0.5">
            {status!.queue_preview.map((item, i) => (
              <div key={i} className="flex gap-2 text-[11px]">
                <span className="font-mono text-slate-600">{item.priority}</span>
                <span className="text-slate-300">{item.topic}</span>
                <span className="ml-auto font-mono text-[10px] text-slate-500">{item.task_type}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Recent results */}
      <div className="flex-1 overflow-auto">
        {results.length === 0 ? (
          <p className="px-3 py-4 text-[11px] text-slate-600">
            No research completed yet — topics in queue will appear here.
          </p>
        ) : (
          <table className="w-full text-left text-[11px]">
            <thead className="sticky top-0 bg-surface text-[10px] uppercase tracking-wider text-slate-500">
              <tr>
                <th className="px-3 py-1.5">Topic</th>
                <th className="px-3 py-1.5">Type</th>
                <th className="px-3 py-1.5 text-right">Pages</th>
                <th className="px-3 py-1.5 text-right">Conf</th>
                <th className="px-3 py-1.5 text-right">Trust</th>
                <th className="px-3 py-1.5">Status</th>
              </tr>
            </thead>
            <tbody>
              {results.map((r, i) => (
                <tr key={i} className="border-t border-border/60">
                  <td className="max-w-[16ch] truncate px-3 py-1.5 text-slate-300" title={r.topic}>
                    {r.topic}
                  </td>
                  <td className="px-3 py-1.5 font-mono text-[10px] text-slate-500">
                    {r.task_type.replace(/_/g, " ")}
                  </td>
                  <td className="px-3 py-1.5 text-right font-mono text-slate-400">
                    {r.pages_fetched}
                  </td>
                  <td className="px-3 py-1.5 text-right font-mono text-slate-300">
                    {r.confidence.toFixed(2)}
                  </td>
                  <td className="px-3 py-1.5 text-right font-mono text-slate-400">
                    {r.trust_score.toFixed(2)}
                  </td>
                  <td
                    className={`px-3 py-1.5 font-mono uppercase ${
                      r.status === "COMPLETED"
                        ? "text-emerald-400"
                        : r.status === "FAILED"
                          ? "text-rose-400"
                          : "text-slate-500"
                    }`}
                  >
                    {r.status}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Thoughts tab — live from /api/cognitive/indira/thoughts
// ---------------------------------------------------------------------------

function ThoughtsPanel() {
  const { data, isError, isLoading } = useQuery({
    queryKey: ["cognitive", "indira", "thoughts"],
    queryFn: ({ signal }) => fetchIndiraThoughts(30, signal),
    refetchInterval: 8_000,
  });

  if (isLoading)
    return <p className="px-3 py-4 text-[11px] text-slate-600">Loading thoughts…</p>;
  if (isError)
    return <p className="px-3 py-4 text-[11px] text-rose-400">Failed to load thought stream.</p>;

  const thoughts = data?.thoughts ?? [];

  if (thoughts.length === 0)
    return (
      <p className="px-3 py-4 text-[11px] text-slate-600">
        No thoughts yet — waiting for the first meta-controller tick.
      </p>
    );

  return (
    <div className="flex flex-col divide-y divide-border/40">
      {thoughts.map((t, i) => {
        const p = t.payload ?? {};
        return (
          <div key={i} className="px-3 py-2">
            <div className="flex items-baseline justify-between">
              <span className="font-mono text-[10px] uppercase text-sky-400">
                {p.reasoning_step ?? "THOUGHT"}
              </span>
              <span className="font-mono text-[10px] text-slate-600">
                {typeof p.confidence === "number"
                  ? `conf ${p.confidence.toFixed(2)}`
                  : ""}
              </span>
            </div>
            {p.context && (
              <p className="mt-0.5 text-[11px] leading-snug text-slate-400">{p.context}</p>
            )}
            {p.conclusion && (
              <p className="mt-0.5 text-[11px] leading-snug text-slate-200">{p.conclusion}</p>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Beliefs tab — live from /api/cognitive/indira/beliefs
// ---------------------------------------------------------------------------

function BeliefsPanel() {
  const { data, isError, isLoading } = useQuery({
    queryKey: ["cognitive", "indira", "beliefs"],
    queryFn: ({ signal }) => fetchIndiraBeliefs(30, signal),
    refetchInterval: 10_000,
  });

  if (isLoading)
    return <p className="px-3 py-4 text-[11px] text-slate-600">Loading beliefs…</p>;
  if (isError)
    return <p className="px-3 py-4 text-[11px] text-rose-400">Failed to load belief stream.</p>;

  const beliefs = data?.beliefs ?? [];

  if (beliefs.length === 0)
    return (
      <p className="px-3 py-4 text-[11px] text-slate-600">
        No belief transitions yet — waiting for the first regime shift.
      </p>
    );

  return (
    <div className="flex flex-col divide-y divide-border/40">
      {beliefs.map((b, i) => {
        const p = b.payload ?? {};
        const delta =
          typeof p.new_value === "number" && typeof p.old_value === "number"
            ? p.new_value - p.old_value
            : null;
        return (
          <div key={i} className="px-3 py-2">
            <div className="flex items-baseline justify-between">
              <span className="font-mono text-[10px] uppercase text-violet-400">
                {typeof p.subject === "string" ? p.subject : "BELIEF"}
              </span>
              {delta !== null && (
                <span
                  className={`font-mono text-[10px] ${delta >= 0 ? "text-emerald-400" : "text-rose-400"}`}
                >
                  Δ {delta >= 0 ? "+" : ""}{delta.toFixed(3)}
                </span>
              )}
            </div>
            <div className="mt-0.5 flex gap-3 text-[11px] text-slate-400">
              {typeof p.old_value === "number" && (
                <span>
                  <span className="text-slate-600">from </span>
                  <span className="font-mono">{p.old_value.toFixed(3)}</span>
                </span>
              )}
              {typeof p.new_value === "number" && (
                <span>
                  <span className="text-slate-600">to </span>
                  <span className="font-mono text-slate-200">{p.new_value.toFixed(3)}</span>
                </span>
              )}
              {typeof p.confidence === "number" && (
                <span className="ml-auto font-mono text-[10px] text-slate-500">
                  conf {p.confidence.toFixed(2)}
                </span>
              )}
            </div>
            {typeof p.driver === "string" && p.driver && (
              <p className="mt-0.5 font-mono text-[10px] text-slate-600">{p.driver}</p>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Static tab body components
// ---------------------------------------------------------------------------

function PhilosophiesTable({ rows }: { rows: PhilosophyRow[] }) {
  return (
    <table className="w-full table-fixed text-left text-[11px]">
      <thead className="sticky top-0 bg-surface text-[10px] uppercase tracking-wider text-slate-500">
        <tr>
          <th className="w-1/4 px-3 py-1.5">Trader</th>
          <th className="w-2/5 px-3 py-1.5">Style</th>
          <th className="w-1/12 px-3 py-1.5 text-right">Followers</th>
          <th className="w-1/12 px-3 py-1.5">Version</th>
          <th className="w-1/4 px-3 py-1.5">Updated</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.id} className="border-t border-border/60">
            <td className="px-3 py-1.5 font-mono text-accent">{r.name}</td>
            <td className="px-3 py-1.5 text-slate-300">{r.style}</td>
            <td className="px-3 py-1.5 text-right text-slate-400">{r.followers.toLocaleString()}</td>
            <td className="px-3 py-1.5 font-mono text-slate-500">{r.philosophy_version}</td>
            <td className="px-3 py-1.5 font-mono text-slate-500">{r.last_updated}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function FeedTable({ rows }: { rows: FeedRow[] }) {
  return (
    <table className="w-full table-fixed text-left text-[11px]">
      <thead className="sticky top-0 bg-surface text-[10px] uppercase tracking-wider text-slate-500">
        <tr>
          <th className="w-1/3 px-3 py-1.5">Trader</th>
          <th className="w-1/6 px-3 py-1.5">Symbol</th>
          <th className="w-1/6 px-3 py-1.5">Side</th>
          <th className="w-1/6 px-3 py-1.5 text-right">Size %</th>
          <th className="w-1/6 px-3 py-1.5">When</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.id} className="border-t border-border/60">
            <td className="px-3 py-1.5 font-mono text-accent">{r.trader}</td>
            <td className="px-3 py-1.5 text-slate-300">{r.symbol}</td>
            <td className={`px-3 py-1.5 font-mono uppercase ${r.side === "BUY" ? "text-emerald-400" : r.side === "SELL" ? "text-rose-400" : "text-slate-400"}`}>
              {r.side}
            </td>
            <td className="px-3 py-1.5 text-right font-mono text-slate-300">{r.size_pct.toFixed(2)}</td>
            <td className="px-3 py-1.5 font-mono text-slate-500">{r.ts_iso}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function ShadowTable({ rows }: { rows: ShadowEval[] }) {
  return (
    <table className="w-full table-fixed text-left text-[11px]">
      <thead className="sticky top-0 bg-surface text-[10px] uppercase tracking-wider text-slate-500">
        <tr>
          <th className="w-1/5 px-3 py-1.5">Strategy</th>
          <th className="w-1/12 px-3 py-1.5 text-right">Sharpe</th>
          <th className="w-1/12 px-3 py-1.5 text-right">DD%</th>
          <th className="w-1/12 px-3 py-1.5 text-right">Fill</th>
          <th className="w-1/12 px-3 py-1.5 text-right">News</th>
          <th className="w-1/12 px-3 py-1.5 text-right">N</th>
          <th className="w-1/6 px-3 py-1.5">Gate</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.id} className="border-t border-border/60">
            <td className="px-3 py-1.5 font-mono text-accent">{r.strategy}</td>
            <td className="px-3 py-1.5 text-right font-mono text-slate-300">{r.sharpe.toFixed(2)}</td>
            <td className="px-3 py-1.5 text-right font-mono text-slate-300">{r.max_drawdown_pct.toFixed(1)}</td>
            <td className="px-3 py-1.5 text-right font-mono text-slate-300">{(r.fill_rate * 100).toFixed(0)}%</td>
            <td className="px-3 py-1.5 text-right font-mono text-slate-300">{(r.news_attribution * 100).toFixed(0)}%</td>
            <td className="px-3 py-1.5 text-right font-mono text-slate-500">{r.samples}</td>
            <td className={`px-3 py-1.5 font-mono uppercase ${r.gate_pass ? "text-emerald-400" : "text-rose-400"}`}>
              {r.gate_pass ? "PASS" : "FAIL"}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
