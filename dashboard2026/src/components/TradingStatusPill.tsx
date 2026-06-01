import { useQuery } from "@tanstack/react-query";

import { fetchMode } from "@/api/dashboard";

export function TradingStatusPill() {
  const q = useQuery({
    queryKey: ["trading-status"],
    queryFn: ({ signal }) => fetchMode(signal),
    refetchInterval: 10_000,
  });

  const allowed = q.data?.legal_targets && q.data.legal_targets.length > 0;

  return (
    <span className={`flex items-center gap-1.5 rounded border px-2.5 py-1 font-mono text-[11px] uppercase tracking-wider ${allowed ? "border-ok/40 bg-ok/10 text-ok" : "border-danger/40 bg-danger/10 text-danger"}`}>
      TRADING: {allowed ? "✓" : "✗"}
    </span>
  );
}
