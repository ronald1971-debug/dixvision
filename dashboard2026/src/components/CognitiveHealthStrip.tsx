import { useQuery } from "@tanstack/react-query";

import { fetchCognitiveSnapshot } from "@/api/cognitive";

/**
 * Compact health strip that shows live orchestrator state for both
 * INDIRA and DYON.  Designed to sit at the top of each learning page
 * below the page header.
 *
 * Polls /api/cognitive/snapshot every 15 s.
 * Renders as a single row of monospace pills — no layout impact.
 */
export function CognitiveHealthStrip() {
  const { data, isError, isLoading } = useQuery({
    queryKey: ["cognitive", "snapshot"],
    queryFn: ({ signal }) => fetchCognitiveSnapshot(signal),
    refetchInterval: 15_000,
  });

  if (isLoading) {
    return (
      <div className="flex gap-2 font-mono text-[10px] text-slate-600 uppercase tracking-wider">
        <span>cognitive · loading…</span>
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="flex gap-2 font-mono text-[10px] text-rose-500 uppercase tracking-wider">
        <span>cognitive · offline</span>
      </div>
    );
  }

  const indira = data.indira;
  const evo = data.evolution;
  const dyon = evo?.dyon;
  const mem = data.memory;
  const res = data.research;

  return (
    <div
      className="flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[10px] uppercase tracking-wider"
      aria-label="cognitive health"
    >
      {/* INDIRA */}
      <Pill
        label="INDIRA"
        color="violet"
        items={[
          `t=${indira?.tick_count ?? "—"}`,
          `pos=${indira?.cycle_position ?? "—"}`,
        ]}
      />

      {/* DYON */}
      <Pill
        label="DYON"
        color="teal"
        items={[
          `ticks=${dyon?.tick_count ?? "—"}`,
          `scans=${dyon?.scan_count ?? "—"}`,
          evo?.structural_loop_wired ? "SEL✓" : "SEL—",
        ]}
      />

      {/* Memory */}
      <Pill
        label="MEM"
        color="sky"
        items={[
          `ep=${mem?.episodic_size ?? "—"}`,
          `sem=${mem?.semantic_size ?? "—"}`,
          `c=${mem?.consolidate_seq ?? "—"}`,
        ]}
      />

      {/* Research */}
      <Pill
        label="RES"
        color={res?.running ? "emerald" : "slate"}
        items={[
          res?.running ? "RUN" : "IDLE",
          `q=${res?.queue_depth ?? "—"}`,
          `ok=${res?.total_runs ?? "—"}`,
        ]}
      />
    </div>
  );
}

type PillColor = "violet" | "teal" | "sky" | "emerald" | "slate";

const COLOR: Record<PillColor, string> = {
  violet: "text-violet-400 border-violet-500/30",
  teal:   "text-teal-400 border-teal-500/30",
  sky:    "text-sky-400 border-sky-500/30",
  emerald:"text-emerald-400 border-emerald-500/30",
  slate:  "text-slate-500 border-slate-600/30",
};

function Pill({
  label,
  color,
  items,
}: {
  label: string;
  color: PillColor;
  items: string[];
}) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded border px-1.5 py-0.5 ${COLOR[color]}`}
    >
      <span className="opacity-60">{label}</span>
      {items.map((item, i) => (
        <span key={i} className="opacity-90">{item}</span>
      ))}
    </span>
  );
}
