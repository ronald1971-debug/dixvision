import { useQuery, useMutation } from "@tanstack/react-query";
import { fetchLedgerTail, verifyLedgerChain, exportLedger } from "@/api/signals";

export function LedgerPage() {
  const tailQ = useQuery({
    queryKey: ["ledger-tail"],
    queryFn: ({ signal }) => fetchLedgerTail(100, "", signal),
    refetchInterval: 5000,
  });

  const verifyQ = useQuery({
    queryKey: ["ledger-verify"],
    queryFn: ({ signal }) => verifyLedgerChain(signal),
    refetchInterval: 30000,
  });

  const exportQ = useMutation({
    mutationFn: () => exportLedger(1000),
    onSuccess: (blob) => {
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `ledger-export-${Date.now()}.jsonl`;
      a.click();
      URL.revokeObjectURL(url);
    },
  });

  const events = tailQ.data?.events ?? [];
  const chainOk = verifyQ.data?.ok ?? null;

  return (
    <section className="flex h-full flex-col">
      <header className="mb-4 flex items-baseline justify-between">
        <div>
          <h1 className="text-lg font-semibold tracking-tight">
            Event-Sourced Ledger
            <span className="ml-2 rounded border border-border bg-bg px-2 py-0.5 font-mono text-[11px] uppercase tracking-widest text-slate-400">LIVE</span>
          </h1>
          <p className="mt-1 text-xs text-slate-400">
            Hash-chained immutable event log with stream filters + JSONL export
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => exportQ.mutate()}
            disabled={exportQ.isPending}
            className="rounded border border-border bg-surface px-3 py-1.5 text-xs hover:border-accent disabled:opacity-50"
          >
            Export JSONL
          </button>
        </div>
      </header>

      {chainOk === true && (
        <div className="mb-4 flex items-center gap-2 rounded border border-ok/30 bg-ok/10 px-4 py-2 text-xs text-ok">
          <span className="font-semibold">Chain: OK</span>
          <span className="text-slate-400">— hash verified to latest seq</span>
        </div>
      )}
      {chainOk === false && (
        <div className="mb-4 flex items-center gap-2 rounded border border-danger/30 bg-danger/10 px-4 py-2 text-xs text-danger">
          <span className="font-semibold">Chain: BROKEN</span>
          <span>Hash chain break detected — investigate immediately</span>
        </div>
      )}

      <div className="flex-1 overflow-auto rounded border border-border bg-surface">
        <table className="w-full text-left text-xs">
          <thead className="sticky top-0 bg-surface text-[10px] uppercase tracking-widest text-slate-500">
            <tr>
              <th className="px-3 py-2">seq</th>
              <th className="px-3 py-2">ts</th>
              <th className="px-3 py-2">stream</th>
              <th className="px-3 py-2">sub_type</th>
              <th className="px-3 py-2">hash_prefix</th>
            </tr>
          </thead>
          <tbody>
            {(!events || events.length === 0) && (
              <tr>
                <td colSpan={5} className="px-3 py-8 text-center text-slate-500">
                  No events in ledger tail.
                </td>
              </tr>
            )}
            {(events as LedgerEvent[]).map((e) => (
              <tr key={e.seq} className="border-t border-border">
                <td className="px-3 py-1.5 font-mono text-slate-300">{e.seq}</td>
                <td className="px-3 py-1.5 font-mono text-slate-400">{e.ts_utc?.split("T")[1]?.split("Z")[0] ?? e.ts_utc}</td>
                <td className="px-3 py-1.5 text-slate-300">{e.stream}</td>
                <td className="px-3 py-1.5 font-mono text-slate-400">{e.sub_type}</td>
                <td className="px-3 py-1.5 font-mono text-slate-500">{e.hash_prefix?.slice(0, 8)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
