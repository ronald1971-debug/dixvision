/**
 * API functions for the DIX VISION v42.2 dashboard.
 * Organized by domain: DYON (System), INDIRA (Market Execution),
 * GOVERNANCE (Authority), and EVENT-SOURCED LEDGER.
 */

const BASE = (import.meta.env.VITE_API_BASE ?? "").replace(/\/$/, "");

// ============================================================
// TYPE DEFINITIONS
// ============================================================

// DYON Domain Types
export interface LatencyMetrics {
  fast_execute_p50_ms: number;
  fast_execute_p95_ms: number;
  fast_execute_p99_ms: number;
  hazard_detect_p50_ms: number;
  hazard_detect_p95_ms: number;
  ledger_write_p50_ms: number;
  ledger_write_p95_ms: number;
  threshold_ms: number;
}

export interface TrafficMetrics {
  trades_per_sec: number;
  ticks_per_sec: number;
  hazards_per_sec: number;
  ledger_events_per_sec: number;
}

export interface ErrorMetrics {
  rejected_order_rate: number;
  adapter_error_rate: number;
  hazard_critical_rate: number;
}

export interface SaturationMetrics {
  hazard_queue_depth: number;
  hazard_queue_max: number;
  ledger_queue_depth: number;
  ledger_queue_max: number;
  fast_risk_cache_staleness_ms: number;
}

export interface GoldenSignals {
  latency: LatencyMetrics;
  traffic: TrafficMetrics;
  errors: ErrorMetrics;
  saturation: SaturationMetrics;
  timestamp_utc: string;
}

export interface SLOBurnRate {
  budget_1h_percent: number;
  budget_6h_percent: number;
  budget_24h_percent: number;
  alert_threshold_percent: number;
  timestamp_utc: string;
}

export type HazardSeverity = "INFO" | "WARNING" | "CRITICAL";
export type HazardStatus = "pending" | "escalated" | "resolved";

export interface SystemHazard {
  id: string;
  timestamp_utc: string;
  hazard_type: string;
  severity: HazardSeverity;
  status: HazardStatus;
  message: string;
  ledger_seq?: number;
}

export type TradingForm =
  | "SPOT"
  | "MARGIN"
  | "PERP"
  | "FUTURES"
  | "OPTIONS"
  | "DEX_SWAP"
  | "DEX_LP";

export interface TradingFormMetrics {
  form: TradingForm;
  active_signals: number;
  fill_rate_percent: number;
  exposure_usd: number;
  pnl_usd: number;
  active_adapters: string[];
  enabled: boolean;
}

export type AdapterType = "CEX" | "DEX";

export interface AdapterHealth {
  adapter_id: string;
  name: string;
  adapter_type: AdapterType;
  supported_forms: TradingForm[];
  connected: boolean;
  last_tick_age_ms: number;
  throughput_per_min: number;
  reject_count_24h: number;
  error_rate: number;
}

// INDIRA Domain Types (Execution)
export type OrderSide = "BUY" | "SELL";
export type OrderType = "MARKET" | "LIMIT" | "STOP" | "STOP_LIMIT";
export type OrderStatus = "OPEN" | "PARTIALLY_FILLED" | "FILLED" | "CANCELLED" | "REJECTED";

export interface OpenOrder {
  order_id: string;
  symbol: string;
  side: OrderSide;
  order_type: OrderType;
  price: number | null;
  quantity: number;
  filled_quantity: number;
  status: OrderStatus;
  created_at: string;
  adapter_id: string;
  form: TradingForm;
}

export interface Fill {
  fill_id: string;
  order_id: string;
  symbol: string;
  side: OrderSide;
  price: number;
  quantity: number;
  fee: number;
  fee_currency: string;
  timestamp_utc: string;
  adapter_id: string;
}

export interface OrderSubmission {
  symbol: string;
  side: OrderSide;
  order_type: OrderType;
  quantity: number;
  price?: number;
  stop_price?: number;
  adapter_id: string;
  form: TradingForm;
}

export interface OrderResponse {
  success: boolean;
  order_id?: string;
  message: string;
  ledger_seq?: number;
}

export interface StrategyStatus {
  strategy_id: string;
  name: string;
  active: boolean;
  pnl_usd: number;
  positions: number;
}

export interface PositionInfo {
  position_id: string;
  symbol: string;
  side: OrderSide;
  quantity: number;
  entry_price: number;
  current_price: number;
  unrealized_pnl: number;
  adapter_id: string;
  form: TradingForm;
}

// GOVERNANCE Domain Types
export type SystemMode = "NORMAL" | "SAFE" | "DEGRADED" | "HALTED";
export type KillSwitchState = "ARMED" | "DISARMED" | "FIRED";

export interface ModeTransition {
  id: string;
  from_mode: SystemMode;
  to_mode: SystemMode;
  timestamp_utc: string;
  reason: string;
  triggered_by: string;
  ledger_seq: number;
}

export interface AuthorityViolation {
  id: string;
  timestamp_utc: string;
  violator_domain: "INDIRA" | "DYON" | "GOVERNANCE";
  attempted_action: string;
  blocked: boolean;
  reason: string;
  ledger_seq: number;
}

export interface SecurityEvents {
  kill_switch_state: KillSwitchState;
  violations_24h: AuthorityViolation[];
  violation_count_24h: number;
}

export interface ExecutionConstraintSet {
  max_drawdown_percent: number;
  max_loss_per_trade_percent: number;
  fail_closed: boolean;
  trading_allowed: boolean;
  last_updated_utc: string;
}

export interface KillSwitchResponse {
  success: boolean;
  new_state: KillSwitchState;
  message: string;
  ledger_seq?: number;
}

// LEDGER Domain Types
export type LedgerStream = "MARKET" | "SYSTEM" | "GOVERNANCE" | "HAZARD" | "SECURITY";

export interface LedgerEvent {
  seq: number;
  timestamp_utc: string;
  stream: LedgerStream;
  sub_type: string;
  hash_prefix: string;
  payload_preview: string;
}

export interface LedgerChainStatus {
  ok: boolean;
  verified_to_seq: number;
  break_at_seq?: number;
  break_reason?: string;
}

export interface LedgerTailResponse {
  events: LedgerEvent[];
  chain_status: LedgerChainStatus;
}

// ============================================================
// DYON DOMAIN (System Observation)
// ============================================================

export async function fetchGoldenSignals(
  signal?: AbortSignal
): Promise<GoldenSignals> {
  const res = await fetch(`${BASE}/api/signals`, {
    signal,
    headers: { Accept: "application/json" },
  });
  if (!res.ok) {
    throw new Error(`GET /api/signals failed: ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as GoldenSignals;
}

export async function fetchSLOBurnRate(
  signal?: AbortSignal
): Promise<SLOBurnRate> {
  const res = await fetch(`${BASE}/api/signals/slo`, {
    signal,
    headers: { Accept: "application/json" },
  });
  if (!res.ok) {
    throw new Error(`GET /api/signals/slo failed: ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as SLOBurnRate;
}

export async function fetchSystemHazards(
  signal?: AbortSignal
): Promise<SystemHazard[]> {
  const res = await fetch(`${BASE}/api/hazards`, {
    signal,
    headers: { Accept: "application/json" },
  });
  if (!res.ok) {
    throw new Error(`GET /api/hazards failed: ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as SystemHazard[];
}

export async function fetchAdapterHealth(
  signal?: AbortSignal
): Promise<AdapterHealth[]> {
  const res = await fetch(`${BASE}/api/adapters`, {
    signal,
    headers: { Accept: "application/json" },
  });
  if (!res.ok) {
    throw new Error(`GET /api/adapters failed: ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as AdapterHealth[];
}

// ============================================================
// INDIRA DOMAIN (Market Execution)
// ============================================================

export async function fetchTradingForms(
  signal?: AbortSignal
): Promise<TradingFormMetrics[]> {
  const res = await fetch(`${BASE}/api/forms`, {
    signal,
    headers: { Accept: "application/json" },
  });
  if (!res.ok) {
    throw new Error(`GET /api/forms failed: ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as TradingFormMetrics[];
}

export async function fetchOpenOrders(
  signal?: AbortSignal
): Promise<OpenOrder[]> {
  const res = await fetch(`${BASE}/api/orders/open`, {
    signal,
    headers: { Accept: "application/json" },
  });
  if (!res.ok) {
    throw new Error(`GET /api/orders/open failed: ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as OpenOrder[];
}

export async function fetchRecentFills(
  signal?: AbortSignal
): Promise<Fill[]> {
  const res = await fetch(`${BASE}/api/fills`, {
    signal,
    headers: { Accept: "application/json" },
  });
  if (!res.ok) {
    throw new Error(`GET /api/fills failed: ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as Fill[];
}

export async function submitOrder(
  order: OrderSubmission
): Promise<OrderResponse> {
  const res = await fetch(`${BASE}/api/orders/submit`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify(order),
  });
  if (!res.ok) {
    throw new Error(`POST /api/orders/submit failed: ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as OrderResponse;
}

export async function cancelOrder(orderId: string): Promise<OrderResponse> {
  const res = await fetch(`${BASE}/api/orders/cancel`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify({ order_id: orderId }),
  });
  if (!res.ok) {
    throw new Error(`POST /api/orders/cancel failed: ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as OrderResponse;
}

export async function cancelAllOrders(): Promise<OrderResponse> {
  const res = await fetch(`${BASE}/api/orders/cancel-all`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify({}),
  });
  if (!res.ok) {
    throw new Error(`POST /api/orders/cancel-all failed: ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as OrderResponse;
}

export async function activateStrategy(
  strategyId: string
): Promise<OrderResponse> {
  const res = await fetch(`${BASE}/api/strategies/activate`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify({ strategy_id: strategyId }),
  });
  if (!res.ok) {
    throw new Error(`POST /api/strategies/activate failed: ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as OrderResponse;
}

export async function pauseStrategy(strategyId: string): Promise<OrderResponse> {
  const res = await fetch(`${BASE}/api/strategies/pause`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify({ strategy_id: strategyId }),
  });
  if (!res.ok) {
    throw new Error(`POST /api/strategies/pause failed: ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as OrderResponse;
}

export async function pauseAllStrategies(): Promise<OrderResponse> {
  const res = await fetch(`${BASE}/api/strategies/pause-all`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify({}),
  });
  if (!res.ok) {
    throw new Error(`POST /api/strategies/pause-all failed: ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as OrderResponse;
}

export async function closePosition(positionId: string): Promise<OrderResponse> {
  const res = await fetch(`${BASE}/api/positions/close`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify({ position_id: positionId }),
  });
  if (!res.ok) {
    throw new Error(`POST /api/positions/close failed: ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as OrderResponse;
}

// ============================================================
// GOVERNANCE DOMAIN (Authority Layer)
// ============================================================

export async function fetchModeTimeline(
  signal?: AbortSignal
): Promise<ModeTransition[]> {
  const res = await fetch(`${BASE}/api/mode/timeline`, {
    signal,
    headers: { Accept: "application/json" },
  });
  if (!res.ok) {
    throw new Error(`GET /api/mode/timeline failed: ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as ModeTransition[];
}

export async function fetchSecurityEvents(
  signal?: AbortSignal
): Promise<SecurityEvents> {
  const res = await fetch(`${BASE}/api/security/events`, {
    signal,
    headers: { Accept: "application/json" },
  });
  if (!res.ok) {
    throw new Error(`GET /api/security/events failed: ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as SecurityEvents;
}

export async function fetchConstraintSet(
  signal?: AbortSignal
): Promise<ExecutionConstraintSet> {
  const res = await fetch(`${BASE}/api/governance/constraints`, {
    signal,
    headers: { Accept: "application/json" },
  });
  if (!res.ok) {
    throw new Error(`GET /api/governance/constraints failed: ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as ExecutionConstraintSet;
}

export async function armKillSwitch(): Promise<KillSwitchResponse> {
  const res = await fetch(`${BASE}/api/kill-switch`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify({ action: "arm" }),
  });
  if (!res.ok) {
    throw new Error(`POST /api/kill-switch (arm) failed: ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as KillSwitchResponse;
}

export async function disarmKillSwitch(): Promise<KillSwitchResponse> {
  const res = await fetch(`${BASE}/api/kill-switch`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify({ action: "disarm" }),
  });
  if (!res.ok) {
    throw new Error(`POST /api/kill-switch (disarm) failed: ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as KillSwitchResponse;
}

export async function fireKillSwitch(reason: string): Promise<KillSwitchResponse> {
  const res = await fetch(`${BASE}/api/kill-switch`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify({ action: "fire", reason }),
  });
  if (!res.ok) {
    throw new Error(`POST /api/kill-switch (fire) failed: ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as KillSwitchResponse;
}

// ============================================================
// EVENT-SOURCED LEDGER
// ============================================================

export async function fetchLedgerTail(
  streams?: LedgerStream[],
  limit = 100,
  signal?: AbortSignal
): Promise<LedgerTailResponse> {
  const params = new URLSearchParams();
  if (streams && streams.length > 0) {
    params.set("streams", streams.join(","));
  }
  params.set("limit", String(limit));

  const res = await fetch(`${BASE}/api/ledger/tail?${params.toString()}`, {
    signal,
    headers: { Accept: "application/json" },
  });
  if (!res.ok) {
    throw new Error(`GET /api/ledger/tail failed: ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as LedgerTailResponse;
}

export async function verifyLedgerChain(
  signal?: AbortSignal
): Promise<LedgerChainStatus> {
  const res = await fetch(`${BASE}/api/ledger/verify`, {
    signal,
    headers: { Accept: "application/json" },
  });
  if (!res.ok) {
    throw new Error(`GET /api/ledger/verify failed: ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as LedgerChainStatus;
}

export async function exportLedger(
  streams?: LedgerStream[],
  limit = 1000
): Promise<Blob> {
  const params = new URLSearchParams();
  if (streams && streams.length > 0) {
    params.set("streams", streams.join(","));
  }
  params.set("limit", String(limit));

  const res = await fetch(`${BASE}/api/ledger/export?${params.toString()}`, {
    headers: { Accept: "application/x-ndjson" },
  });
  if (!res.ok) {
    throw new Error(`GET /api/ledger/export failed: ${res.status} ${res.statusText}`);
  }
  return res.blob();
}

export async function replayLedger(
  fromSeq: number,
  signal?: AbortSignal
): Promise<{ success: boolean; rebuilt_hash: string; events_replayed: number }> {
  const res = await fetch(`${BASE}/api/ledger/replay`, {
    method: "POST",
    signal,
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify({ from_seq: fromSeq }),
  });
  if (!res.ok) {
    throw new Error(`POST /api/ledger/replay failed: ${res.status} ${res.statusText}`);
  }
  return res.json();
}
