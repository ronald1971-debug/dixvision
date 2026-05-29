import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

import {
  fetchDecisions,
  fetchOperatorActions,
  fetchOverrideLog,
  fetchSliders,
  setSlider,
} from "@/api/audit";

function DecisionRow({ d }: { d: { id: string; ts_utc: string; action: string; reason: string; strategy_id?: string; outcome?: string; approved_by?: string } }) {
  return (
    <tr className="border-t border-border align-top text-xs">
      <td className="px-3 py-2 font-mono text-slate-400 whitespace-nowrap">{d.ts_utc}</td>
      <td className="px-3 py-2 font-mono text-slate-300">{d.strategy_id ?? "—"}</td>
      <td className="px-3 py-2 text-slate-200">{d.action}</td>
      <td className="px-3 py-2 text-slate-400">{d.reason}</td>
      <td className="px-3 py-2 text-slate-500">{d.outcome ?? "—"}</td>
      <td className="px-3 py-2 text-slate-500">{d.approved_by ?? "—"}</td>
    </tr>
  );
}

function DecisionTraceTab() {
  const [strategyId, setStrategyId] = useState("");
  const { data, isPending, isError, error } = useQuery({
    queryKey: ["audit", "decisions", strategyId],
    queryFn: ({ signal }) => fetchDecisions(strategyId || undefined, 50, signal),
    refetchInterval: 10_000,
  });

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <input
          type="text"
          placeholder="Filter by strategy id…"
          value={strategyId}
          onChange={(e) => setStrategyId(e.target.value)}
          className="w-64 rounded border border-border bg-bg px-2 py-1 text-xs text-slate-200 placeholder-slate-500 focus:border-accent focus:outline-none"
        />
      </div>
      {isPending && <p className="text-sm text-slate-400">Loading…</p>}
      {isError && (
        <p className="text-sm text-danger">{(error as Error).message}</p>
      )}
      {data && (
        <div className="overflow-auto">
          <table className="w-full text-left">
            <thead className="text-[10px] uppercase tracking-wider text-slate-500">
              <tr>
                <th className="px-3 py-2">timestamp</th>
                <th className="px-3 py-2">strategy</th>
                <th className="px-3 py-2">action</th>
                <th className="px-3 py-2">reason</th>
                <th className="px-3 py-2">outcome</th>
                <th className="px-3 py-2">approved by</th>
              </tr>
            </thead>
            <tbody>
              {data.decisions.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-3 py-6 text-center text-sm text-slate-500">
                    No decisions recorded
                  </td>
                </tr>
              ) : (
                data.decisions.map((d) => <DecisionRow key={d.id} d={d} />)
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

const SLIDER_LABELS: Record<string, string> = {
  max_order_size_usd: "Max order size (USD)",
  max_position_pct: "Max position %",
  circuit_breaker_drawdown: "Circuit breaker drawdown",
  circuit_breaker_loss_pct: "Circuit breaker loss %",
};

function RiskSlidersTab() {
  const qc = useQueryClient();
  const { data, isPending, isError, error } = useQuery({
    queryKey: ["risk", "sliders"],
    queryFn: ({ signal }) => fetchSliders(signal),
    refetchInterval: 10_000,
  });

  const mutation = useMutation({
    mutationFn: ({ slider, value }: { slider: string; value: number }) =>
      setSlider(slider, value),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["risk", "sliders"] }),
  });

  const [draft, setDraft] = useState<Record<string, string>>({});

  if (isPending) return <p className="text-sm text-slate-400">Loading…</p>;
  if (isError) return <p className="text-sm text-danger">{(error as Error).message}</p>;
  if (!data) return null;

  const sliders = [
    "max_order_size_usd",
    "max_position_pct",
    "circuit_breaker_drawdown",
    "circuit_breaker_loss_pct",
  ] as const;

  return (
    <div className="max-w-lg space-y-4">
      {sliders.map((key) => {
        const bounds = data.bounds[key] as [number, number];
        const current = data[key];
        const draftVal = draft[key] ?? String(current);
        return (
          <div key={key} className="space-y-1">
            <div className="flex items-baseline justify-between">
              <label className="text-xs text-slate-300">
                {SLIDER_LABELS[key] ?? key}
              </label>
              <span className="font-mono text-[10px] text-slate-500">
                [{bounds[0]}, {bounds[1]}]
              </span>
            </div>
            <div className="flex gap-2">
              <input
                type="number"
                min={bounds[0]}
                max={bounds[1]}
                step={bounds[1] > 100 ? 100 : 0.01}
                value={draftVal}
                onChange={(e) => setDraft((d) => ({ ...d, [key]: e.target.value }))}
                className="w-40 rounded border border-border bg-bg px-2 py-1 font-mono text-xs focus:border-accent focus:outline-none"
              />
              <button
                type="button"
                disabled={mutation.isPending}
                onClick={() => {
                  const v = parseFloat(draftVal);
                  if (!isNaN(v)) mutation.mutate({ slider: key, value: v });
                }}
                className="rounded border border-border bg-surface px-3 py-1 text-xs hover:border-accent disabled:opacity-50"
              >
                apply
              </button>
            </div>
            {mutation.isError && (
              <p className="text-xs text-danger">{(mutation.error as Error).message}</p>
            )}
          </div>
        );
      })}
      <p className="text-[10px] text-slate-500">version {data.version_id}</p>
    </div>
  );
}

function OperatorActionsTab() {
  const { data, isPending, isError, error } = useQuery({
    queryKey: ["audit", "actions"],
    queryFn: ({ signal }) => fetchOperatorActions(50, signal),
    refetchInterval: 15_000,
  });

  if (isPending) return <p className="text-sm text-slate-400">Loading…</p>;
  if (isError) return <p className="text-sm text-danger">{(error as Error).message}</p>;
  if (!data) return null;

  return (
    <div className="overflow-auto">
      <table className="w-full text-left">
        <thead className="text-[10px] uppercase tracking-wider text-slate-500">
          <tr>
            <th className="px-3 py-2">timestamp</th>
            <th className="px-3 py-2">kind</th>
            <th className="px-3 py-2">subject</th>
            <th className="px-3 py-2">state</th>
            <th className="px-3 py-2">approvers</th>
          </tr>
        </thead>
        <tbody>
          {data.actions.length === 0 ? (
            <tr>
              <td colSpan={5} className="px-3 py-6 text-center text-sm text-slate-500">
                No operator actions recorded
              </td>
            </tr>
          ) : (
            data.actions.map((a) => (
              <tr key={a.id} className="border-t border-border align-top text-xs">
                <td className="px-3 py-2 font-mono text-slate-400 whitespace-nowrap">{a.ts_utc}</td>
                <td className="px-3 py-2 font-mono text-slate-300">{a.kind}</td>
                <td className="px-3 py-2 text-slate-200">{a.subject}</td>
                <td className="px-3 py-2">
                  <span className={`rounded border px-1.5 py-0.5 font-mono text-[10px] uppercase ${
                    a.state === "APPROVED" ? "border-ok/40 text-ok" :
                    a.state === "DENIED" ? "border-danger/40 text-danger" :
                    "border-border text-slate-400"
                  }`}>{a.state}</span>
                </td>
                <td className="px-3 py-2 text-slate-500">{a.approvers.join(", ") || "—"}</td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

function OverrideLogTab() {
  const { data, isPending, isError, error } = useQuery({
    queryKey: ["audit", "overrides"],
    queryFn: ({ signal }) => fetchOverrideLog(50, signal),
    refetchInterval: 15_000,
  });

  if (isPending) return <p className="text-sm text-slate-400">Loading…</p>;
  if (isError) return <p className="text-sm text-danger">{(error as Error).message}</p>;
  if (!data) return null;

  return (
    <div className="overflow-auto">
      {data.source === "unavailable" && (
        <p className="mb-2 text-xs text-slate-500">Ledger unavailable — no overrides to display</p>
      )}
      <table className="w-full text-left">
        <thead className="text-[10px] uppercase tracking-wider text-slate-500">
          <tr>
            <th className="px-3 py-2">timestamp</th>
            <th className="px-3 py-2">parameter</th>
            <th className="px-3 py-2">old</th>
            <th className="px-3 py-2">new</th>
            <th className="px-3 py-2">operator</th>
            <th className="px-3 py-2">rationale</th>
          </tr>
        </thead>
        <tbody>
          {data.overrides.length === 0 ? (
            <tr>
              <td colSpan={6} className="px-3 py-6 text-center text-sm text-slate-500">
                No overrides recorded
              </td>
            </tr>
          ) : (
            data.overrides.map((o) => (
              <tr key={o.id} className="border-t border-border align-top text-xs">
                <td className="px-3 py-2 font-mono text-slate-400 whitespace-nowrap">{o.ts_utc}</td>
                <td className="px-3 py-2 font-mono text-slate-300">{o.parameter || o.kind}</td>
                <td className="px-3 py-2 font-mono text-slate-500">{String(o.old_value) || "—"}</td>
                <td className="px-3 py-2 font-mono text-slate-200">{String(o.new_value) || "—"}</td>
                <td className="px-3 py-2 text-slate-500">{o.operator_id || "—"}</td>
                <td className="px-3 py-2 text-slate-400">{o.rationale || "—"}</td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

type Tab = "decisions" | "actions" | "overrides" | "sliders";

export function AuditPage() {
  const [tab, setTab] = useState<Tab>("decisions");

  return (
    <section className="flex h-full flex-col">
      <header className="mb-3">
        <h1 className="text-lg font-semibold tracking-tight">Audit</h1>
        <p className="mt-1 text-xs text-slate-400">
          Decision trace and risk sliders. Every operator action is
          recorded in the audit ledger.
        </p>
      </header>
      <div className="mb-3 flex gap-1 border-b border-border">
        {(["decisions", "actions", "overrides", "sliders"] as Tab[]).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={`rounded-t px-4 py-1.5 text-xs transition-colors ${
              tab === t
                ? "border border-b-bg border-border bg-surface text-slate-200"
                : "text-slate-500 hover:text-slate-300"
            }`}
          >
            {t === "decisions" ? "Decision Trace"
              : t === "actions" ? "Operator Actions"
              : t === "overrides" ? "Override Log"
              : "Risk Sliders"}
          </button>
        ))}
      </div>
      <div className="flex-1 overflow-auto pb-6">
        {tab === "decisions" ? <DecisionTraceTab />
          : tab === "actions" ? <OperatorActionsTab />
          : tab === "overrides" ? <OverrideLogTab />
          : <RiskSlidersTab />}
      </div>
    </section>
  );
}
