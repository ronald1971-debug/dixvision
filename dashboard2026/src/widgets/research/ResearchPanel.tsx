/**
 * Research Panel widget (BUILD-DIRECTIVE §24 — research widget).
 *
 * Interface for submitting and viewing browser research tasks.
 * Shows active research tasks and their results.
 */

import { useState } from "react";

interface ResearchTask {
  id: string;
  task_type: string;
  query: string;
  status: string;
}

const TASK_TYPES = [
  { value: "TRADER_PROFILE", label: "Trader Profile" },
  { value: "MARKET_ANALYSIS", label: "Market Analysis" },
  { value: "STRATEGY_REPORT", label: "Strategy Report" },
  { value: "NEWS_DEEP_DIVE", label: "News Deep Dive" },
  { value: "ACADEMIC_PAPER", label: "Academic Paper" },
];

const STATUS_COLOR: Record<string, string> = {
  COMPLETED: "text-emerald-400",
  FAILED: "text-rose-400",
  NO_URLS: "text-amber-400",
};

export function ResearchPanel() {
  const [tasks, setTasks] = useState<ResearchTask[]>([]);
  const [query, setQuery] = useState("");
  const [taskType, setTaskType] = useState("TRADER_PROFILE");
  const [submitting, setSubmitting] = useState(false);

  const submitResearch = () => {
    const q = query.trim();
    if (!q || submitting) return;
    setSubmitting(true);
    fetch("/api/research/submit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ task_type: taskType, query: q }),
    })
      .then((r) => r.json())
      .then((data: Partial<ResearchTask>) => {
        setTasks((t) => [
          { id: String(Date.now()), task_type: taskType, query: q, status: "PENDING", ...data },
          ...t,
        ]);
        setQuery("");
      })
      .catch(() => {
        setTasks((t) => [
          { id: String(Date.now()), task_type: taskType, query: q, status: "FAILED" },
          ...t,
        ]);
      })
      .finally(() => setSubmitting(false));
  };

  return (
    <section className="flex h-full flex-col rounded border border-border bg-surface">
      <header className="border-b border-border px-3 py-2">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-300">
          Browser Research
        </h3>
        <p className="mt-0.5 text-[11px] text-slate-500">
          sandboxed · read-only · no execution
        </p>
      </header>

      <div className="flex gap-2 border-b border-border/60 p-3">
        <select
          value={taskType}
          onChange={(e) => setTaskType(e.target.value)}
          className="rounded border border-border bg-bg/40 px-2 py-1 text-[11px] text-slate-200"
        >
          {TASK_TYPES.map((t) => (
            <option key={t.value} value={t.value}>
              {t.label}
            </option>
          ))}
        </select>
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Research query or URL…"
          onKeyDown={(e) => e.key === "Enter" && submitResearch()}
          className="min-w-0 flex-1 rounded border border-border bg-bg/40 px-2 py-1 text-[11px] text-slate-200 placeholder:text-slate-600 focus:border-accent/60 focus:outline-none"
        />
        <button
          type="button"
          onClick={submitResearch}
          disabled={submitting || !query.trim()}
          className="rounded border border-accent/40 bg-accent/10 px-3 py-1 text-[11px] text-accent hover:bg-accent/20 disabled:opacity-40"
        >
          {submitting ? "…" : "Submit"}
        </button>
      </div>

      <div className="flex-1 overflow-auto">
        {tasks.length === 0 ? (
          <p className="px-3 py-4 text-[11px] text-slate-600">
            No research tasks yet.
          </p>
        ) : (
          <table className="w-full text-[11px]">
            <thead className="sticky top-0 bg-surface text-[10px] uppercase tracking-wider text-slate-500">
              <tr className="border-b border-border">
                <th className="px-3 py-1.5 text-left">type</th>
                <th className="px-3 py-1.5 text-left">query</th>
                <th className="px-3 py-1.5 text-right">status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/40">
              {tasks.map((t) => (
                <tr key={t.id}>
                  <td className="px-3 py-1.5 font-mono text-slate-400">
                    {t.task_type}
                  </td>
                  <td className="max-w-xs truncate px-3 py-1.5 text-slate-300">
                    {t.query}
                  </td>
                  <td
                    className={`px-3 py-1.5 text-right font-mono ${
                      STATUS_COLOR[t.status] ?? "text-slate-400"
                    }`}
                  >
                    {t.status}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  );
}
