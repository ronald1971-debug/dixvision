import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

import { fetchScout, runScout, type ScoutCandidate } from "@/api/scout";

function CandidateCard({ c }: { c: ScoutCandidate }) {
  return (
    <div className="flex flex-col gap-1 rounded border border-border bg-surface px-3 py-2.5">
      <div className="flex items-center gap-2">
        <span className="font-mono text-sm font-semibold text-slate-200">
          {c.symbol}
        </span>
        {c.score !== undefined && (
          <span className="rounded border border-border px-1.5 py-0.5 font-mono text-[10px] text-slate-400">
            score {c.score.toFixed(2)}
          </span>
        )}
        {(c.tags ?? []).map((t) => (
          <span
            key={t}
            className="rounded border border-border px-1 py-0.5 text-[9px] uppercase tracking-wider text-slate-500"
          >
            {t}
          </span>
        ))}
      </div>
      <p className="text-xs text-slate-400">{c.reason}</p>
    </div>
  );
}

export function ScoutPage() {
  const qc = useQueryClient();
  const [runError, setRunError] = useState<string | null>(null);

  const { data, isPending, isError, error } = useQuery({
    queryKey: ["scout"],
    queryFn: ({ signal }) => fetchScout(signal),
    refetchInterval: 30_000,
  });

  const mutation = useMutation({
    mutationFn: () => runScout(),
    onSuccess: () => {
      setRunError(null);
      qc.invalidateQueries({ queryKey: ["scout"] });
    },
    onError: (e: Error) => setRunError(e.message),
  });

  return (
    <section className="flex h-full flex-col">
      <header className="mb-3 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-lg font-semibold tracking-tight">
            Weekly Scout
            {data && data.finished_utc && (
              <span className="ml-3 font-mono text-[11px] uppercase tracking-widest text-slate-400">
                last run {data.finished_utc}
              </span>
            )}
          </h1>
          <p className="mt-1 text-xs text-slate-400">
            DYON weekly market scan — surface candidates for the operator
            strategy pipeline. Runs automatically on the DYON schedule;
            use the button to run on demand.
          </p>
        </div>
        <button
          type="button"
          onClick={() => mutation.mutate()}
          disabled={mutation.isPending}
          className="shrink-0 rounded border border-border bg-surface px-4 py-1.5 text-xs hover:border-accent disabled:opacity-50"
        >
          {mutation.isPending ? "running…" : "run scout"}
        </button>
      </header>

      {runError && (
        <div className="mb-2 rounded border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">
          {runError}
        </div>
      )}

      {isPending && <p className="text-sm text-slate-400">Loading…</p>}

      {isError && (
        <div className="rounded border border-danger/40 bg-danger/10 p-3 text-sm text-danger">
          {(error as Error).message}
        </div>
      )}

      {data && (
        <div className="flex-1 space-y-4 overflow-auto pb-6">
          {data.errors.length > 0 && (
            <div className="rounded border border-warn/40 bg-warn/10 px-3 py-2 text-xs text-warn">
              Scan errors: {data.errors.join(" · ")}
            </div>
          )}
          <div>
            <h2 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">
              Candidates ({data.candidates.length})
            </h2>
            {data.candidates.length === 0 ? (
              <p className="rounded border border-border bg-surface px-3 py-6 text-center text-sm text-slate-500">
                No candidates from last scan
              </p>
            ) : (
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
                {data.candidates.map((c) => (
                  <CandidateCard key={c.symbol} c={c} />
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
