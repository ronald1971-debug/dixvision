const BASE = (import.meta.env.VITE_API_BASE ?? "").replace(/\/$/, "");

export interface DecisionEntry {
  id: string;
  ts_utc: string;
  strategy_id?: string;
  signal?: string;
  action: string;
  reason: string;
  outcome?: string;
  approved_by?: string;
}

export interface DecisionTracePayload {
  decisions: DecisionEntry[];
  total?: number;
}

export interface SliderBounds {
  max_order_size_usd: [number, number];
  max_position_pct: [number, number];
  circuit_breaker_drawdown: [number, number];
  circuit_breaker_loss_pct: [number, number];
}

export interface SlidersPayload {
  max_order_size_usd: number;
  max_position_pct: number;
  circuit_breaker_drawdown: number;
  circuit_breaker_loss_pct: number;
  bounds: SliderBounds;
  version_id: string;
}

export interface OperatorActionEntry {
  id: string;
  ts_utc: string;
  kind: string;
  subject: string;
  state: string;
  approvers: string[];
}

export interface OperatorActionsPayload {
  actions: OperatorActionEntry[];
}

export interface OverrideEntry {
  id: string;
  ts_utc: string;
  kind: string;
  parameter: string;
  old_value: unknown;
  new_value: unknown;
  operator_id: string;
  rationale: string;
}

export interface OverrideLogPayload {
  overrides: OverrideEntry[];
  source: string;
  ts_ms: number;
}

export async function fetchOperatorActions(
  limit = 50,
  signal?: AbortSignal,
): Promise<OperatorActionsPayload> {
  const res = await fetch(`${BASE}/api/audit/actions?limit=${limit}`, {
    signal,
    headers: { Accept: "application/json" },
  });
  if (!res.ok) {
    throw new Error(`GET /api/audit/actions failed: ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as OperatorActionsPayload;
}

export async function fetchOverrideLog(
  limit = 50,
  signal?: AbortSignal,
): Promise<OverrideLogPayload> {
  const res = await fetch(`${BASE}/api/audit/overrides?limit=${limit}`, {
    signal,
    headers: { Accept: "application/json" },
  });
  if (!res.ok) {
    throw new Error(`GET /api/audit/overrides failed: ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as OverrideLogPayload;
}

export async function fetchDecisions(
  strategyId?: string,
  limit = 20,
  signal?: AbortSignal,
): Promise<DecisionTracePayload> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (strategyId) params.set("strategy_id", strategyId);
  const res = await fetch(`${BASE}/api/audit/decisions?${params}`, {
    signal,
    headers: { Accept: "application/json" },
  });
  if (!res.ok) {
    throw new Error(`GET /api/audit/decisions failed: ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as DecisionTracePayload;
}

export async function fetchSliders(signal?: AbortSignal): Promise<SlidersPayload> {
  const res = await fetch(`${BASE}/api/risk/sliders`, {
    signal,
    headers: { Accept: "application/json" },
  });
  if (!res.ok) {
    throw new Error(`GET /api/risk/sliders failed: ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as SlidersPayload;
}

export async function setSlider(
  slider: string,
  value: number,
  operator_id = "operator",
): Promise<{ accepted: boolean; slider: string; value: number }> {
  const res = await fetch(`${BASE}/api/risk/sliders`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ slider, value, operator_id }),
  });
  if (!res.ok) {
    throw new Error(`POST /api/risk/sliders failed: ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as { accepted: boolean; slider: string; value: number };
}
