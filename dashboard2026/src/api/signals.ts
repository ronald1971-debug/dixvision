import { apiUrl } from "@/api/base";

// ── DYON Domain ──────────────────────────────────────────────────────────────

export interface GoldenSignalsPayload {
  ts_ms: number;
  latency: {
    fast_execute_p50_ms: number;
    fast_execute_p95_ms: number;
    fast_execute_p99_ms: number;
    hazard_detect_p50_ms: number;
    hazard_detect_p95_ms: number;
    hazard_detect_p99_ms: number;
    ledger_write_p50_ms: number;
    ledger_write_p95_ms: number;
    ledger_write_p99_ms: number;
    threshold_ms: number;
  };
  traffic: {
    trades_per_sec: number;
    ticks_per_sec: number;
    hazards_per_sec: number;
    ledger_events_per_sec: number;
  };
  errors: {
    rejected_order_rate_pct: number;
    adapter_error_rate_pct: number;
    hazard_critical_rate_pct: number;
  };
  saturation: {
    hazard_queue_depth: number;
    ledger_queue_depth: number;
    risk_cache_age_ms: number;
  };
}

export async function fetchGoldenSignals(signal?: AbortSignal): Promise<GoldenSignalsPayload> {
  const res = await fetch(apiUrl("/api/signals"), {
    signal,
    headers: { Accept: "application/json" },
  });
  if (!res.ok) throw new Error(`GET /api/signals failed: ${res.status} ${res.statusText}`);
  return (await res.json()) as GoldenSignalsPayload;
}

export interface SLOBurnRate {
  window: string;
  budget_pct: number;
  burn_pct: number;
  status: string;
}

export interface SLOBurnRatePayload {
  ts_ms: number;
  windows: SLOBurnRate[];
}

export async function fetchSLOBurnRate(signal?: AbortSignal): Promise<SLOBurnRatePayload> {
  const res = await fetch(apiUrl("/api/slo/burn-rate"), {
    signal,
    headers: { Accept: "application/json" },
  });
  if (!res.ok) throw new Error(`GET /api/slo/burn-rate failed: ${res.status} ${res.statusText}`);
  return (await res.json()) as SLOBurnRatePayload;
}

export interface AdapterMeta {
  name: string;
  venue: string;
  forms: string[];
  state: "DISCONNECTED" | "CONNECTING" | "READY" | "DEGRADED" | "HALTED";
  last_tick_ms: number;
  throughput_per_min: number;
  rejects: number;
}

export interface AdapterHealthPayload {
  adapters: AdapterMeta[];
  ts_ms: number;
}

export async function fetchAdapterHealth(signal?: AbortSignal): Promise<AdapterHealthPayload> {
  const res = await fetch(apiUrl("/api/adapters"), {
    signal,
    headers: { Accept: "application/json" },
  });
  if (!res.ok) throw new Error(`GET /api/adapters failed: ${res.status} ${res.statusText}`);
  return (await res.json()) as AdapterHealthPayload;
}

export interface HazardEvent {
  id: string;
  ts_utc: string;
  kind: string;
  hazard_type: string;
  severity: string;
  source: string;
  escalation: string;
}

export interface HazardsPayload {
  hazards: HazardEvent[];
  ts_ms: number;
}

export async function fetchSystemHazards(signal?: AbortSignal): Promise<HazardsPayload> {
  const res = await fetch(apiUrl("/api/hazards?limit=50"), {
    signal,
    headers: { Accept: "application/json" },
  });
  if (!res.ok) throw new Error(`GET /api/hazards failed: ${res.status} ${res.statusText}`);
  return (await res.json()) as HazardsPayload;
}

// ── INDIRA Domain (Execution) ─────────────────────────────────────────────────

export interface TradingForm {
  form: string;
  signals: number;
  fill_rate_pct: number;
  exposure_usd: number;
  pnl_usd: number;
  adapters_ready: number;
}

export interface TradingFormsPayload {
  forms: TradingForm[];
  ts_ms: number;
}

export async function fetchTradingForms(signal?: AbortSignal): Promise<TradingFormsPayload> {
  const res = await fetch(apiUrl("/api/forms"), {
    signal,
    headers: { Accept: "application/json" },
  });
  if (!res.ok) throw new Error(`GET /api/forms failed: ${res.status} ${res.statusText}`);
  return (await res.json()) as TradingFormsPayload;
}

export interface Order {
  id: string;
  symbol: string;
  side: string;
  type: string;
  qty: number;
  price: number | null;
  status: string;
  ts_utc: string;
}

export interface OpenOrdersPayload {
  orders: Order[];
  ts_ms: number;
}

export async function fetchOpenOrders(signal?: AbortSignal): Promise<OpenOrdersPayload> {
  const res = await fetch(apiUrl("/api/orders/open"), {
    signal,
    headers: { Accept: "application/json" },
  });
  if (!res.ok) throw new Error(`GET /api/orders/open failed: ${res.status} ${res.statusText}`);
  return (await res.json()) as OpenOrdersPayload;
}

export interface Fill {
  id: string;
  symbol: string;
  side: string;
  qty: number;
  price: number;
  fee_usd: number;
  ts_utc: string;
}

export interface FillsPayload {
  fills: Fill[];
  ts_ms: number;
}

export async function fetchRecentFills(limit = 20, signal?: AbortSignal): Promise<FillsPayload> {
  const res = await fetch(apiUrl(`/api/fills?limit=${limit}`), {
    signal,
    headers: { Accept: "application/json" },
  });
  if (!res.ok) throw new Error(`GET /api/fills failed: ${res.status} ${res.statusText}`);
  return (await res.json()) as FillsPayload;
}

export interface OrderSubmitInput {
  symbol: string;
  side?: string;
  type?: string;
  qty: number;
  price?: number | null;
}

export async function submitOrder(input: OrderSubmitInput, signal?: AbortSignal) {
  const res = await fetch(apiUrl("/api/orders/submit"), {
    method: "POST",
    signal,
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(input),
  });
  if (!res.ok) throw new Error(`POST /api/orders/submit failed: ${res.status} ${res.statusText}`);
  return (await res.json()) as Record<string, unknown>;
}

export async function cancelOrder(orderId: string, signal?: AbortSignal) {
  const res = await fetch(apiUrl("/api/orders/cancel"), {
    method: "POST",
    signal,
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ order_id: orderId }),
  });
  if (!res.ok) throw new Error(`POST /api/orders/cancel failed: ${res.status} ${res.statusText}`);
  return (await res.json()) as Record<string, unknown>;
}

export async function cancelAllOrders(signal?: AbortSignal) {
  const res = await fetch(apiUrl("/api/orders/cancel-all"), {
    method: "POST",
    signal,
    headers: { Accept: "application/json" },
  });
  if (!res.ok) throw new Error(`POST /api/orders/cancel-all failed: ${res.status} ${res.statusText}`);
  return (await res.json()) as Record<string, unknown>;
}

export async function activateStrategy(strategyId: string, signal?: AbortSignal) {
  const res = await fetch(apiUrl("/api/strategies/activate"), {
    method: "POST",
    signal,
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ strategy_id: strategyId }),
  });
  if (!res.ok) throw new Error(`POST /api/strategies/activate failed: ${res.status} ${res.statusText}`);
  return (await res.json()) as Record<string, unknown>;
}

export async function pauseStrategy(strategyId: string, signal?: AbortSignal) {
  const res = await fetch(apiUrl("/api/strategies/pause"), {
    method: "POST",
    signal,
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ strategy_id: strategyId }),
  });
  if (!res.ok) throw new Error(`POST /api/strategies/pause failed: ${res.status} ${res.statusText}`);
  return (await res.json()) as Record<string, unknown>;
}

export async function closePosition(positionId: string, signal?: AbortSignal) {
  const res = await fetch(apiUrl("/api/positions/close"), {
    method: "POST",
    signal,
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ position_id: positionId }),
  });
  if (!res.ok) throw new Error(`POST /api/positions/close failed: ${res.status} ${res.statusText}`);
  return (await res.json()) as Record<string, unknown>;
}

// ── GOVERNANCE Domain ─────────────────────────────────────────────────────────

export interface ModeTransition {
  ts_utc: string;
  from_mode: string;
  to_mode: string;
  reason: string;
}

export interface ModeTimelinePayload {
  timeline: ModeTransition[];
  ts_ms: number;
}

export async function fetchModeTimeline(signal?: AbortSignal): Promise<ModeTimelinePayload> {
  const res = await fetch(apiUrl("/api/mode/timeline?limit=20"), {
    signal,
    headers: { Accept: "application/json" },
  });
  if (!res.ok) throw new Error(`GET /api/mode/timeline failed: ${res.status} ${res.statusText}`);
  return (await res.json()) as ModeTimelinePayload;
}

export interface AuthorityViolation {
  id: string;
  ts_utc: string;
  kind: string;
  subject: string;
  state: string;
  approvers: string[];
}

export interface SecurityEventsPayload {
  violations: AuthorityViolation[];
  total: number;
  ts_ms: number;
}

export async function fetchSecurityEvents(signal?: AbortSignal): Promise<SecurityEventsPayload> {
  const res = await fetch(apiUrl("/api/security/events?limit=50"), {
    signal,
    headers: { Accept: "application/json" },
  });
  if (!res.ok) throw new Error(`GET /api/security/events failed: ${res.status} ${res.statusText}`);
  return (await res.json()) as SecurityEventsPayload;
}

export async function triggerKillSwitch(reason = "", signal?: AbortSignal) {
  const res = await fetch(apiUrl("/api/kill-switch"), {
    method: "POST",
    signal,
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ reason }),
  });
  if (!res.ok) throw new Error(`POST /api/kill-switch failed: ${res.status} ${res.statusText}`);
  return (await res.json()) as Record<string, unknown>;
}

// ── EVENT-SOURCED LEDGER ───────────────────────────────────────────────────────

export interface LedgerEvent {
  seq: number;
  ts_utc: string;
  chain: string;
  kind: string;
  sub_type: string;
  hash_prefix: string;
  payload_summary: string;
}

export interface LedgerTailPayload {
  events: LedgerEvent[];
  chain_stats: Record<string, unknown>;
  ts_ms: number;
}

export async function fetchLedgerTail(limit = 100, stream = "", signal?: AbortSignal): Promise<LedgerTailPayload> {
  const qs = new URLSearchParams({ limit: String(limit) });
  if (stream) qs.set("stream", stream);
  const res = await fetch(apiUrl(`/api/ledger/tail?${qs.toString()}`), {
    signal,
    headers: { Accept: "application/json" },
  });
  if (!res.ok) throw new Error(`GET /api/ledger/tail failed: ${res.status} ${res.statusText}`);
  return (await res.json()) as LedgerTailPayload;
}

export interface LedgerVerifyPayload {
  ok: boolean;
  break_row: string | null;
  ts_ms: number;
}

export async function verifyLedgerChain(signal?: AbortSignal): Promise<LedgerVerifyPayload> {
  const res = await fetch(apiUrl("/api/ledger/verify"), {
    signal,
    headers: { Accept: "application/json" },
  });
  if (!res.ok) throw new Error(`GET /api/ledger/verify failed: ${res.status} ${res.statusText}`);
  return (await res.json()) as LedgerVerifyPayload;
}

export async function exportLedger(limit = 1000, signal?: AbortSignal): Promise<Blob> {
  const res = await fetch(apiUrl(`/api/ledger/export?limit=${limit}`), {
    signal,
  });
  if (!res.ok) throw new Error(`GET /api/ledger/export failed: ${res.status} ${res.statusText}`);
  return res.blob();
}

export interface ReplayPayload {
  preview: boolean;
  from_seq: number;
  events_replayed: number;
  projector_hash: string;
  status: string;
  ts_ms: number;
}

export async function replayLedger(fromSeq = 0, signal?: AbortSignal): Promise<ReplayPayload> {
  const res = await fetch(apiUrl("/api/ledger/replay"), {
    method: "POST",
    signal,
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ from_seq: fromSeq }),
  });
  if (!res.ok) throw new Error(`POST /api/ledger/replay failed: ${res.status} ${res.statusText}`);
  return (await res.json()) as ReplayPayload;
}
