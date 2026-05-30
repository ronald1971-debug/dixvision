import { useCallback, useEffect, useRef, useState } from "react";

import { Activity } from "lucide-react";

import {
  activateMacroScenario,
  fetchSimulationSnapshot,
  type AgentRecord,
  type CrowdSnapshotResponse,
  type ExchangeSnapshotResponse,
  type LatencySnapshotResponse,
  type LiquiditySnapshotResponse,
  type MacroSnapshotResponse,
  type MarketSnapshotResponse,
  type ReflexiveSnapshotResponse,
  type SimulationSnapshotResponse,
  type TierSnapshot,
  type VenueState,
  type VolatilitySnapshotResponse,
} from "@/api/simulation";

// ─── Helpers ──────────────────────────────────────────────────────────────────

function Bar({
  pct,
  color = "bg-sky-500",
  h = "h-1.5",
}: {
  pct: number;
  color?: string;
  h?: string;
}) {
  return (
    <div className={`w-full rounded-full bg-slate-700/60 ${h}`}>
      <div
        className={`${h} rounded-full ${color}`}
        style={{ width: `${Math.max(2, Math.min(100, pct))}%` }}
      />
    </div>
  );
}

function Kv({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 py-0.5 text-xs">
      <span className="text-slate-400">{label}</span>
      <span className="font-mono text-slate-100">{value}</span>
    </div>
  );
}

function Card({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border border-slate-700/60 bg-slate-800/60 p-3">
      <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-400">
        {title}
      </div>
      {children}
    </div>
  );
}

function regimeColor(r: string) {
  if (r === "EXTREME" || r === "EXTREME_VOL") return "text-red-400";
  if (r === "ELEVATED" || r === "HIGH_VOL") return "text-amber-400";
  if (r === "NORMAL") return "text-sky-400";
  return "text-emerald-400";
}

function stateColor(s: string) {
  if (s === "EUPHORIA" || s === "OVERCONFIDENT" || s === "BULLISH") return "text-emerald-400";
  if (s === "BEARISH") return "text-amber-400";
  if (s === "PANIC" || s === "CAPITULATION") return "text-red-400";
  return "text-slate-300";
}

function venueStateColor(s: string) {
  if (s === "FULL_OUTAGE") return "text-red-400";
  if (s === "PARTIAL_OUTAGE") return "text-orange-400";
  if (s === "CIRCUIT_BREAKER") return "text-amber-400";
  if (s === "DEGRADED") return "text-yellow-400";
  return "text-emerald-400";
}

// ─── Tab definitions ──────────────────────────────────────────────────────────

type Tab =
  | "market"
  | "arena"
  | "crowd"
  | "reflexive"
  | "volatility"
  | "liquidity"
  | "macro"
  | "exchange"
  | "latency";

const TABS: { key: Tab; label: string }[] = [
  { key: "market",     label: "Market" },
  { key: "arena",      label: "Arena" },
  { key: "crowd",      label: "Crowd" },
  { key: "reflexive",  label: "Reflexive" },
  { key: "volatility", label: "Volatility" },
  { key: "liquidity",  label: "Liquidity" },
  { key: "macro",      label: "Macro" },
  { key: "exchange",   label: "Exchange" },
  { key: "latency",    label: "Latency" },
];

// ─── Tab panels ───────────────────────────────────────────────────────────────

function MarketPanel({ data }: { data: MarketSnapshotResponse }) {
  const bars = data.recent_bars ?? [];
  const last = bars[bars.length - 1];
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      <Card title="Price">
        <Kv label="Close" value={last ? last.close.toFixed(4) : "—"} />
        <Kv label="Regime" value={<span className={regimeColor(data.regime)}>{data.regime}</span>} />
        <Kv label="Vol" value={(data.vol * 100).toFixed(3) + "%"} />
        <Kv label="Vol ratio" value={data.vol_ratio?.toFixed(3)} />
        <Kv label="Log return" value={(data.last_log_return * 100).toFixed(4) + "%"} />
        <Kv label="Realised vol" value={(data.realised_vol * 100).toFixed(3) + "%"} />
        <Kv label="Jump count" value={data.jump_count} />
        <Kv label="Heston var" value={data.heston_var?.toFixed(6)} />
        <Kv label="Ticks" value={data.tick_count} />
      </Card>
      <Card title="Recent bars (OHLCV)">
        <div className="max-h-48 overflow-y-auto space-y-0.5">
          {bars.slice(-12).map((b, i) => (
            <div key={i} className="grid grid-cols-4 gap-1 font-mono text-[10px] text-slate-300">
              <span>{b.open.toFixed(3)}</span>
              <span className="text-emerald-400">{b.high.toFixed(3)}</span>
              <span className="text-red-400">{b.low.toFixed(3)}</span>
              <span>{b.close.toFixed(3)}</span>
            </div>
          ))}
        </div>
      </Card>
      <Card title="Order book">
        {(data.recent_books ?? []).slice(-6).map((bk, i) => (
          <div key={i} className="grid grid-cols-3 gap-1 font-mono text-[10px] text-slate-300">
            <span className="text-emerald-400">{bk.bid?.toFixed(4)}</span>
            <span className="text-red-400">{bk.ask?.toFixed(4)}</span>
            <span className="text-slate-400">{(bk.spread * 10000)?.toFixed(1)}bp</span>
          </div>
        ))}
      </Card>
    </div>
  );
}

function ArenaPanel({ data }: { data: { agents: AgentRecord[]; target_survival_rate: number; total_actions: number; tick_count: number } }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <Card title="Arena stats">
        <Kv label="Target survival" value={(data.target_survival_rate * 100).toFixed(1) + "%"} />
        <Kv label="Total actions" value={data.total_actions} />
        <Kv label="Ticks" value={data.tick_count} />
      </Card>
      <Card title="Agents">
        <div className="space-y-2">
          {(data.agents ?? []).map((a) => (
            <div key={a.agent_type}>
              <div className="flex items-center justify-between text-xs">
                <span className="font-medium text-slate-200">{a.agent_type}</span>
                <span className="font-mono text-slate-400">
                  {(a.win_rate * 100).toFixed(0)}% wr · {a.total_edge_bps.toFixed(1)}bp
                </span>
              </div>
              <Bar pct={a.win_rate * 100} color="bg-violet-500" />
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

function CrowdPanel({ data }: { data: CrowdSnapshotResponse }) {
  const allStates: string[] = data.all_states ?? [
    "CAPITULATION","PANIC","BEARISH","NEUTRAL","BULLISH","OVERCONFIDENT","EUPHORIA",
  ];
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      <Card title="Sentiment">
        <Kv label="State" value={<span className={stateColor(data.state)}>{data.state}</span>} />
        <Kv label="Fear/Greed" value={data.fear_greed?.toFixed(1)} />
        <Kv label="Herding" value={(data.herding_coeff * 100).toFixed(1) + "%"} />
        <Kv label="Transitions" value={data.transitions} />
        <Kv label="Herding surges" value={data.herding_surges} />
        <Kv label="Contrarian signals" value={data.contrarian_signals} />
        <Kv label="Ticks" value={data.tick_count} />
      </Card>
      <Card title="State ladder">
        {allStates.map((s, i) => (
          <div key={s} className="flex items-center gap-2 py-0.5 text-xs">
            <span
              className={`h-2 w-2 rounded-full ${data.state_idx === i ? "bg-violet-400" : "bg-slate-600"}`}
            />
            <span className={data.state_idx === i ? stateColor(s) : "text-slate-500"}>{s}</span>
          </div>
        ))}
      </Card>
      <Card title="Fear/Greed history">
        <div className="flex h-20 items-end gap-px">
          {(data.fear_greed_history ?? []).slice(-40).map((v, i) => (
            <div
              key={i}
              className="flex-1 rounded-sm"
              style={{
                height: `${Math.max(2, v)}%`,
                background: v > 60 ? "#34d399" : v < 40 ? "#f87171" : "#94a3b8",
              }}
            />
          ))}
        </div>
      </Card>
    </div>
  );
}

function ReflexivePanel({ data }: { data: ReflexiveSnapshotResponse }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      <Card title="Reflexivity">
        <Kv label="State" value={<span className={data.state === "CASCADE" ? "text-red-400" : data.state === "CORRECTION" ? "text-amber-400" : "text-emerald-400"}>{data.state}</span>} />
        <Kv label="Rho (ρ)" value={data.rho?.toFixed(4)} />
        <Kv label="Sentiment" value={data.sentiment?.toFixed(4)} />
        <Kv label="Momentum" value={data.momentum?.toFixed(6)} />
        <Kv label="Cascades" value={data.cascade_count} />
        <Kv label="Corrections" value={data.correction_count} />
        <Kv label="Ticks" value={data.tick_count} />
      </Card>
      <Card title="Rho history">
        <div className="flex h-20 items-end gap-px">
          {(data.rho_history ?? []).slice(-40).map((v, i) => (
            <div
              key={i}
              className="flex-1 rounded-sm bg-violet-500"
              style={{ height: `${Math.max(2, v * 100)}%` }}
            />
          ))}
        </div>
      </Card>
      <Card title="Sentiment history">
        <div className="flex h-20 items-end gap-px">
          {(data.sentiment_history ?? []).slice(-40).map((v, i) => (
            <div
              key={i}
              className="flex-1 rounded-sm"
              style={{
                height: `${Math.max(2, Math.abs(v) * 50)}%`,
                background: v >= 0 ? "#34d399" : "#f87171",
              }}
            />
          ))}
        </div>
      </Card>
    </div>
  );
}

function VolatilityPanel({ data }: { data: VolatilitySnapshotResponse }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      <Card title="Regime">
        <Kv label="Regime" value={<span className={regimeColor(data.regime)}>{data.regime}</span>} />
        <Kv label="Current vol" value={(data.current_vol * 100).toFixed(4) + "%"} />
        <Kv label="Baseline vol" value={(data.baseline_vol * 100).toFixed(4) + "%"} />
        <Kv label="Vol ratio" value={data.vol_ratio?.toFixed(3)} />
        <Kv label="Vol-of-vol" value={(data.vol_of_vol * 100).toFixed(4) + "%"} />
        <Kv label="Gamma exposure" value={data.gamma_exposure?.toFixed(4)} />
        <Kv label="Contagion pool" value={(data.contagion_pool * 100).toFixed(1) + "%"} />
        <Kv label="Cascades" value={data.cascade_count} />
        <Kv label="Squeezes" value={data.squeeze_count} />
        <Kv label="Contagion events" value={data.contagion_count} />
      </Card>
      <Card title="Vol history">
        <div className="flex h-20 items-end gap-px">
          {(data.vol_history ?? []).slice(-40).map((v, i) => (
            <div
              key={i}
              className="flex-1 rounded-sm bg-amber-500"
              style={{ height: `${Math.max(2, v * 2000)}%` }}
            />
          ))}
        </div>
      </Card>
      <Card title="Contagion">
        <Bar pct={data.contagion_pool * 100} color="bg-red-500" h="h-2" />
        <p className="mt-1 text-[10px] text-slate-500">Pool level — spills to correlated assets at &gt;30%</p>
        <div className="mt-3">
          <Kv label="Gamma exposure" value={data.gamma_exposure?.toFixed(4)} />
          <Bar pct={(data.gamma_exposure / 3) * 100} color="bg-violet-500" h="h-2" />
        </div>
      </Card>
    </div>
  );
}

function LiquidityPanel({ data }: { data: LiquiditySnapshotResponse }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      <Card title="Depth">
        <Kv label="Depth index" value={data.depth_index?.toFixed(2)} />
        <Bar pct={data.depth_index} color={data.depth_index > 60 ? "bg-emerald-500" : data.depth_index > 30 ? "bg-amber-500" : "bg-red-500"} h="h-2" />
        <div className="mt-2">
          <Kv label="Spread" value={data.spread_bps?.toFixed(3) + " bps"} />
          <Kv label="Impact 1M" value={data.impact_1m_bps?.toFixed(4) + " bps"} />
          <Kv label="Impact 10M" value={data.impact_10m_bps?.toFixed(4) + " bps"} />
        </div>
      </Card>
      <Card title="Attack counts">
        <Kv label="Spoofs" value={data.spoof_count} />
        <Kv label="Layers" value={data.layer_count} />
        <Kv label="Icebergs detected" value={data.iceberg_count} />
        <Kv label="Depth erosions" value={data.erosion_count} />
        <Kv label="Ticks" value={data.tick_count} />
      </Card>
      <Card title="Recent events">
        <div className="max-h-40 space-y-0.5 overflow-y-auto">
          {(data.recent_events ?? []).slice(-10).map((e, i) => (
            <div key={i} className="flex items-center gap-2 text-[10px]">
              <span className={`rounded px-1 font-mono ${e.kind === "SPOOF" ? "bg-red-900/40 text-red-300" : e.kind === "LAYER" ? "bg-orange-900/40 text-orange-300" : "bg-slate-700/60 text-slate-400"}`}>
                {e.kind as string}
              </span>
              <span className="text-slate-400">sev={(e.severity as number)?.toFixed(2)}</span>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

const MACRO_SCENARIOS = [
  "RATE_SHOCK","BANKING_CRISIS","GEOPOLITICAL_SHOCK","DEFLATIONARY_SPIRAL",
  "HYPERINFLATION","STAGFLATION","LIQUIDITY_CRISIS","TECH_SECTOR_ROUT","CRYPTO_WINTER",
];

function MacroPanel({ data, onActivate }: { data: MacroSnapshotResponse; onActivate: (s: string) => void }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      <Card title="Stress index">
        <div className="mb-1 text-2xl font-bold tabular-nums text-amber-400">
          {data.stress_index?.toFixed(1)}
          <span className="ml-1 text-xs font-normal text-slate-400">/ 100</span>
        </div>
        <Bar pct={data.stress_index} color={data.stress_index > 60 ? "bg-red-500" : data.stress_index > 30 ? "bg-amber-500" : "bg-emerald-500"} h="h-3" />
        <div className="mt-2 space-y-0.5">
          <Kv label="Active scenarios" value={data.active_count} />
          <Kv label="Composite vol mult" value={data.composite_vol_mult?.toFixed(3) + "×"} />
          <Kv label="Price impact" value={(data.composite_price_impact * 100)?.toFixed(2) + "%"} />
        </div>
      </Card>
      <Card title="Active scenarios">
        {data.active_count === 0 ? (
          <p className="text-xs text-slate-500">No active scenarios</p>
        ) : (
          <div className="space-y-1.5">
            {(data.active_scenarios ?? []).map((s) => (
              <div key={s.name}>
                <div className="flex items-center justify-between text-xs">
                  <span className="text-amber-300">{s.name}</span>
                  <span className="font-mono text-slate-400">{(s.intensity * 100).toFixed(0)}% · {s.duration_bars}b</span>
                </div>
                <Bar pct={s.intensity * 100} color="bg-amber-500" />
              </div>
            ))}
          </div>
        )}
      </Card>
      <Card title="Inject scenario">
        <div className="flex flex-col gap-1">
          {MACRO_SCENARIOS.map((s) => {
            const isActive = (data.active_scenarios ?? []).some((a) => a.name === s);
            return (
              <button
                key={s}
                disabled={isActive}
                onClick={() => onActivate(s)}
                className={`rounded px-2 py-0.5 text-left text-[10px] transition ${isActive ? "cursor-default bg-amber-900/30 text-amber-400" : "bg-slate-700/60 text-slate-300 hover:bg-slate-600/60"}`}
              >
                {s}
              </button>
            );
          })}
        </div>
      </Card>
    </div>
  );
}

function ExchangePanel({ data }: { data: ExchangeSnapshotResponse }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      <Card title="Fill rate">
        <div className="mb-1 text-2xl font-bold tabular-nums text-sky-400">
          {(data.aggregate_fill_rate * 100).toFixed(1)}
          <span className="ml-1 text-xs font-normal text-slate-400">%</span>
        </div>
        <Bar pct={data.aggregate_fill_rate * 100} color={data.aggregate_fill_rate > 0.8 ? "bg-emerald-500" : data.aggregate_fill_rate > 0.5 ? "bg-amber-500" : "bg-red-500"} h="h-3" />
        <div className="mt-2 space-y-0.5">
          <Kv label="Best venue" value={data.best_venue} />
          <Kv label="Venues failing" value={`${data.venues_failing} / 5`} />
          <Kv label="Failures" value={data.failure_count} />
          <Kv label="Recoveries" value={data.recovery_count} />
        </div>
      </Card>
      <Card title="Venues">
        <div className="space-y-1.5">
          {(data.venues ?? []).map((v: VenueState) => (
            <div key={v.venue}>
              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-200">{v.venue}</span>
                <span className={venueStateColor(v.state)}>{v.state}</span>
              </div>
              <Bar pct={v.fill_rate * 100} color={v.fill_rate > 0.8 ? "bg-emerald-500" : v.fill_rate > 0.4 ? "bg-amber-500" : "bg-red-500"} />
            </div>
          ))}
        </div>
      </Card>
      <Card title="Recent events">
        <div className="max-h-40 space-y-0.5 overflow-y-auto">
          {(data.recent_events ?? []).slice(-10).map((e, i) => (
            <div key={i} className="flex items-center justify-between gap-2 text-[10px]">
              <span className="text-slate-400">{e.venue as string}</span>
              <span className={`rounded px-1 font-mono ${e.kind === "RECOVERED" ? "bg-emerald-900/40 text-emerald-300" : "bg-red-900/40 text-red-300"}`}>
                {e.kind as string}
              </span>
              <span className="text-slate-500">{e.state as string}</span>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

function LatencyPanel({ data }: { data: LatencySnapshotResponse }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      <Card title="Latency index">
        <div className="mb-1 text-2xl font-bold tabular-nums text-violet-400">
          {data.latency_index?.toFixed(1)}
          <span className="ml-1 text-xs font-normal text-slate-400">/ 100</span>
        </div>
        <Bar pct={data.latency_index} color="bg-violet-500" h="h-3" />
        <div className="mt-2 space-y-0.5">
          <Kv label="Adverse fills" value={data.adverse_fills} />
          <Kv label="Queue jumps" value={data.queue_jumps} />
          <Kv label="Spikes" value={data.spike_count} />
          <Kv label="Ticks" value={data.tick_count} />
        </div>
      </Card>
      <Card title="Tiers">
        <div className="space-y-2">
          {(data.tiers ?? []).map((t: TierSnapshot) => (
            <div key={t.tier}>
              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-200">{t.tier}</span>
                <span className="font-mono text-slate-400">
                  {t.latency_us >= 1000 ? (t.latency_us / 1000).toFixed(1) + "ms" : t.latency_us.toFixed(0) + "µs"}
                </span>
              </div>
              <div className="grid grid-cols-2 gap-1">
                <div>
                  <div className="text-[9px] text-slate-500">Fill prob</div>
                  <Bar pct={t.fill_prob * 100} color="bg-sky-500" />
                </div>
                <div>
                  <div className="text-[9px] text-slate-500">Adverse sel</div>
                  <Bar pct={t.adverse_sel * 100} color="bg-red-500" />
                </div>
              </div>
            </div>
          ))}
        </div>
      </Card>
      <Card title="Latency history">
        <div className="flex h-20 items-end gap-px">
          {(data.latency_history ?? []).slice(-40).map((v, i) => (
            <div
              key={i}
              className="flex-1 rounded-sm bg-violet-500"
              style={{ height: `${Math.max(2, v)}%` }}
            />
          ))}
        </div>
      </Card>
    </div>
  );
}

// ─── Seed / empty data ────────────────────────────────────────────────────────

function emptySeed(): SimulationSnapshotResponse {
  return {
    orchestrator: { tick_count: 0, engines: 9, running: false },
    synthetic_market: { regime: "NORMAL", price: 100, vol: 0.02, baseline_vol: 0.02, vol_ratio: 1, jump_count: 0, heston_var: 0.0004, tick_count: 0, last_log_return: 0, realised_vol: 0.02, recent_bars: [], recent_books: [] },
    adversarial_arena: { tick_count: 0, target_survival_rate: 1, total_actions: 0, agents: [], recent_actions: [] },
    reflexive: { state: "EQUILIBRIUM", rho: 0.1, sentiment: 0, momentum: 0, cascade_count: 0, correction_count: 0, tick_count: 0, rho_history: [], sentiment_history: [], recent_events: [] },
    liquidity_warfare: { depth_index: 75, spread_bps: 2, spoof_count: 0, layer_count: 0, iceberg_count: 0, erosion_count: 0, tick_count: 0, impact_1m_bps: 0, impact_10m_bps: 0, recent_events: [] },
    crowd_psychology: { state: "NEUTRAL", state_idx: 3, fear_greed: 50, herding_coeff: 0.25, contrarian_signals: 0, herding_surges: 0, transitions: 0, tick_count: 0, fear_greed_history: [], herding_history: [], recent_events: [], all_states: ["CAPITULATION","PANIC","BEARISH","NEUTRAL","BULLISH","OVERCONFIDENT","EUPHORIA"] },
    volatility_cascade: { regime: "NORMAL", current_vol: 0.02, baseline_vol: 0.02, vol_ratio: 1, vol_of_vol: 0, gamma_exposure: 1, contagion_pool: 0, cascade_count: 0, squeeze_count: 0, contagion_count: 0, tick_count: 0, vol_history: [], recent_events: [] },
    macro_stress: { stress_index: 0, active_count: 0, activation_count: 0, tick_count: 0, composite_vol_mult: 1, composite_price_impact: 0, active_scenarios: [], inactive_scenarios: [], stress_history: [], recent_events: [] },
    exchange_failure: { tick_count: 0, failure_count: 0, recovery_count: 0, venues_failing: 0, aggregate_fill_rate: 1, best_venue: "VENUE_A", venues: [], recent_events: [] },
    latency_warfare: { latency_index: 75, adverse_fills: 0, queue_jumps: 0, spike_count: 0, tick_count: 0, tiers: [], latency_history: [], recent_events: [] },
  };
}

// ─── Page root ────────────────────────────────────────────────────────────────

export function SimulationPage() {
  const [tab, setTab] = useState<Tab>("market");
  const [data, setData] = useState<SimulationSnapshotResponse>(emptySeed());
  const [live, setLive] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const load = useCallback(async () => {
    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;
    try {
      const snap = await fetchSimulationSnapshot(ac.signal);
      setData(snap);
      setLive(true);
      setErr(null);
    } catch (e) {
      if ((e as Error).name !== "AbortError") {
        setLive(false);
        setErr((e as Error).message);
      }
    }
  }, []);

  useEffect(() => {
    void load();
    const id = setInterval(() => void load(), 8_000);
    return () => {
      clearInterval(id);
      abortRef.current?.abort();
    };
  }, [load]);

  const handleActivate = async (scenario: string) => {
    try {
      await activateMacroScenario(scenario);
      void load();
    } catch {
      // best-effort
    }
  };

  return (
    <div className="flex h-full flex-col gap-4 overflow-y-auto p-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Activity className="h-5 w-5 text-sky-400" />
          <h1 className="text-lg font-semibold text-slate-100">Simulation Dominance</h1>
          <span className="rounded bg-sky-900/40 px-2 py-0.5 text-[10px] font-medium text-sky-300">
            PAPER ONLY
          </span>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-slate-400">
            tick #{data.orchestrator.tick_count} · {data.orchestrator.engines} engines
          </span>
          <span
            className={`h-2 w-2 rounded-full ${live ? "bg-emerald-400" : "bg-slate-600"}`}
            title={live ? "Live" : err ?? "Offline"}
          />
        </div>
      </div>

      {/* Tabs */}
      <div className="flex flex-wrap gap-1">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`rounded px-3 py-1 text-xs font-medium transition ${tab === t.key ? "bg-sky-600 text-white" : "bg-slate-700/60 text-slate-400 hover:bg-slate-700"}`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Panel */}
      <div className="flex-1">
        {tab === "market"     && <MarketPanel     data={data.synthetic_market} />}
        {tab === "arena"      && <ArenaPanel      data={data.adversarial_arena} />}
        {tab === "crowd"      && <CrowdPanel      data={data.crowd_psychology} />}
        {tab === "reflexive"  && <ReflexivePanel  data={data.reflexive} />}
        {tab === "volatility" && <VolatilityPanel data={data.volatility_cascade} />}
        {tab === "liquidity"  && <LiquidityPanel  data={data.liquidity_warfare} />}
        {tab === "macro"      && <MacroPanel      data={data.macro_stress} onActivate={handleActivate} />}
        {tab === "exchange"   && <ExchangePanel   data={data.exchange_failure} />}
        {tab === "latency"    && <LatencyPanel     data={data.latency_warfare} />}
      </div>

      {err && (
        <div className="rounded border border-red-800/60 bg-red-900/20 px-3 py-2 text-xs text-red-300">
          {err} — using seed data
        </div>
      )}
    </div>
  );
}
