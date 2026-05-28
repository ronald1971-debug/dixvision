import { useEffect, useState } from "react";

/**
 * Tier-3 / E-track AI widget — Intent execution router.
 *
 * Surfaces an intent-based execution panel comparing solver quotes for
 * the same swap intent.  Quote data is fetched from:
 *
 *   GET /api/dashboard/dex/route?symbol=<sym>
 *
 * Response shape mirrors ``dashboard_projection_routes.RouteSnapshot``:
 *   { symbol, quotes: [{venue, in_token, out_token, in_amount,
 *     out_amount, price_impact_bps, est_fill_ms}], best_venue, ts_iso }
 *
 * Falls back to SEED_QUOTES when the backend is unavailable.
 *
 * Operator approval edge (INV-72) gates the actual sign+broadcast —
 * the "stage" button does not place a real order.
 */
interface RouterQuote {
  venue: string;
  in_token: string;
  out_token: string;
  in_amount: number;
  out_amount: number;
  price_impact_bps: number;
  est_fill_ms: number;
}

const SEED_QUOTES: RouterQuote[] = [
  {
    venue: "UniswapX",
    in_token: "ETH",
    out_token: "USDC",
    in_amount: 0.5,
    out_amount: 1_004.21,
    price_impact_bps: 1.4,
    est_fill_ms: 5_000,
  },
  {
    venue: "CowSwap",
    in_token: "ETH",
    out_token: "USDC",
    in_amount: 0.5,
    out_amount: 1_003.87,
    price_impact_bps: 1.7,
    est_fill_ms: 10_000,
  },
  {
    venue: "Across",
    in_token: "ETH",
    out_token: "USDC",
    in_amount: 0.5,
    out_amount: 1_001.40,
    price_impact_bps: 0.9,
    est_fill_ms: 3_000,
  },
];

const VENUE_NOTES: Record<string, string> = {
  UniswapX: "Dutch auction · filler-paid gas · MEV-protected",
  CowSwap: "Batch auction · CoW · CIP-38 settlement",
  Across: "Cross-chain bridge · relayer-paid · UMA dispute window",
  "Jupiter Juno": "Solana DEX aggregator · SPL-compatible",
  "1inch Fusion+": "Aggregator · gasless intent · resolver network",
};

export function IntentExecutionPanel() {
  const [tokenIn, setTokenIn] = useState("ETH");
  const [tokenOut, setTokenOut] = useState("USDC");
  const [amountIn, setAmountIn] = useState("0.5");
  const [staged, setStaged] = useState<string | null>(null);
  const [quotes, setQuotes] = useState<RouterQuote[]>(SEED_QUOTES);
  const [bestVenue, setBestVenue] = useState<string>(SEED_QUOTES[0].venue);
  const [live, setLive] = useState(false);

  useEffect(() => {
    const symbol = `${tokenIn}/${tokenOut}`;
    fetch(`/api/dashboard/dex/route?symbol=${encodeURIComponent(symbol)}`)
      .then((r) => r.json())
      .then((d) => {
        const raw: unknown[] = Array.isArray(d.quotes) ? d.quotes : [];
        if (raw.length === 0) return;
        const parsed: RouterQuote[] = raw.map((q: unknown) => {
          const row = q as Record<string, unknown>;
          return {
            venue: String(row.venue ?? ""),
            in_token: String(row.in_token ?? tokenIn),
            out_token: String(row.out_token ?? tokenOut),
            in_amount: Number(row.in_amount ?? 0),
            out_amount: Number(row.out_amount ?? 0),
            price_impact_bps: Number(row.price_impact_bps ?? 0),
            est_fill_ms: Number(row.est_fill_ms ?? 0),
          };
        });
        setQuotes(parsed);
        setBestVenue(String(d.best_venue ?? parsed[0]?.venue ?? ""));
        setLive(true);
        setStaged(null);
      })
      .catch(() => setLive(false));
  }, [tokenIn, tokenOut]);

  return (
    <section className="flex h-full flex-col rounded border border-border bg-surface">
      <header className="border-b border-border px-3 py-2 flex items-start justify-between">
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-300">
            Intent execution router
          </h3>
          <p className="mt-0.5 text-[11px] text-slate-500">
            solver quotes for one intent · operator-approval-gated
          </p>
        </div>
        <span
          className={`text-[10px] px-1.5 py-0.5 rounded ${
            live
              ? "bg-emerald-900 text-emerald-300"
              : "bg-amber-900 text-amber-300"
          }`}
        >
          {live ? "live" : "seed"}
        </span>
      </header>
      <div className="border-b border-border bg-bg/40 px-3 py-2">
        <div className="grid grid-cols-3 gap-2 font-mono text-[11px] text-slate-300">
          <label className="flex flex-col gap-0.5">
            <span className="text-[10px] uppercase tracking-wider text-slate-500">
              token in
            </span>
            <input
              value={tokenIn}
              onChange={(e) => setTokenIn(e.target.value.toUpperCase())}
              className="rounded border border-border bg-bg/60 px-2 py-1 text-slate-200 focus:border-accent focus:outline-none"
            />
          </label>
          <label className="flex flex-col gap-0.5">
            <span className="text-[10px] uppercase tracking-wider text-slate-500">
              token out
            </span>
            <input
              value={tokenOut}
              onChange={(e) => setTokenOut(e.target.value.toUpperCase())}
              className="rounded border border-border bg-bg/60 px-2 py-1 text-slate-200 focus:border-accent focus:outline-none"
            />
          </label>
          <label className="flex flex-col gap-0.5">
            <span className="text-[10px] uppercase tracking-wider text-slate-500">
              amount in
            </span>
            <input
              value={amountIn}
              onChange={(e) => setAmountIn(e.target.value)}
              className="rounded border border-border bg-bg/60 px-2 py-1 text-slate-200 focus:border-accent focus:outline-none"
            />
          </label>
        </div>
      </div>
      <ul className="flex-1 divide-y divide-border/40 overflow-auto">
        {quotes.map((q) => {
          const isBest = q.venue === bestVenue;
          const isStaged = staged === q.venue;
          const notes = VENUE_NOTES[q.venue] ?? "intent-based solver";
          return (
            <li
              key={q.venue}
              className={`grid grid-cols-[1fr_auto] gap-2 px-3 py-2 font-mono text-[11px] text-slate-300 ${
                isBest ? "bg-emerald-500/5" : ""
              }`}
            >
              <div className="min-w-0">
                <div className="flex items-baseline gap-2">
                  <span className="font-semibold text-slate-200">
                    {q.venue}
                  </span>
                  {isBest && (
                    <span className="rounded border border-emerald-500/40 px-1.5 py-0.5 text-[9px] uppercase tracking-wider text-emerald-300">
                      best
                    </span>
                  )}
                  <span className="ml-auto text-emerald-400">
                    {q.out_amount.toLocaleString(undefined, {
                      minimumFractionDigits: 2,
                      maximumFractionDigits: 2,
                    })}{" "}
                    {q.out_token}
                  </span>
                </div>
                <div className="mt-0.5 flex flex-wrap items-baseline gap-3 text-[10px] text-slate-500">
                  <span>impact {q.price_impact_bps.toFixed(1)} bps</span>
                  <span>
                    fill ~{(q.est_fill_ms / 1_000).toFixed(0)}s
                  </span>
                </div>
                <div className="mt-1 truncate text-[10px] text-slate-500">
                  {notes}
                </div>
              </div>
              <button
                type="button"
                onClick={() => setStaged(isStaged ? null : q.venue)}
                className={`self-center rounded border px-2 py-0.5 text-[10px] uppercase tracking-wider ${
                  isStaged
                    ? "border-accent/40 bg-accent/10 text-accent"
                    : "border-border bg-bg/40 text-slate-400 hover:border-accent hover:text-accent"
                }`}
              >
                {isStaged ? "staged" : "stage"}
              </button>
            </li>
          );
        })}
      </ul>
      {staged && (
        <footer className="border-t border-border bg-bg/40 px-3 py-2 font-mono text-[10px] text-slate-500">
          staged via <span className="text-slate-300">{staged}</span> ·
          awaiting approval-edge gate (INV-72)
        </footer>
      )}
    </section>
  );
}
