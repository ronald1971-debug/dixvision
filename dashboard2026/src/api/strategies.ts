const BASE = (import.meta.env.VITE_API_BASE ?? "").replace(/\/$/, "");

export type StrategyStage =
  | "submitted"
  | "sandbox"
  | "shadow"
  | "canary"
  | "live"
  | "retired";

export interface CustomStrategy {
  id: string;
  name: string;
  author: string;
  language: string;
  stage: StrategyStage;
  submitted_utc: string;
  promoted_utc?: string;
  sandbox_result?: string;
  retire_reason?: string;
}

export interface StrategiesPayload {
  strategies: CustomStrategy[];
}

export async function fetchCustomStrategies(signal?: AbortSignal): Promise<StrategiesPayload> {
  const res = await fetch(`${BASE}/api/custom-strategies`, {
    signal,
    headers: { Accept: "application/json" },
  });
  if (!res.ok) {
    throw new Error(`GET /api/custom-strategies failed: ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as StrategiesPayload;
}

async function _action(
  endpoint: string,
  strategy_id: string,
  operator_id = "operator",
  reason = "",
): Promise<CustomStrategy> {
  const res = await fetch(`${BASE}/api/custom-strategies/${endpoint}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ strategy_id, operator_id, reason }),
  });
  if (!res.ok) {
    throw new Error(
      `POST /api/custom-strategies/${endpoint} failed: ${res.status} ${res.statusText}`,
    );
  }
  return (await res.json()) as CustomStrategy;
}

export function sandboxStrategy(id: string): Promise<CustomStrategy> {
  return _action("sandbox", id);
}
export function shadowStrategy(id: string): Promise<CustomStrategy> {
  return _action("shadow", id);
}
export function canaryStrategy(id: string): Promise<CustomStrategy> {
  return _action("canary", id);
}
export function requestLiveStrategy(id: string, operator_id: string): Promise<CustomStrategy> {
  return _action("request-live", id, operator_id);
}
export function liveStrategy(id: string, operator_id: string): Promise<CustomStrategy> {
  return _action("live", id, operator_id);
}
export function retireStrategy(id: string, reason: string): Promise<CustomStrategy> {
  return _action("retire", id, "operator", reason);
}

export async function submitStrategy(body: {
  name: string;
  source: string;
  author?: string;
  language?: string;
}): Promise<CustomStrategy> {
  const res = await fetch(`${BASE}/api/custom-strategies`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({
      name: body.name,
      source: body.source,
      author: body.author ?? "operator",
      language: body.language ?? "python",
    }),
  });
  if (!res.ok) {
    throw new Error(`POST /api/custom-strategies failed: ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as CustomStrategy;
}
