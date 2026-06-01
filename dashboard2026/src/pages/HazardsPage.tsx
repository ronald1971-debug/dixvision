import { useQuery } from "@tanstack/react-query";
import { fetchSystemHazards } from "@/api/signals";

export function HazardsPage() {
  const q = useQuery({
    queryKey: ["hazards-page"],
    queryFn: ({ signal }) => fetchSystemHazards(signal),
    refetchInterval: 5000,
  });

  const hazards = q.data?.hazards ?? [];

  return (
    <section className="flex h-full flex-col">
      <header className="mb-4">
        <h1 className="text-lg font-semibold tracking-tight">
          DYON SYSTEM_HAZARD Events
          <span className="ml-2 rounded border border-border bg-bg px-2 py-0.5 font-mono text-[11px] uppercase tracking-widest text-slate-400">LIVE</span>
        </h1>
        <p className="mt-1 text-xs text-slate-400">
          Escalation feed: DYON → GOVERNANCE. Independence verified.
        </p>
      </header>

      <div className="flex-1 overflow-auto rounded border border-border bg-surface">
        {hazards.length === 0 ? (
          <div className="flex h-32 items-center justify-center text-xs text-slate-500">
            No SYSTEM_HAZARD events in current window.
          </div>
        ) : (
          <table className="w-full text-left text-xs">
            <thead className="sticky top-0 bg-surface text-[10px] uppercase tracking-widest text-slate-500">
              <tr>
                <th className="px-3 py-2">ID</th>
                <th className="px-3 py-2">Time</th>
                <th className="px-3 py-2">Hazard Type</th>
                <th className="px-3 py-2">Severity</th>
                <th className="px-3 py-2">Source</th>
                <th className="px-3 py-2">Escalation</th>
              </tr>
            </thead>
            <tbody>
              {hazards.map((h: { id: string; ts_utc: string; hazard_type: string; severity: string; source: string; escalation: string }) => {
                const sevCls =
                  h.severity === "CRITICAL" ? "text-danger"
                  : h.severity === "WARNING" ? "text-warn"
                  : h.severity === "INFO" ? "text-blue-400"
                  : "text-slate-300";
                return (
                  <tr key={h.id} className="border-t border-border">
                    <td className="px-3 py-1.5 font-mono text-slate-400">{h.id.split("-")[1]}</td>
                    <td className="px-3 py-1.5 font-mono text-slate-400">{h.ts_utc?.split("T")[1]?.split("Z")[0]}</td>
                    <td className="px-3 py-1.5 text-slate-200">{h.hazard_type}</td>
                    <td className={`px-3 py-1.5 font-mono uppercase tracking-wider ${sevCls}`}>{h.severity}</td>
                    <td className="px-3 py-1.5 text-slate-400">{h.source}</td>
                    <td className={`px-3 py-1.5 text-[10px] uppercase tracking-widest ${h.escalation === "escalated" ? "text-danger" : h.escalation === "pending" ? "text-warn" : "text-ok"}`}>
                      {h.escalation}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </section>
  );
}
