/**
 * Stage 8 Simulation Dominance API fetchers.
 *
 * Covers all 12 endpoints under /api/simulation/*.
 * PAPER ONLY / RESEARCH ONLY / LEARNING ONLY / SIMULATION ONLY.
 */

const BASE = (import.meta.env.VITE_API_BASE ?? "").replace(/\/$/, "");

async function _get<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    signal,
    headers: { Accept: "application/json" },
  });
  if (!res.ok) throw new Error(`GET ${path} failed: ${res.status}`);
  return res.json() as Promise<T>;
}

async function _post<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`POST ${path} failed: ${res.status}`);
  return res.json() as Promise<T>;
}

// ─── Shared primitives ────────────────────────────────────────────────────────

export interface SimEvent {
  ts_ns: number;
  kind: string;
  [key: string]: unknown;
}

// ─── Synthetic Market ─────────────────────────────────────────────────────────

export interface SyntheticBar {
  ts_ns: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  vol: number;
  log_return: number;
}

export interface SyntheticBook {
  ts_ns: number;
  bid: number;
  ask: number;
  spread: number;
  mid: number;
  depth_score: number;
}

export interface MarketSnapshotResponse {
  regime: string;
  price: number;
  vol: number;
  baseline_vol: number;
  vol_ratio: number;
  jump_count: number;
  heston_var: number;
  tick_count: number;
  last_log_return: number;
  realised_vol: number;
  recent_bars: SyntheticBar[];
  recent_books: SyntheticBook[];
}

// ─── Adversarial Arena ────────────────────────────────────────────────────────

export interface AgentRecord {
  agent_type: string;
  wins: number;
  losses: number;
  total_edge_bps: number;
  win_rate: number;
  last_action: string;
}

export interface ArenaSnapshotResponse {
  tick_count: number;
  target_survival_rate: number;
  total_actions: number;
  agents: AgentRecord[];
  recent_actions: SimEvent[];
}

// ─── Reflexive ────────────────────────────────────────────────────────────────

export interface ReflexiveSnapshotResponse {
  state: string;
  rho: number;
  sentiment: number;
  momentum: number;
  cascade_count: number;
  correction_count: number;
  tick_count: number;
  rho_history: number[];
  sentiment_history: number[];
  recent_events: SimEvent[];
}

// ─── Liquidity Warfare ────────────────────────────────────────────────────────

export interface LiquiditySnapshotResponse {
  depth_index: number;
  spread_bps: number;
  spoof_count: number;
  layer_count: number;
  iceberg_count: number;
  erosion_count: number;
  tick_count: number;
  impact_1m_bps: number;
  impact_10m_bps: number;
  recent_events: SimEvent[];
}

// ─── Crowd Psychology ─────────────────────────────────────────────────────────

export interface CrowdSnapshotResponse {
  state: string;
  state_idx: number;
  fear_greed: number;
  herding_coeff: number;
  contrarian_signals: number;
  herding_surges: number;
  transitions: number;
  tick_count: number;
  fear_greed_history: number[];
  herding_history: number[];
  recent_events: SimEvent[];
  all_states: string[];
}

// ─── Volatility Cascade ───────────────────────────────────────────────────────

export interface VolatilitySnapshotResponse {
  regime: string;
  current_vol: number;
  baseline_vol: number;
  vol_ratio: number;
  vol_of_vol: number;
  gamma_exposure: number;
  contagion_pool: number;
  cascade_count: number;
  squeeze_count: number;
  contagion_count: number;
  tick_count: number;
  vol_history: number[];
  recent_events: SimEvent[];
}

// ─── Macro Stress ─────────────────────────────────────────────────────────────

export interface MacroScenario {
  name: string;
  active: boolean;
  intensity: number;
  price_multiplier: number;
  vol_multiplier: number;
  liquidity_drain: number;
  duration_bars: number;
}

export interface MacroSnapshotResponse {
  stress_index: number;
  active_count: number;
  activation_count: number;
  tick_count: number;
  composite_vol_mult: number;
  composite_price_impact: number;
  active_scenarios: MacroScenario[];
  inactive_scenarios: string[];
  stress_history: number[];
  recent_events: SimEvent[];
}

// ─── Exchange Failure ─────────────────────────────────────────────────────────

export interface VenueState {
  venue: string;
  state: string;
  fill_rate: number;
  slippage_mult: number;
  latency_mult: number;
  outage_ticks: number;
}

export interface ExchangeSnapshotResponse {
  tick_count: number;
  failure_count: number;
  recovery_count: number;
  venues_failing: number;
  aggregate_fill_rate: number;
  best_venue: string;
  venues: VenueState[];
  recent_events: SimEvent[];
}

// ─── Latency Warfare ─────────────────────────────────────────────────────────

export interface TierSnapshot {
  tier: string;
  latency_us: number;
  queue_priority: number;
  fill_prob: number;
  adverse_sel: number;
  queue_position: number;
}

export interface LatencySnapshotResponse {
  latency_index: number;
  adverse_fills: number;
  queue_jumps: number;
  spike_count: number;
  tick_count: number;
  tiers: TierSnapshot[];
  latency_history: number[];
  recent_events: SimEvent[];
}

// ─── Combined Snapshot ────────────────────────────────────────────────────────

export interface SimulationSnapshotResponse {
  orchestrator: { tick_count: number; engines: number; running: boolean };
  synthetic_market: MarketSnapshotResponse;
  adversarial_arena: ArenaSnapshotResponse;
  reflexive: ReflexiveSnapshotResponse;
  liquidity_warfare: LiquiditySnapshotResponse;
  crowd_psychology: CrowdSnapshotResponse;
  volatility_cascade: VolatilitySnapshotResponse;
  macro_stress: MacroSnapshotResponse;
  exchange_failure: ExchangeSnapshotResponse;
  latency_warfare: LatencySnapshotResponse;
}

// ─── Fetcher functions ────────────────────────────────────────────────────────

export const fetchSimulationSnapshot = (signal?: AbortSignal) =>
  _get<SimulationSnapshotResponse>("/api/simulation/snapshot", signal);

export const fetchSimulationMarket = (signal?: AbortSignal) =>
  _get<MarketSnapshotResponse>("/api/simulation/market", signal);

export const fetchSimulationArena = (signal?: AbortSignal) =>
  _get<ArenaSnapshotResponse>("/api/simulation/arena", signal);

export const fetchSimulationReflexive = (signal?: AbortSignal) =>
  _get<ReflexiveSnapshotResponse>("/api/simulation/reflexive", signal);

export const fetchSimulationLiquidity = (signal?: AbortSignal) =>
  _get<LiquiditySnapshotResponse>("/api/simulation/liquidity", signal);

export const fetchSimulationCrowd = (signal?: AbortSignal) =>
  _get<CrowdSnapshotResponse>("/api/simulation/crowd", signal);

export const fetchSimulationVolatility = (signal?: AbortSignal) =>
  _get<VolatilitySnapshotResponse>("/api/simulation/volatility", signal);

export const fetchSimulationMacro = (signal?: AbortSignal) =>
  _get<MacroSnapshotResponse>("/api/simulation/macro", signal);

export const fetchSimulationExchange = (signal?: AbortSignal) =>
  _get<ExchangeSnapshotResponse>("/api/simulation/exchange", signal);

export const fetchSimulationLatency = (signal?: AbortSignal) =>
  _get<LatencySnapshotResponse>("/api/simulation/latency", signal);

export const activateMacroScenario = (scenario: string) =>
  _post<{ activated: string; ts_ns: number }>("/api/simulation/macro/activate", { scenario });

export const tickSimulation = () =>
  _post<{ ticked: boolean; ts_ns: number }>("/api/simulation/tick");
