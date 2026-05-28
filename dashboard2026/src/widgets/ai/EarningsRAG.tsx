import { useEffect, useMemo, useState } from "react";

/**
 * Tier-3 AI widget — Earnings-call RAG.
 *
 * Pick a recent earnings transcript, ask a question, get an answer
 * with cited paragraphs. Local TF-style retrieval is the offline
 * fallback; production retrieval delegates to the cognitive chat
 * adapter via GET /api/research/earnings_rag?symbol=&q=.
 *
 * Backend: GET /api/research/earnings_rag — returns transcript catalog
 * on bare call; returns {answer, citations} with ?symbol=&q= params.
 */
interface Transcript {
  id: string;
  ticker: string;
  quarter: string;
  bullishness: number;
  paragraphs: { id: string; section: string; text: string }[];
}

const TRANSCRIPTS: Transcript[] = [
  {
    id: "AAPL-2025Q3",
    ticker: "AAPL",
    quarter: "2025 Q3",
    bullishness: 0.42,
    paragraphs: [
      {
        id: "p1",
        section: "Guidance",
        text: "We expect services revenue growth to accelerate into the December quarter driven by App Store, advertising, and Apple Music.",
      },
      {
        id: "p2",
        section: "Margins",
        text: "Gross margin guidance for the December quarter is 46.0–47.0%, reflecting a richer mix and continued cost leverage.",
      },
      {
        id: "p3",
        section: "China",
        text: "iPhone revenue in Greater China declined modestly; we are encouraged by trade-in dynamics and expect sequential improvement.",
      },
    ],
  },
  {
    id: "NVDA-2025Q2",
    ticker: "NVDA",
    quarter: "2025 Q2",
    bullishness: 0.78,
    paragraphs: [
      {
        id: "p1",
        section: "Data Center",
        text: "Data center revenue grew 154% year over year on broad-based demand for Hopper and ramping Blackwell shipments.",
      },
      {
        id: "p2",
        section: "Supply",
        text: "Blackwell production yields are improving; we expect supply to better meet demand entering the second half.",
      },
      {
        id: "p3",
        section: "Sovereign AI",
        text: "Sovereign AI deployments are now in 12 countries and represent a multi-billion-dollar opportunity over the next year.",
      },
    ],
  },
  {
    id: "TSLA-2025Q3",
    ticker: "TSLA",
    quarter: "2025 Q3",
    bullishness: -0.18,
    paragraphs: [
      {
        id: "p1",
        section: "Deliveries",
        text: "Auto deliveries were 462,890 in Q3, up modestly year over year but below internal targets due to model-mix friction.",
      },
      {
        id: "p2",
        section: "Robotaxi",
        text: "Cybercab production targeting end of 2026; pilot fleet expansion in Austin and Phoenix is on track.",
      },
      {
        id: "p3",
        section: "Energy",
        text: "Energy storage deployments hit 9.6 GWh, a record, with Megapack backlog extending into 2027.",
      },
    ],
  },
];

function scoreLocal(text: string, q: string): number {
  if (!q.trim()) return 0;
  const tokens = q
    .toLowerCase()
    .replace(/[^a-z0-9 ]/g, " ")
    .split(/\s+/)
    .filter((t) => t.length > 2);
  if (tokens.length === 0) return 0;
  const lc = text.toLowerCase();
  let hits = 0;
  for (const t of tokens) {
    if (lc.includes(t)) hits += 1;
  }
  return hits / tokens.length;
}

export function EarningsRAG() {
  const [selected, setSelected] = useState(TRANSCRIPTS[0].id);
  const [q, setQ] = useState("");
  const [live, setLive] = useState(false);
  const [liveAnswer, setLiveAnswer] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // Fetch backend answer whenever the user's query changes (debounced 600ms).
  useEffect(() => {
    if (!q.trim()) {
      setLiveAnswer(null);
      return;
    }
    const ticker = TRANSCRIPTS.find((t) => t.id === selected)?.ticker ?? selected;
    const timer = setTimeout(() => {
      setLoading(true);
      fetch(
        `/api/research/earnings_rag?symbol=${encodeURIComponent(ticker)}&q=${encodeURIComponent(q)}`,
      )
        .then((r) => r.json())
        .then((d) => {
          if (d.answer && String(d.answer).trim()) {
            setLiveAnswer(String(d.answer));
            setLive(true);
          }
        })
        .catch(() => setLive(false))
        .finally(() => setLoading(false));
    }, 600);
    return () => clearTimeout(timer);
  }, [q, selected]);

  const transcript = useMemo(
    () => TRANSCRIPTS.find((t) => t.id === selected) ?? TRANSCRIPTS[0],
    [selected],
  );

  const localRanked = useMemo(() => {
    if (!q.trim()) return [];
    return transcript.paragraphs
      .map((p) => ({ p, s: scoreLocal(p.text, q) }))
      .filter((r) => r.s > 0)
      .sort((a, b) => b.s - a.s)
      .slice(0, 3);
  }, [q, transcript]);

  const bullish = transcript.bullishness;

  return (
    <section className="flex h-full flex-col rounded border border-border bg-surface">
      <header className="flex items-baseline justify-between border-b border-border px-3 py-2">
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-300">
            Earnings RAG
          </h3>
          <p className="mt-0.5 text-[11px] text-slate-500">
            ask · cited paragraphs · adversarial bullishness
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={`text-[10px] px-1.5 py-0.5 rounded ${
              live
                ? "bg-emerald-900 text-emerald-300"
                : "bg-amber-900 text-amber-300"
            }`}
          >
            {live ? "live" : "mock"}
          </span>
          <span
            className={`rounded border px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider ${
              bullish > 0.2
                ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
                : bullish < -0.2
                  ? "border-rose-500/40 bg-rose-500/10 text-rose-300"
                  : "border-slate-500/40 bg-slate-500/10 text-slate-300"
            }`}
          >
            bullishness {bullish.toFixed(2)}
          </span>
        </div>
      </header>
      <div className="flex flex-1 flex-col gap-2 overflow-auto p-3 text-[12px]">
        <label className="flex items-baseline gap-2 font-mono text-[10px] uppercase tracking-wider text-slate-400">
          transcript
          <select
            value={selected}
            onChange={(e) => { setSelected(e.target.value); setLiveAnswer(null); }}
            className="flex-1 rounded border border-border bg-bg/40 px-2 py-1 text-[11px] text-slate-200 focus:border-accent focus:outline-none"
          >
            {TRANSCRIPTS.map((t) => (
              <option key={t.id} value={t.id}>
                {t.ticker} · {t.quarter}
              </option>
            ))}
          </select>
        </label>
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="ask about guidance, margins, growth …"
          className="rounded border border-border bg-bg/40 px-2 py-1 font-mono text-[11px] text-slate-200 focus:border-accent focus:outline-none"
        />
        <div>
          <h4 className="mb-1 font-mono text-[10px] uppercase tracking-wider text-slate-500">
            {live && liveAnswer ? "cognitive answer" : "top citations"}
          </h4>
          {q.trim().length === 0 ? (
            <p className="text-[11px] text-slate-500">
              type a question to retrieve cited paragraphs
            </p>
          ) : loading ? (
            <p className="text-[11px] text-slate-500">querying backend…</p>
          ) : live && liveAnswer ? (
            <div className="rounded border border-emerald-800/40 bg-emerald-900/10 p-2 text-[11px] text-slate-300">
              <p>{liveAnswer}</p>
              <p className="mt-1 text-[10px] text-emerald-600">
                source: cognitive_chat
              </p>
            </div>
          ) : localRanked.length === 0 ? (
            <p className="text-[11px] text-slate-500">no matches</p>
          ) : (
            <ul className="space-y-1.5">
              {localRanked.map(({ p, s }) => (
                <li
                  key={p.id}
                  className="rounded border border-border bg-bg/40 p-2 text-[11px] text-slate-300"
                >
                  <div className="flex items-baseline justify-between font-mono text-[10px] uppercase tracking-wider text-slate-500">
                    <span>{p.section}</span>
                    <span>match {(s * 100).toFixed(0)}%</span>
                  </div>
                  <p className="mt-1">{p.text}</p>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </section>
  );
}
