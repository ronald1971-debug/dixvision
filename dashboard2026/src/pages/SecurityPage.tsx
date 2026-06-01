import { useQuery, useMutation } from "@tanstack/react-query";
import { fetchModeTimeline, fetchSecurityEvents, triggerKillSwitch } from "@/api/signals";

export function SecurityPage() {
  const modeQ = useQuery({
    queryKey: ["mode-timeline"],
    queryFn: ({ signal }) => fetchModeTimeline(signal),
    refetchInterval: 10000,
  });

  const secQ = useQuery({
    queryKey: ["security-events"],
    queryFn: ({ signal }) => fetchSecurityEvents(signal),
    refetchInterval: 10000,
  });

  const ksQ = useMutation({
    mutationFn: () => triggerKillSwitch(""),
  });

  const totalViolations = secQ.data?.total ?? 0;
  const violations = secQ.data?.violations ?? [];

  const modeColors: Record<string, string> = {
    NORMAL: "text-ok border-ok/30 bg-ok/10",
    SAFE: "text-blue-400 border-blue-400/30 bg-blue-400/10",
    DEGRADED: "text-warn border-warn/30 bg-warn/10",
    HALTED: "text-danger border-danger/30 bg-danger/10",
  };

  return (
    <section className="flex h-full flex-col">
      <header className="mb-4">
        <h1 className="text-lg font-semibold tracking-tight">
          GOVERNANCE Security & Authority
          <span className="ml-2 rounded border border-border bg-bg px-2 py-0.5 font-mono text-[11px] uppercase tracking-widest text-slate-400">LIVE</span>
        </h1>
        <p className="mt-1 text-xs text-slate-400">
          Kill-switch state, authority violations, and mode transitions
        </p>
      </header>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="flex flex-col gap-3">
          <div className="rounded border border-border bg-surface p-4">
            <h3 className="mb-2 text-sm font-semibold uppercase tracking-wider text-slate-300">
              Kill Switch
            </h3>
            <div className="flex flex-col gap-2">
              <div className="flex items-baseline gap-2">
                <span className="rounded border border-ok/30 bg-ok/10 px-2 py-1 font-mono text-xs text-ok">
                  ARMED
                </span>
                <span className="text-[10px] text-slate-500">CONTROL-domain action available</span>
              </div>
              <button
                onClick={() => ksQ.mutate()}
                disabled={ksQ.isPending}
                className="self-start rounded border border-danger/40 bg-danger/10 px-3 py-1.5 text-xs text-danger hover:bg-danger/20 disabled:opacity-50"
              >
                {ksQ.isPending ? "Arming…" : "Arm Kill Switch"}
              </button>
            </div>
          </div>

          <div className="rounded border border-border bg-surface p-4">
            <h3 className="mb-2 text-sm font-semibold uppercase tracking-wider text-slate-300">
              EXECUTION_CONSTRAINT_SET
            </h3>
            <div className="flex flex-col gap-1 text-xs">
              {[
                ["max_drawdown", "4% (hard stop)"],
                ["max_loss_per_trade", "5%"],
                ["fail_closed", "true"],
                ["trading_allowed", "true"],
              ].map(([k, v]) => (
                <div key={k} className="flex items-baseline justify-between">
                  <span className="text-slate-400">{k}</span>
                  <span className="font-mono text-slate-200">{v}</span>
                </div>
              ))}
              <span className="mt-1 text-[10px] text-slate-500">
                last_updated: 2026-05-31T14:30:00Z
              </span>
            </div>
          </div>
        </div>

        <div className="flex flex-col gap-3">
          <div className="rounded border border-border bg-surface p-4">
            <h3 className="mb-2 text-sm font-semibold uppercase tracking-wider text-slate-300">
              Authority Violations
            </h3>
            <div className="mb-2 text-xs text-slate-400">
              Total: {totalViolations} (last 24h)
            </div>
            <div className="flex max-h-48 flex-col gap-1 overflow-auto">
              {violations.length === 0 && (
                <p className="text-xs text-slate-500">No violations in current window.</p>
              )}
              {violations.map((v: { id: string; ts_utc: string; kind: string; subject: string; state: string }) => (
                <div
                  key={v.id}
                  className="flex items-center gap-2 rounded border border-border bg-bg/60 px-3 py-1"
                >
                  <span className="text-xs text-slate-300">{v.ts_utc?.split("T")[1]?.split("Z")[0]}</span>
                  <span className="text-[10px] text-slate-500">{v.kind}</span>
                  <span className="ml-auto text-[10px] uppercase tracking-widest text-warn">
                    {v.state}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="mt-4 rounded border border-border bg-surface p-4">
        <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider text-slate-300">
          Mode Transition Timeline
        </h3>
        <div className="flex flex-col gap-2">
          {(modeQ.data?.timeline ?? []).map((t: { ts_utc: string; from_mode: string; to_mode: string; reason: string }) => (
            <div
              key={t.ts_utc + t.to_mode}
              className={`flex items-center gap-3 rounded border px-3 py-2 text-xs ${modeColors[t.to_mode] || "border-border text-slate-300"}`}
            >
              <span className="font-mono text-slate-400">{t.ts_utc?.split("T")[0] ?? t.ts_utc}</span>
              <span className="font-semibold">{t.from_mode} → {t.to_mode}</span>
              <span className="text-slate-400">{t.reason}</span>
            </div>
          ))}
          {(!modeQ.data?.timeline || modeQ.data.timeline.length === 0) && (
            <p className="text-xs text-slate-500">No mode transitions recorded.</p>
          )}
        </div>
      </div>
    </section>
  );
}
