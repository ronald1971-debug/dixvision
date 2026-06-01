import { useMutation, useQueryClient } from "@tanstack/react-query";
import { closePosition } from "@/api/signals";

interface Position {
  id: string;
  symbol: string;
  venue: string;
  side: "long" | "short";
  size: number;
  entry: number;
  mark: number;
  unrealized: number;
  realized: number;
}

const MOCK: Position[] = [
  { id: "pos-001", symbol: "BTC-PERP", venue: "hyperliquid", side: "long", size: 0.42, entry: 64210.5, mark: 65120, unrealized: 381.99, realized: 0 },
  { id: "pos-002", symbol: "SOL/USDC", venue: "binance-spot", side: "long", size: 38, entry: 142.3, mark: 145.8, unrealized: 133.0, realized: 12.5 },
  { id: "pos-003", symbol: "PEPE", venue: "raydium", side: "long", size: 1800000, entry: 0.0000091, mark: 0.0000119, unrealized: 5.04, realized: 0 },
];

export function PositionManager() {
  const qc = useQueryClient();
  const positions = MOCK;

  const closeM = useMutation({
    mutationFn: (id: string) => closePosition(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["positions"] }),
  });

  return (
    <div className="flex flex-col gap-2 rounded border border-border bg-surface p-4">
      <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-300">Position Manager</h3>
      <p className="text-[11px] text-slate-500">Close or reduce open positions. INDIRA execution.</p>
      <div className="max-h-72 overflow-auto">
        <table className="w-full text-left text-xs">
          <thead className="text-[10px] uppercase text-slate-500">
            <tr>
              <th className="px-2 py-1.5">Symbol</th>
              <th className="px-2 py-1.5">Side</th>
              <th className="px-2 py-1.5">Size</th>
              <th className="px-2 py-1.5">Entry</th>
              <th className="px-2 py-1.5">Mark</th>
              <th className="px-2 py-1.5">uPnL</th>
              <th className="px-2 py-1.5"></th>
            </tr>
          </thead>
          <tbody>
            {positions.map((p) => (
              <tr key={p.id} className="border-t border-border">
                <td className="px-2 py-1.5 font-mono text-slate-200">{p.symbol}</td>
                <td className={`px-2 py-1.5 ${p.side === "long" ? "text-ok" : "text-danger"}`}>{p.side.toUpperCase()}</td>
                <td className="px-2 py-1.5 font-mono text-slate-300">{p.size}</td>
                <td className="px-2 py-1.5 font-mono text-slate-400">{p.entry.toLocaleString()}</td>
                <td className="px-2 py-1.5 font-mono text-slate-400">{p.mark.toLocaleString()}</td>
                <td className={`px-2 py-1.5 font-mono ${p.unrealized >= 0 ? "text-ok" : "text-danger"}`}>
                  {p.unrealized >= 0 ? "+" : ""}{p.unrealized.toFixed(2)}
                </td>
                <td className="px-2 py-1.5">
                  <button
                    onClick={() => closeM.mutate(p.id)}
                    disabled={closeM.isPending}
                    className="rounded border border-danger/40 bg-danger/10 px-2 py-1 text-[10px] uppercase tracking-widest text-danger hover:bg-danger/20 disabled:opacity-50"
                  >
                    Close
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
