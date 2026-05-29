import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

import {
  fetchCustomStrategies,
  sandboxStrategy,
  shadowStrategy,
  canaryStrategy,
  retireStrategy,
  type CustomStrategy,
  type StrategyStage,
} from "@/api/strategies";

const STAGE_CLS: Record<StrategyStage, string> = {
  submitted: "border-slate-500 text-slate-400",
  sandbox: "border-blue-500/60 text-blue-400",
  shadow: "border-yellow-500/60 text-yellow-400",
  canary: "border-orange-500/60 text-orange-400",
  live: "border-ok/60 text-ok",
  retired: "border-slate-600 text-slate-600",
};

function StrategyRow({
  s,
  onAction,
  pending,
}: {
  s: CustomStrategy;
  onAction: (action: string, id: string) => void;
  pending: boolean;
}) {
  const nextActions: { label: string; action: string }[] = [];
  if (s.stage === "submitted") nextActions.push({ label: "sandbox", action: "sandbox" });
  if (s.stage === "sandbox") nextActions.push({ label: "shadow", action: "shadow" });
  if (s.stage === "shadow") nextActions.push({ label: "canary", action: "canary" });
  if (s.stage !== "retired" && s.stage !== "live")
    nextActions.push({ label: "retire", action: "retire" });

  return (
    <tr className="border-t border-border align-top text-xs">
      <td className="px-3 py-2 font-mono text-slate-200">{s.name}</td>
      <td className="px-3 py-2 text-slate-400">{s.author}</td>
      <td className="px-3 py-2">
        <span
          className={`inline-block rounded border px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wider ${STAGE_CLS[s.stage] ?? ""}`}
        >
          {s.stage}
        </span>
      </td>
      <td className="px-3 py-2 font-mono text-slate-500">
        {s.submitted_utc}
      </td>
      <td className="px-3 py-2 text-slate-400">
        {s.sandbox_result ?? "—"}
      </td>
      <td className="px-3 py-2">
        <div className="flex gap-1">
          {nextActions.map(({ label, action }) => (
            <button
              key={action}
              type="button"
              disabled={pending}
              onClick={() => onAction(action, s.id)}
              className="rounded border border-border px-2 py-0.5 text-[10px] hover:border-accent disabled:opacity-40"
            >
              {label}
            </button>
          ))}
        </div>
      </td>
    </tr>
  );
}

export function StrategiesPage() {
  const qc = useQueryClient();
  const [actionError, setActionError] = useState<string | null>(null);

  const { data, isPending, isError, error } = useQuery({
    queryKey: ["custom-strategies"],
    queryFn: ({ signal }) => fetchCustomStrategies(signal),
    refetchInterval: 15_000,
  });

  const mutation = useMutation({
    mutationFn: ({ action, id }: { action: string; id: string }) => {
      switch (action) {
        case "sandbox":
          return sandboxStrategy(id);
        case "shadow":
          return shadowStrategy(id);
        case "canary":
          return canaryStrategy(id);
        case "retire":
          return retireStrategy(id, "operator-requested");
        default:
          return Promise.reject(new Error(`Unknown action: ${action}`));
      }
    },
    onSuccess: () => {
      setActionError(null);
      qc.invalidateQueries({ queryKey: ["custom-strategies"] });
    },
    onError: (e: Error) => setActionError(e.message),
  });

  return (
    <section className="flex h-full flex-col">
      <header className="mb-3">
        <h1 className="text-lg font-semibold tracking-tight">
          Custom Strategies
        </h1>
        <p className="mt-1 text-xs text-slate-400">
          Operator-submitted strategy lifecycle: submitted → sandbox → shadow
          → canary → live → retired. All promotions are recorded in the audit
          ledger. Live promotion requires a governance approval request.
        </p>
      </header>

      {actionError && (
        <div className="mb-2 rounded border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">
          {actionError}
        </div>
      )}

      {isPending && <p className="text-sm text-slate-400">Loading…</p>}

      {isError && (
        <div className="rounded border border-danger/40 bg-danger/10 p-3 text-sm text-danger">
          {(error as Error).message}
        </div>
      )}

      {data && (
        <div className="flex-1 overflow-auto pb-6">
          <table className="w-full text-left">
            <thead className="text-[10px] uppercase tracking-wider text-slate-500">
              <tr>
                <th className="px-3 py-2">name</th>
                <th className="px-3 py-2">author</th>
                <th className="px-3 py-2">stage</th>
                <th className="px-3 py-2">submitted</th>
                <th className="px-3 py-2">sandbox result</th>
                <th className="px-3 py-2">actions</th>
              </tr>
            </thead>
            <tbody>
              {data.strategies.length === 0 ? (
                <tr>
                  <td
                    colSpan={6}
                    className="px-3 py-6 text-center text-sm text-slate-500"
                  >
                    No strategies submitted yet
                  </td>
                </tr>
              ) : (
                data.strategies.map((s) => (
                  <StrategyRow
                    key={s.id}
                    s={s}
                    onAction={(action, id) => mutation.mutate({ action, id })}
                    pending={mutation.isPending}
                  />
                ))
              )}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
